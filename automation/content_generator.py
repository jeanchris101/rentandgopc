"""
Punta Cana Properties — AI Content Generator
Uses Claude Haiku to generate social posts (4 languages) and weekly blog drafts.
Hard budget cap: $0.25/day on API calls.
"""

import os
import json
import sys
from datetime import datetime, date
from pathlib import Path
from anthropic import Anthropic

# --- Config ---
MODEL = "claude-haiku-4-5-20251001"
COST_PER_MTOK_INPUT = 0.80    # $/million tokens
COST_PER_MTOK_OUTPUT = 4.00   # $/million tokens
DAILY_BUDGET = 0.25           # USD
DATA_DIR = Path(__file__).parent / "data"
QUEUE_FILE = DATA_DIR / "content-queue.json"
USAGE_FILE = DATA_DIR / "usage-log.json"

LANGUAGES = ["en", "es", "fr", "ru"]

TOPICS = [
    "lifestyle",
    "roi",
    "market_stats",
    "neighborhood",
    "try_before_you_buy",
]

BRAND_SYSTEM_PROMPT = """You are a content writer for Rent & Go PC, a vacation rental and real estate company in Punta Cana, Dominican Republic. The founder is Ari — authentic, helpful, not salesy.

Brand voice rules:
- Value-first: lead with what the reader gains, not what you're selling
- Authentic: write like a knowledgeable friend, not a corporate brochure
- Specific: use real numbers (8-12% ROI, $25K-35K/yr Airbnb income, 4h30 from Montreal)
- No hype words: avoid "luxury", "paradise", "dream", "exclusive", "once in a lifetime"
- No CONFOTUR references — say "tax benefits" if relevant
- Quebec French: use "tu" form, "condo" not "appartement", "rendement" not "ROI"
- Russian: natural conversational tone, use "ты" form

Property context:
- 2BR condos in Cocotal Golf & Country Club, Bavaro area
- $180,000-$220,000 price range
- Airbnb generates $25,000-$35,000/year (8-12% net return)
- 100% foreign ownership allowed in DR
- 90-day rental credit: stay first, buy later, 100% of rent applies to purchase
- Direct flights from Montreal (4h30, Sunwing/Air Transat), NYC, Miami
- Gated community, golf course, pools, 10 min to beach
"""

TOPIC_PROMPTS = {
    "lifestyle": "Write about the Punta Cana lifestyle — morning coffee overlooking the golf course, beach days, the expat community, year-round summer. Make readers feel what daily life is like.",
    "roi": "Write about rental income and investment returns. Use specific numbers: $120-180/night on Airbnb, 65-80% occupancy, 8-12% net annual return. Compare to stock market or savings accounts.",
    "market_stats": "Write about the Punta Cana real estate market — 7M+ tourists/year, property appreciation of 5-10% annually, USD-based economy, growing infrastructure. Position as a smart investment.",
    "neighborhood": "Spotlight a neighborhood or feature: Cocotal Golf, Bavaro Beach, Cap Cana marina, Downtown Punta Cana. Describe what makes it special for owners and renters.",
    "try_before_you_buy": "Promote the Try Before You Buy program — stay in the actual condo, experience the lifestyle, then decide. 100% of rent credited to purchase within 90 days. No pressure, no timeshare pitch.",
}

SOCIAL_POST_PROMPT = """Generate a social media post about: {topic_description}

Requirements:
- Write the post in ALL 4 languages: English, Spanish, French (Quebec), Russian
- Each version should feel natural in that language, not a direct translation
- Include 3-5 relevant hashtags per language
- Keep each post under 280 characters (Twitter-friendly) but also suitable for Instagram/Facebook
- Include a call to action (visit website, DM for info, link in bio, etc.)

Return valid JSON with this exact structure:
{{
  "en": {{"text": "...", "hashtags": ["...", "..."]}},
  "es": {{"text": "...", "hashtags": ["...", "..."]}},
  "fr": {{"text": "...", "hashtags": ["...", "..."]}},
  "ru": {{"text": "...", "hashtags": ["...", "..."]}}
}}

Return ONLY the JSON, no other text."""

BLOG_PROMPT = """Write a blog article about: {topic_description}

Requirements:
- Write in English only (will be translated separately)
- 600-900 words, SEO-friendly
- Include a compelling H1 title and 3-5 H2 subheadings
- Include specific numbers and data points
- End with a clear call to action
- Tone: informative, trustworthy, conversational

Return valid JSON:
{{
  "title": "...",
  "slug": "...",
  "meta_description": "...",
  "content_html": "..."
}}

Return ONLY the JSON, no other text."""


def calc_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * COST_PER_MTOK_INPUT / 1_000_000) + \
           (output_tokens * COST_PER_MTOK_OUTPUT / 1_000_000)


def load_json(path: Path, default=None):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else []


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_today_spend(usage_log: list) -> float:
    today = date.today().isoformat()
    return sum(e["cost_usd"] for e in usage_log if e["date"] == today)


def log_usage(usage_log: list, entry: dict) -> list:
    usage_log.append(entry)
    save_json(USAGE_FILE, usage_log)
    return usage_log


def get_topic_for_today() -> str:
    day_of_year = date.today().timetuple().tm_yday
    return TOPICS[day_of_year % len(TOPICS)]


def get_second_topic_for_today() -> str:
    day_of_year = date.today().timetuple().tm_yday
    return TOPICS[(day_of_year + 2) % len(TOPICS)]


def is_blog_day() -> bool:
    """Generate a blog on Mondays (weekday 0)."""
    return date.today().weekday() == 0


def call_haiku(client: Anthropic, user_prompt: str, usage_log: list) -> tuple[str | None, list]:
    """Call Haiku API. Returns (response_text, updated_usage_log) or (None, log) if budget exceeded."""
    today_spend = get_today_spend(usage_log)
    if today_spend >= DAILY_BUDGET:
        print(f"  Budget cap reached: ${today_spend:.4f} >= ${DAILY_BUDGET}")
        return None, usage_log

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=BRAND_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = calc_cost(input_tokens, output_tokens)
    text = response.content[0].text

    entry = {
        "date": date.today().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "type": "api_call",
        "model": MODEL,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        "daily_total_usd": round(today_spend + cost, 6),
    }
    usage_log = log_usage(usage_log, entry)
    print(f"  Tokens: {input_tokens} in / {output_tokens} out — Cost: ${cost:.4f} — Daily total: ${today_spend + cost:.4f}")

    return text, usage_log


def parse_json_response(text: str) -> dict | None:
    """Extract JSON from response, handling markdown code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (code fences)
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  Failed to parse JSON: {e}")
        return None


def generate_social_post(client: Anthropic, topic: str, usage_log: list) -> tuple[dict | None, list]:
    """Generate a social post in 4 languages. Returns (post_data, updated_log)."""
    description = TOPIC_PROMPTS[topic]
    prompt = SOCIAL_POST_PROMPT.format(topic_description=description)

    print(f"Generating social post: {topic}")
    text, usage_log = call_haiku(client, prompt, usage_log)
    if text is None:
        return None, usage_log

    parsed = parse_json_response(text)
    if parsed is None:
        return None, usage_log

    post = {
        "id": f"social-{date.today().isoformat()}-{topic}",
        "type": "social_post",
        "topic": topic,
        "generated_at": datetime.now().isoformat(),
        "status": "draft",
        "content": parsed,
    }
    return post, usage_log


def generate_blog(client: Anthropic, topic: str, usage_log: list) -> tuple[dict | None, list]:
    """Generate a blog article draft. Returns (blog_data, updated_log)."""
    description = TOPIC_PROMPTS[topic]
    prompt = BLOG_PROMPT.format(topic_description=description)

    print(f"Generating blog article: {topic}")
    text, usage_log = call_haiku(client, prompt, usage_log)
    if text is None:
        return None, usage_log

    parsed = parse_json_response(text)
    if parsed is None:
        return None, usage_log

    blog = {
        "id": f"blog-{date.today().isoformat()}-{topic}",
        "type": "blog_article",
        "topic": topic,
        "generated_at": datetime.now().isoformat(),
        "status": "draft",
        "content": parsed,
    }
    return blog, usage_log


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    usage_log = load_json(USAGE_FILE, [])
    queue = load_json(QUEUE_FILE, [])

    today_spend = get_today_spend(usage_log)
    print(f"Daily budget: ${DAILY_BUDGET} — Spent today: ${today_spend:.4f}")

    if today_spend >= DAILY_BUDGET:
        print("Budget cap reached for today. Exiting.")
        return

    # Generate 1-2 social posts
    topic1 = get_topic_for_today()
    post1, usage_log = generate_social_post(client, topic1, usage_log)
    if post1:
        queue.append(post1)
        print(f"  Added: {post1['id']}")

    topic2 = get_second_topic_for_today()
    post2, usage_log = generate_social_post(client, topic2, usage_log)
    if post2:
        queue.append(post2)
        print(f"  Added: {post2['id']}")

    # Generate blog on Mondays
    if is_blog_day():
        blog_topic = topic1
        blog, usage_log = generate_blog(client, blog_topic, usage_log)
        if blog:
            queue.append(blog)
            print(f"  Added: {blog['id']}")
    else:
        print("Not a blog day (Monday only). Skipping blog generation.")

    save_json(QUEUE_FILE, queue)

    final_spend = get_today_spend(usage_log)
    print(f"\nDone. Daily spend: ${final_spend:.4f} / ${DAILY_BUDGET}")
    print(f"Queue size: {len(queue)} items")


if __name__ == "__main__":
    main()
