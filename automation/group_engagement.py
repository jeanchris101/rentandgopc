"""
Punta Cana Properties — Group Engagement Assistant
Scans FB group posts, detects questions, generates helpful reply suggestions using Claude Haiku.
Daily budget cap: $0.25 on API calls.
"""

import os
import json
import re
import sys
import argparse
from datetime import datetime, date
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
RAW_POSTS_FILE = DATA_DIR / "group-raw-posts.json"
QUESTIONS_FILE = DATA_DIR / "group-questions.json"
USAGE_FILE = DATA_DIR / "engagement-usage.json"

MODEL = "claude-haiku-4-5-20251001"
COST_PER_MTOK_INPUT = 0.80    # $/million tokens
COST_PER_MTOK_OUTPUT = 4.00   # $/million tokens
DAILY_BUDGET = 0.50           # USD
CLASSIFY_BATCH_SIZE = 20      # posts per classification call

TOPICS = [
    "cost_of_living", "neighborhoods", "buying_process", "rental_income",
    "visa_residency", "lifestyle", "schools", "safety", "healthcare",
    "restaurants_food", "travel_tips", "construction_renovation", "legal",
    "car_rentals", "other",
]

CLASSIFY_SYSTEM_PROMPT = """You are a classifier for Facebook group posts about Punta Cana / Dominican Republic.

For each post, determine:
1. is_question: Is this a question, request for advice, recommendation ask, or someone seeking information? (true/false)
   - TRUE for: direct questions, "looking for...", "anyone know...", "anyone recommend...", "has anyone...", "help me with...", sharing a problem/dilemma, comparing options, asking for opinions/experiences, travel questions, passport/visa questions, food/restaurant recs, activity suggestions, moving logistics, ANY post where someone could benefit from a helpful local reply
   - FALSE for: ads/listings, memes, event promotions, pure statements with no implicit question, news shares, someone just posting photos
   - FALSE for RHETORICAL QUESTIONS in ads/promotions: If a post uses a question mark as a sales hook ("Do you have a property and wonder about Airbnb?") but then offers a service ("I help you from A to Z"), that is an AD, not a question. The "?" is rhetorical — they are not seeking information, they are selling. Look for patterns like: question followed by "I/we help you", "contact me", "our services", professional service language, or self-promotion. These should ALWAYS be is_question: false.
2. language: What language is it in? (en/es/fr/other)
3. topic: Best matching topic from this list: cost_of_living, neighborhoods, buying_process, rental_income, visa_residency, lifestyle, schools, safety, healthcare, restaurants_food, travel_tips, construction_renovation, legal, car_rentals, other
   - car_rentals: questions about renting cars, golf carts, scooters, ATVs, or any vehicle rentals in Punta Cana / DR
4. relevance: How useful would it be for a LOCAL Punta Cana expert to reply? (1-5)
   - 5 = directly about PC real estate, buying, renting, investing
   - 4 = about living in PC/DR — neighborhoods, costs, safety, schools, visa, travel tips
   - 3 = general DR life — restaurants, car rentals, passport/entry requirements, healthcare, travel tips
   - 2 = tangentially related — the expert could add useful local context or build community trust
   - 1 = completely unrelated to DR/PC (e.g., US politics, memes about other countries)

Be VERY GENEROUS with is_question — if someone could benefit from ANY kind of helpful reply from a local, mark it true.
Be GENEROUS with relevance — if a local Punta Cana person could give a useful answer, it's at LEAST a 2. Questions about travel to DR, passport requirements, restaurants, activities, weather, etc. are ALL relevant (3+). Only mark 1 for posts that have NOTHING to do with DR/PC life.

IMPORTANT: Ignore garbled/encoded text at the start of posts — focus on the actual readable content."""

CLASSIFY_PROMPT = """Classify these Facebook group posts. For each, determine if someone could benefit from a helpful reply (is_question), the language, topic, and relevance (1-5) for a LOCAL Punta Cana expert.

Remember: travel questions, passport questions, restaurant recs, activity suggestions, moving advice — these are ALL relevant (3+). Only score 1 if it has NOTHING to do with DR/PC.

Posts:
{posts_json}

Return a JSON array with one object per post, in the same order:
[
  {{
    "post_id": "...",
    "is_question": true/false,
    "language": "en|es|fr|other",
    "topic": "cost_of_living|neighborhoods|buying_process|rental_income|visa_residency|lifestyle|schools|safety|healthcare|restaurants_food|travel_tips|construction_renovation|legal|car_rentals|other",
    "relevance": 1-5
  }}
]

Return ONLY the JSON array, no other text."""

REPLY_SYSTEM_PROMPT = """You are helping Ari write replies to Facebook group posts. Ari is a real estate and relocation professional based in Punta Cana, DR. He runs Rent & Go PC (rentandgopc.com).

TONE: Friendly professional. Think of a knowledgeable local expert who genuinely wants to help — approachable but credible. You're talking to someone you DON'T know personally, so keep it warm but respectful.

STYLE RULES:
- Write in the SAME LANGUAGE as the question
- Sound like a real person writing a helpful Facebook comment — not an AI, not a sales pitch, not a text to your best friend
- Use proper grammar and capitalization — you're a professional representing a business
- Use contractions naturally (don't, it's, you'll) but keep sentences well-formed
- Keep it conversational but polished — like how a good real estate agent would reply publicly
- DON'T use bullet points or numbered lists in FB comments
- DON'T use slang like "tbh", "btw", "imo", "ngl" — keep it clean
- DON'T start with "Great question!", "Hey!", "Yo!" or overly familiar greetings
- DON'T use "..." for dramatic pauses
- DO start naturally — jump into the answer or use a brief, relevant opener
- In Spanish: use "usted" for strangers, proper accents, professional but warm
- In French: use "vous" form for strangers, proper accents, professional tone
- NO hashtags. NO "DM me for more info". NO website links unless someone literally asks for help finding services
- 1 emoji MAX and only if it adds warmth (like 👋 in a welcome), most replies should have zero
- Length: 2-4 sentences. Concise, helpful, and to the point.
- If you can't genuinely help or add value, return null
- When you know the answer, be direct and confident — you live here

Punta Cana facts (use naturally when relevant, don't dump info):
- Cost of living: $1,500-3,000/month couple, $2,500-4,500 family of 4
- Rent: 1BR $500-800, 2BR $800-1,500, 3BR $1,200-2,500
- Buying: $180K-320K for 2BR condos, foreigners buy freely, no restrictions
- Airbnb income: $25K-35K/year on a $200-300K property
- Neighborhoods: Bavaro (beach/tourist), Cocotal (golf/quiet), Cap Cana (luxury), Downtown PC (local/affordable)
- Visa: 30 days free, residency via investment ($200K property) or income proof
- Safety: Tourist areas very safe, common sense like anywhere
- Healthcare: Private clinics good, insurance $50-150/month
- Schools: International schools $300-800/month
- Utilities: Electric $80-200/month (AC kills), water $15-30, internet $30-50"""

REPLY_PROMPT = """Write a reply to this Facebook group post as Ari. The post is in {language} — reply in the SAME language.

Group: {group_name}
Author: {author}
Post: {text}

Return valid JSON:
{{
  "text": "your reply here",
  "tone": "helpful_expert"
}}

If you genuinely can't help with this question, return: {{"text": null, "tone": null}}

Return ONLY the JSON, no other text."""


# --- Utilities (same pattern as content_generator.py) ---

# --- Keyword-based question detection (FREE, no API calls) ---

def detect_question_keywords(text: str, language: str = None) -> bool:
    """Detect if a post is a question using regex/keyword matching.

    Designed to be GENEROUS — better to have false positives (filtered later
    by Haiku relevance scoring) than miss real questions.

    Supports English, Spanish, and French. If language is None, checks all three.
    Returns True if the text looks like a question or information request.
    """
    if not text or len(text.strip()) < 10:
        return False

    t = text.strip()
    t_lower = t.lower()

    # --- Junk/meta text filter ---
    # Facebook placeholder text for deleted/restricted posts
    junk_phrases = [
        "when this happens, it's usually because the owner",
        "when this happens, it is usually because the owner",
        "commenting has been turned off",
        "this content isn't available",
        "see original",  # translation widget text
    ]
    if any(jp in t_lower for jp in junk_phrases):
        return False

    # --- Ad/listing signals (reduce false positives) ---
    ad_signals = [
        r'\bfor sale\b', r'\bfor rent\b', r'\bse vende\b', r'\bse alquila\b',
        r'\ben venta\b', r'\ben renta\b', r'\ben alquiler\b',
        r'\bà vendre\b', r'\bà louer\b',
        r'\bwhatsapp\s*\+?\d', r'\bcontact\s*:?\s*\+?\d',
        r'\bdm for\b', r'\bmessage for\b', r'\bcall\s+\d',
        r'\b(?:usd|dop|eur|us\$)\s*[\d,]+', r'\$\s*[\d,]+',
        r'\bprice\s*:', r'\bprecio\s*:', r'\bprix\s*:',
        r'\bapartamento\b', r'\bcondo\b', r'\bvilla\b',
        r'\b(?:property|maintenance|cleaning)\s+(?:management|service)\b',
        r'\bhire us\b', r'\bnuestros servicios\b', r'\bnos services\b',
        r'\bubicaci[oó]n\s*:', r'\blocation\s*:',
    ]

    # --- Service-offering / promotional signals ---
    # These catch ads disguised as questions (rhetorical "?" followed by "I help you")
    service_signals = [
        # English service offerings
        r'\bi (?:can |will )?help you\b', r'\bwe (?:can |will )?help you\b',
        r'\bi accompany you\b', r'\bwe accompany you\b',
        r'\bcontact me\b', r'\bdm me\b', r'\bmessage me\b', r'\breach out\b',
        r'\bwe offer\b', r'\bi offer\b', r'\bour services\b', r'\bmy services\b',
        r'\bbook now\b', r'\bbook today\b', r'\bget in touch\b',
        r'\bfree consultation\b', r'\bfree estimate\b', r'\bfree quote\b',
        r'\bschedule (?:a |your )', r'\blet me help\b',
        r'\b(?:full|complete|end.to.end|a.to.z|turnkey)\s+(?:service|management|solution)\b',
        # French service offerings
        r'\bje vous accompagne\b', r'\bnous vous accompagnons\b',
        r'\bcontactez[- ](?:moi|nous)\b', r'\b[eé]crivez[- ](?:moi|nous)\b',
        r'\bmise en valeur\b', r'\banalyse du potentiel\b',
        r'\bprise en charge\b', r'\bde a [àa] z\b',
        r'\bnos services\b', r'\bje propose\b', r'\bnous proposons\b',
        r'\br[eé]servez\b', r'\bappellez[- ](?:moi|nous)\b',
        r'\bgestion (?:locative|compl[eè]te|de (?:votre|vos))\b',
        # Spanish service offerings
        r'\bte (?:ayudo|acompa[nñ]o)\b', r'\ble (?:ayudo|ayudamos)\b',
        r'\bcont[aá]ctame\b', r'\bcont[aá]ctenos\b', r'\bescr[ií]beme\b',
        r'\bofrecemos\b', r'\bofrezco\b', r'\bnuestro servicio\b',
        r'\breserva ahora\b', r'\bagenda tu\b', r'\bllama ahora\b',
        r'\bconsulta gratis\b', r'\bcotizaci[oó]n gratis\b',
        r'\bde la a a la z\b', r'\bservicio (?:completo|integral|llave en mano)\b',
    ]

    ad_score = sum(1 for p in ad_signals if re.search(p, t_lower))
    service_score = sum(1 for p in service_signals if re.search(p, t_lower))
    # 2+ ad signals = probably an ad, OR 1+ service offering signal = promotional
    is_likely_ad = ad_score >= 2 or service_score >= 1

    # --- Universal signals ---

    # Contains question mark (very strong signal)
    if "?" in t:
        # If it's clearly an ad with a rhetorical question, skip
        if is_likely_ad:
            pass  # Don't return True — let other patterns decide
        else:
            return True

    # Contains inverted question mark (Spanish) — but not in ads
    if "¿" in t and not is_likely_ad:
        return True

    # --- English patterns ---
    if language is None or language == "en":
        # Question words at start of sentence (or after common prefixes)
        # Use \b after each word to avoid matching "whatsapp" for "what", etc.
        en_q_starts = r'(?:^|[.!]\s+)(?:who\b|what\b|where\b|when\b|why\b|how\b|which\b|whose\b|whom\b|is it\b|are there\b|can i\b|can you\b|can we\b|can someone\b|should i\b|would you\b|could someone\b|do you\b|does anyone\b|did anyone\b|will it\b|has anyone\b|have you\b|have any\b)'
        if re.search(en_q_starts, t_lower):
            return True

        # Information-seeking phrases (anywhere in text)
        en_seeking = [
            r'\banyone know\b', r'\banybody know\b', r'\banyone recommend\b',
            r'\banyone suggest\b', r'\bany suggestions\b', r'\bany recommendations\b',
            r'\bany advice\b', r'\bany tips\b', r'\bany idea\b', r'\bany thoughts\b',
            r'\bany experience\b', r'\banyone been\b', r'\banyone tried\b',
            r'\banyone have\b', r'\banyone here\b', r'\banyone else\b',
            r'\bhas anyone\b', r'\bhave anyone\b', r'\bdoes anyone\b',
            r'\bdo you guys\b', r'\bdo y\'?all\b',
            r'\blooking for\b', r'\bsearching for\b', r'\bin search of\b',
            r'\bneed help\b', r'\bneed advice\b', r'\bneed recommendations\b',
            r'\bneed suggestions\b', r'\bneed a\b.*\brecommend',
            r'\bhelp me\b', r'\bcan.{0,15}help\b',
            r'\bwhat.{0,10}best\b', r'\bwhat.{0,10}recommend\b',
            r'\bwhere.{0,10}find\b', r'\bwhere.{0,10}get\b', r'\bwhere.{0,10}buy\b',
            r'\bhow much\b', r'\bhow long\b', r'\bhow far\b', r'\bhow do\b',
            r'\bis it safe\b', r'\bis it worth\b', r'\bis it true\b',
            r'\bis there a\b', r'\bare there\b',
            r'\bthoughts on\b', r'\bopinions on\b', r'\bexperience with\b',
            r'\bwhat do you think\b', r'\bwhat should\b', r'\bwhat would\b',
            r'\bwhat is the\b', r'\bwhat are the\b',
            r'\bshould i\b', r'\bwould you\b', r'\bcould someone\b',
            r'\bi\'m wondering\b', r'\bwondering if\b', r'\bjust wondering\b',
            r'\bi want to know\b', r'\bi\'d like to know\b',
            r'\btrying to find\b', r'\btrying to figure\b',
            r'\bworth it\b', r'\bgood idea\b',
            r'\bfirst time\b.*\b(?:visit|go|travel|trip)\b',
            r'\bplanning (?:a |to )', r'\btraveling to\b', r'\bvisiting\b.*\b(?:first|soon|next)\b',
            r'\bmoving to\b', r'\brelocating\b', r'\bthinking (?:of|about) moving\b',
            r'\bpros and cons\b', r'\badvantages\b.*\bdisadvantages\b',
            r'\bcompare\b', r'\bcomparison\b', r'\bvs\.?\b',
            r'\bwhat.{0,5}cost\b', r'\bhow.{0,5}expensive\b',
        ]
        if any(re.search(p, t_lower) for p in en_seeking):
            return True

    # --- Spanish patterns ---
    if language is None or language == "es":
        es_q_starts = r'(?:^|[.!]\s+)(?:qui[eé]n|qu[eé]|cu[aá]l|cu[aá]nto|cu[aá]ndo|d[oó]nde|c[oó]mo|por qu[eé]|es posible|se puede|hay alg[uú]n|existe|saben|alguien|alguno)'
        if re.search(es_q_starts, t_lower):
            return True

        es_seeking = [
            r'\balguien sabe\b', r'\balguien conoce\b', r'\balguien recomienda\b',
            r'\balguien ha\b', r'\balguien que\b', r'\balguien me\b',
            r'\balguien puede\b', r'\balguien podr[ií]a\b',
            r'\bquisiera (?:saber|preguntar|conocer)\b',
            r'\balguna recomendaci[oó]n\b', r'\balguna sugerencia\b',
            r'\balg[uú]n consejo\b', r'\balg[uú]n tip\b',
            r'\bbusco\b', r'\bbuscando\b', r'\bnecesito\b',
            r'\bme pueden\b', r'\bme podr[ií]an\b', r'\bme ayudan\b',
            r'\bd[oó]nde (?:puedo|consigo|encuentro|queda|hay)\b',
            r'\bcu[aá]nto (?:cuesta|vale|sale|cobran|pagan)\b',
            r'\bqu[eé] (?:tal|opinan|recomiendan|sugieren|piensan)\b',
            r'\bqu[eé] es mejor\b', r'\bcu[aá]l es mejor\b',
            r'\bes seguro\b', r'\bes verdad\b', r'\bes cierto\b',
            r'\bvale la pena\b', r'\bconviene\b',
            r'\bprimera vez\b', r'\bprimer viaje\b',
            r'\bme mudar[eé]\b', r'\bmudarme\b', r'\bmudan\b',
            r'\binfo sobre\b', r'\binformaci[oó]n sobre\b',
            r'\bconoce[ns]?\b.*\b(?:buen|lugar|sitio|doctor|abogado)\b',
            r'\bsaben de\b', r'\bsabe alguien\b',
            r'\brecomiend[ae]n\b', r'\bsugi[eé]r[ae]n\b',
            r'\bayuda\b.*\bpor favor\b', r'\bpor favor\b.*\bayuda\b',
            r'\bqu[eé] necesito\b', r'\bqu[eé] debo\b',
        ]
        if any(re.search(p, t_lower) for p in es_seeking):
            return True

    # --- French patterns ---
    if language is None or language == "fr":
        fr_q_starts = r'(?:^|[.!]\s+)(?:qui\b|que\b |quel\b|quelle\b|quoi\b|où\b|quand\b|comment\b|pourquoi\b|combien\b|est-ce que\b|y a-t-il|savez\b|connaissez\b|quelqu)'
        if re.search(fr_q_starts, t_lower):
            return True

        fr_seeking = [
            r'\bquelqu.un (?:sait|conna[iî]t|recommande|a d[eé]j[aà])\b',
            r'\bquelqu.un peut\b', r'\bquelqu.un qui\b',
            r'\bdes recommandations\b', r'\bdes suggestions\b',
            r'\bdes conseils\b', r'\bun conseil\b',
            r'\bcherche\b', r'\bje cherche\b', r'\ben recherche\b',
            r'\bbesoin de\b', r'\bj.ai besoin\b',
            r'\bo[uù] (?:trouver|acheter|aller|est|sont)\b',
            r'\bcombien (?:co[uû]te|vaut|faut)\b',
            r'\bcomment (?:faire|trouver|aller)\b',
            r'\best-ce (?:que|qu\')\b',
            r'\bc.est s[uû]r\b', r'\bc.est vrai\b',
            r'\bvaut la peine\b', r'\bvaut le coup\b',
            r'\bpremi[eè]re fois\b', r'\bpremier voyage\b',
            r'\bd[eé]m[eé]nager\b',
            r'\bconnaissez.vous\b', r'\bsavez.vous\b',
            r'\bvous recommandez\b', r'\bvous sugg[eé]rez\b',
            r'\bts[eé]\b.*\b(?:bon|place|trouver)\b',  # Quebec informal
            r'\bavez.vous\b', r'\bpouvez.vous\b',
            r'\bqu.en pensez\b', r'\bvotre avis\b', r'\bvos exp[eé]riences\b',
            r'\baide\b.*\bsvp\b', r'\bsvp\b.*\baide\b',
        ]
        if any(re.search(p, t_lower) for p in fr_seeking):
            return True

    return False


def calc_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * COST_PER_MTOK_INPUT / 1_000_000) + \
           (output_tokens * COST_PER_MTOK_OUTPUT / 1_000_000)


def load_json(path: Path, default=None):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_today_spend(usage_log: list) -> float:
    today = date.today().isoformat()
    return sum(e["cost_usd"] for e in usage_log if e["date"] == today)


def log_usage(usage_log: list, task: str, input_tokens: int, output_tokens: int) -> list:
    cost = calc_cost(input_tokens, output_tokens)
    today_spend = get_today_spend(usage_log)
    entry = {
        "date": date.today().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "task": task,
        "model": MODEL,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        "daily_total_usd": round(today_spend + cost, 6),
    }
    usage_log.append(entry)
    save_json(USAGE_FILE, usage_log)
    return usage_log


def parse_json_response(text: str):
    """Extract JSON from response, handling markdown code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  Failed to parse JSON: {e}")
        return None


def budget_check(usage_log: list) -> bool:
    """Return True if within budget."""
    today_spend = get_today_spend(usage_log)
    if today_spend >= DAILY_BUDGET:
        print(f"  Budget cap reached: ${today_spend:.4f} >= ${DAILY_BUDGET}")
        return False
    return True


# --- Core pipeline ---

def classify_posts(client, posts: list, usage_log: list) -> tuple[list, list]:
    """Classify posts in batches. Returns (classifications, updated_usage_log)."""
    all_classifications = []

    for i in range(0, len(posts), CLASSIFY_BATCH_SIZE):
        if not budget_check(usage_log):
            break

        batch = posts[i:i + CLASSIFY_BATCH_SIZE]
        batch_summary = [
            {"post_id": p["id"], "text": p["text"][:800], "author": p.get("author", "")}
            for p in batch
        ]

        prompt = CLASSIFY_PROMPT.format(posts_json=json.dumps(batch_summary, ensure_ascii=False))

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=CLASSIFY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            print(f"  API error classifying batch {i // CLASSIFY_BATCH_SIZE + 1}: {e}")
            continue

        usage_log = log_usage(
            usage_log, "classify",
            response.usage.input_tokens, response.usage.output_tokens,
        )
        cost = calc_cost(response.usage.input_tokens, response.usage.output_tokens)
        print(f"  Batch {i // CLASSIFY_BATCH_SIZE + 1}: {len(batch)} posts — ${cost:.4f}")

        if not response.content or not hasattr(response.content[0], "text"):
            print(f"  Empty response for batch {i // CLASSIFY_BATCH_SIZE + 1}")
            continue

        parsed = parse_json_response(response.content[0].text)
        if parsed and isinstance(parsed, list):
            all_classifications.extend(parsed)
        else:
            print(f"  Failed to parse batch {i // CLASSIFY_BATCH_SIZE + 1} response")

    return all_classifications, usage_log


def generate_reply(client, question: dict, usage_log: list) -> tuple[dict | None, list]:
    """Generate a reply for a single question. Returns (reply_dict, updated_usage_log)."""
    if not budget_check(usage_log):
        return None, usage_log

    lang_map = {"en": "English", "es": "Spanish", "fr": "French"}
    language = lang_map.get(question["language"], question["language"])

    prompt = REPLY_PROMPT.format(
        language=language,
        group_name=question["group_name"],
        author=question["author"],
        text=question["text"],
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=REPLY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        print(f"  API error generating reply for {question['id']}: {e}")
        return None, usage_log

    usage_log = log_usage(
        usage_log, "reply",
        response.usage.input_tokens, response.usage.output_tokens,
    )
    cost = calc_cost(response.usage.input_tokens, response.usage.output_tokens)
    print(f"  Reply for {question['id']} — ${cost:.4f}")

    if not response.content or not hasattr(response.content[0], "text"):
        print(f"  Empty response for {question['id']}")
        return None, usage_log

    parsed = parse_json_response(response.content[0].text)
    if parsed and parsed.get("text"):
        return {
            "text": parsed["text"],
            "tone": parsed.get("tone", "helpful_expert"),
            "generated_at": datetime.now().isoformat(),
        }, usage_log

    return None, usage_log


def merge_questions(existing_data: dict, new_questions: list) -> dict:
    """Merge new questions into existing data, preserving acted-upon items and pending items with replies."""
    existing_questions = existing_data.get("questions", [])

    merged = []
    seen_ids = set()

    # Use question ID as the dedup key (not post_url, which may be empty)
    def dedup_key(q):
        return q.get("id") or q.get("post_url") or q.get("text", "")[:200]

    # Keep existing non-pending items first (answered, skipped, posted, etc.)
    for q in existing_questions:
        if q.get("status") != "pending":
            key = dedup_key(q)
            merged.append(q)
            seen_ids.add(key)

    # Keep existing pending items that already have replies generated
    for q in existing_questions:
        if q.get("status") == "pending" and q.get("reply"):
            key = dedup_key(q)
            if key not in seen_ids:
                merged.append(q)
                seen_ids.add(key)

    # Add new questions (skip duplicates)
    for q in new_questions:
        key = dedup_key(q)
        if key not in seen_ids:
            merged.append(q)
            seen_ids.add(key)

    # Re-add remaining existing pending items (no reply yet, not replaced by new)
    for q in existing_questions:
        if q.get("status") == "pending":
            key = dedup_key(q)
            if key not in seen_ids:
                merged.append(q)
                seen_ids.add(key)

    # Collect unique groups
    groups_map = {}
    for q in merged:
        gid = q.get("group_id")
        if gid and gid not in groups_map:
            groups_map[gid] = {
                "id": gid,
                "name": q.get("group_name", ""),
                "url": f"https://facebook.com/groups/{gid}",
            }

    return {
        "last_scan": datetime.now().isoformat(),
        "groups": list(groups_map.values()),
        "questions": merged,
    }


def run_pipeline(client, classify_only: bool, usage_log: list) -> list:
    """Full pipeline: load posts, classify, generate replies, merge."""
    raw_data = load_json(RAW_POSTS_FILE)
    if not raw_data or not raw_data.get("posts"):
        print("No posts found in group-raw-posts.json")
        return usage_log

    posts = raw_data["posts"]

    # Filter out garbled/junk posts before classification to save API budget
    def is_readable(text):
        if not text or len(text) < 20:
            return False
        # Count actual readable characters vs total
        readable = sum(1 for c in text if c.isalpha() or c.isspace() or c in '.,!?¿¡\'"-:;()@#$%&')
        ratio = readable / len(text) if text else 0
        return ratio > 0.6  # at least 60% readable characters

    original_count = len(posts)
    posts = [p for p in posts if is_readable(p.get("text", ""))]
    if len(posts) < original_count:
        print(f"Filtered {original_count - len(posts)} garbled/junk posts ({len(posts)} remaining)")

    # Step 0: Keyword pre-filter (FREE — no API calls)
    # Only send likely-questions to Haiku for classification + relevance scoring
    keyword_questions = [p for p in posts if detect_question_keywords(p.get("text", ""))]
    keyword_skipped = len(posts) - len(keyword_questions)
    print(f"Keyword pre-filter: {len(keyword_questions)} likely questions, {keyword_skipped} non-questions skipped (FREE)")

    if not keyword_questions:
        print("No questions detected by keyword filter. Skipping API calls.")
        questions = []
    else:
        print(f"Classifying {len(keyword_questions)} posts via Haiku...")

        # Step 1: Classify only the keyword-detected questions
        classifications, usage_log = classify_posts(client, keyword_questions, usage_log)

        # Build lookup
        class_by_id = {c["post_id"]: c for c in classifications if isinstance(c, dict)}

        # Filter questions with relevance >= 2
        questions = []
        for post in keyword_questions:
            cls = class_by_id.get(post["id"])
            if not cls:
                continue
            if not cls.get("is_question"):
                continue
            if cls.get("relevance", 0) < 2:
                continue

            questions.append({
                "id": f"q_{post['id']}",
                "group_id": post.get("group_id", ""),
                "group_name": post.get("group_name", ""),
                "post_url": post.get("post_url", ""),
                "author": post.get("author", ""),
                "text": post.get("text", ""),
                "language": cls.get("language", "en"),
                "topic": cls.get("topic", "other"),
                "relevance": cls.get("relevance", 3),
                "detected_at": datetime.now().isoformat(),
                "reply": None,
                "status": "pending",
            })

    print(f"Found {len(questions)} questions (relevance >= 2)")

    if classify_only:
        print("--classify-only: skipping reply generation")
    else:
        # Step 2: Generate replies
        print(f"Generating replies...")
        for q in questions:
            reply, usage_log = generate_reply(client, q, usage_log)
            if reply:
                q["reply"] = reply

        replied = sum(1 for q in questions if q["reply"])
        print(f"Generated {replied}/{len(questions)} replies")

    # Step 3: Merge
    existing_data = load_json(QUESTIONS_FILE, {})
    merged = merge_questions(existing_data, questions)
    save_json(QUESTIONS_FILE, merged)

    total_qs = len(merged["questions"])
    pending = sum(1 for q in merged["questions"] if q.get("status") == "pending")
    print(f"Saved {total_qs} questions ({pending} pending) to group-questions.json")

    return usage_log


def show_status():
    """Show stats from existing data."""
    questions_data = load_json(QUESTIONS_FILE, {})
    usage_log = load_json(USAGE_FILE, [])

    questions = questions_data.get("questions", [])
    groups = questions_data.get("groups", [])

    if not questions:
        print("No questions found. Run the pipeline first or use --demo.")
        return

    # Counts by status
    status_counts = {}
    for q in questions:
        s = q.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    # Counts by topic
    topic_counts = {}
    for q in questions:
        t = q.get("topic", "other")
        topic_counts[t] = topic_counts.get(t, 0) + 1

    # Counts by language
    lang_counts = {}
    for q in questions:
        lang = q.get("language", "?")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    with_replies = sum(1 for q in questions if q.get("reply"))

    print(f"Groups: {len(groups)}")
    print(f"Total questions: {len(questions)}")
    print(f"With replies: {with_replies}")
    print()

    print("By status:")
    for s, c in sorted(status_counts.items()):
        print(f"  {s}: {c}")
    print()

    print("By topic:")
    for t, c in sorted(topic_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")
    print()

    print("By language:")
    for lang, c in sorted(lang_counts.items(), key=lambda x: -x[1]):
        print(f"  {lang}: {c}")
    print()

    today_spend = get_today_spend(usage_log)
    total_spend = sum(e.get("cost_usd", 0) for e in usage_log)
    print(f"Budget: ${today_spend:.4f} today / ${DAILY_BUDGET} limit")
    print(f"Total spend (all time): ${total_spend:.4f}")


def generate_demo():
    """Generate realistic demo data for dashboard testing."""
    now = datetime.now().isoformat()

    # Use real group names/IDs from group-assist-config.json
    demo_questions = [
        {
            "id": "q_post_demo_001",
            "group_id": "312506675935209",
            "group_name": "Punta Cana Expats",
            "post_url": "https://facebook.com/groups/312506675935209/posts/demo_001",
            "author": "Maria Rodriguez",
            "text": "Hola! Alguien sabe cuanto cuesta vivir en Punta Cana con una familia de 4? Gastos mensuales aproximados incluyendo colegio para los ninos?",
            "language": "es",
            "topic": "cost_of_living",
            "relevance": 5,
            "detected_at": now,
            "reply": {
                "text": "Hola Maria! mira depende mucho de la zona pero para una familia de 4 en Bavaro yo diria entre $2,500-4,000/mes. Alquiler de un 2-3BR anda por $1,200-2,000, colegio internacional entre $300-800 por nino y super como $400-600. Lo que mas te va a sorprender es la luz — el AC te puede llegar a $150-200/mes jaja. Pero honestamente se vive bien con ese presupuesto",
                "tone": "helpful_expert",
                "generated_at": now,
            },
            "status": "pending",
        },
        {
            "id": "q_post_demo_002",
            "group_id": "878923082826821",
            "group_name": "Real Estate Dominican Republic",
            "post_url": "https://facebook.com/groups/878923082826821/posts/demo_002",
            "author": "James Thompson",
            "text": "Can a foreigner buy property in the DR without restrictions? Do I need a local partner or lawyer? Looking at condos near Bavaro Beach.",
            "language": "en",
            "topic": "buying_process",
            "relevance": 5,
            "detected_at": now,
            "reply": {
                "text": "Yeah foreigners can buy with zero restrictions here, same rights as locals. No partner needed. You'll want a good lawyer though — budget like $1,500-3,000 for closing costs total. Bavaro 2BR condos go from $180K-320K depending on the development. The process is honestly pretty straightforward compared to other countries",
                "tone": "helpful_expert",
                "generated_at": now,
            },
            "status": "pending",
        },
        {
            "id": "q_post_demo_003",
            "group_id": "3474701412856852",
            "group_name": "Quebecois a Punta Cana, Republique Dominicaine",
            "post_url": "https://facebook.com/groups/3474701412856852/posts/demo_003",
            "author": "Sophie Tremblay",
            "text": "Bonjour! On pense demenager a Punta Cana depuis Montreal. C'est quoi les quartiers les plus recommandes pour une famille avec enfants? On cherche quelque chose de tranquille mais pas trop loin de la plage.",
            "language": "fr",
            "topic": "neighborhoods",
            "relevance": 5,
            "detected_at": now,
            "reply": {
                "text": "Salut Sophie! honnetement pour une famille je te dirais Cocotal — c'est ferme, tranquille, y'a le golf et les piscines pis t'es a 10 min de la plage. Bavaro c'est plus anime mais un peu touristique. Cap Cana si le budget le permet mais c'est le haut de gamme. Depuis Montreal c'est 4h30 direct avec Sunwing faque c'est super accessible. Si vous venez visiter je peux vous faire un tour des quartiers",
                "tone": "helpful_expert",
                "generated_at": now,
            },
            "status": "pending",
        },
        {
            "id": "q_post_demo_004",
            "group_id": "587885753186026",
            "group_name": "Punta Cana Airbnb (owners/renters)",
            "post_url": "https://facebook.com/groups/587885753186026/posts/demo_004",
            "author": "Robert Chen",
            "text": "What kind of Airbnb income can I realistically expect from a 2BR condo in Punta Cana? Thinking of buying for investment but want real numbers, not sales pitches.",
            "language": "en",
            "topic": "rental_income",
            "relevance": 5,
            "detected_at": now,
            "reply": {
                "text": "So real talk — a 2BR condo ($200-300K) typically does $25K-35K/year gross on Airbnb. Nightly rates $120-180 depending on season, occupancy around 65-80%. After management fees, maintenance, HOA etc you're looking at 8-12% net. Dec-April is peak, summer slower but DR gets tourism year round so its not dead. Biggest factors are location and how good your listing photos are tbh",
                "tone": "helpful_expert",
                "generated_at": now,
            },
            "status": "pending",
        },
        {
            "id": "q_post_demo_005",
            "group_id": "339282416279056",
            "group_name": "Expats Punta Cana / Bavaro",
            "post_url": "https://facebook.com/groups/339282416279056/posts/demo_005",
            "author": "Laura Gomez",
            "text": "Que tan seguro es Punta Cana para vivir? Sobre todo para una mujer sola. He escuchado cosas buenas y malas, me gustaria opiniones de gente que vive alli.",
            "language": "es",
            "topic": "safety",
            "relevance": 4,
            "detected_at": now,
            "reply": {
                "text": "Hola Laura, mira las zonas turisticas (Bavaro, Cocotal, Cap Cana) son bastante seguras. Conozco varias mujeres que viven solas aqui sin ningun problema. Sentido comun como en cualquier lado — no ostentes, evita zonas solas de noche etc. Los complejos cerrados con seguridad 24/7 son lo mas tranquilo. Yo te recomendaria venir unas semanas primero y sentir el ambiente tu misma antes de decidir",
                "tone": "helpful_expert",
                "generated_at": now,
            },
            "status": "pending",
        },
        {
            "id": "q_post_demo_006",
            "group_id": "CanadiansLivingInDominicanRepublic",
            "group_name": "Canadians Living in the Dominican Republic",
            "post_url": "https://facebook.com/groups/CanadiansLivingInDominicanRepublic/posts/demo_006",
            "author": "Mike Patterson",
            "text": "Anyone know the process for getting residency in the DR? I'm a US citizen, retired, looking to make the move permanent. What visa do I need?",
            "language": "en",
            "topic": "visa_residency",
            "relevance": 4,
            "detected_at": now,
            "reply": {
                "text": "Hey Mike so the easiest route for retirees is the Pensionado visa — you just need to show $1,500/month in pension income. Takes like 2-4 months and around $1,000-1,500 total. If you buy property $200K+ theres also an investment residency option. You can enter visa-free for 30 days to start (extendable to 120 for $50). Get a local immigration lawyer in Bavaro, the bureaucracy is slow but doable",
                "tone": "helpful_expert",
                "generated_at": now,
            },
            "status": "pending",
        },
        {
            "id": "q_post_demo_007",
            "group_id": "604142596286067",
            "group_name": "Expats living in The Dominican Republic",
            "post_url": "https://facebook.com/groups/604142596286067/posts/demo_007",
            "author": "Ana Petrova",
            "text": "Looking for international schools in Punta Cana area for my 8 year old. What are the options and roughly how much do they cost? We speak English and Spanish.",
            "language": "en",
            "topic": "schools",
            "relevance": 4,
            "detected_at": now,
            "reply": {
                "text": "Ana theres a few good ones in Bavaro area, they run $300-800/month depending on the school. Most are bilingual english/spanish so thats perfect for you guys. Class sizes tend to be smaller which is nice. I'd say visit 2-3 when you're here cause the vibe is pretty different between them. If you want specific names let me know",
                "tone": "helpful_expert",
                "generated_at": now,
            },
            "status": "pending",
        },
        {
            "id": "q_post_demo_008",
            "group_id": "1502081570566337",
            "group_name": "Dominican Expats Buy, Sell or Rent",
            "post_url": "https://facebook.com/groups/1502081570566337/posts/demo_008",
            "author": "Carlos Mendez",
            "text": "Estoy comparando invertir en Punta Cana vs Cancun. Que ventajas tiene RD sobre Mexico para bienes raices? Alguien ha invertido en ambos?",
            "language": "es",
            "topic": "buying_process",
            "relevance": 5,
            "detected_at": now,
            "reply": {
                "text": "Buena pregunta Carlos. Mira la ventaja grande de RD es que extranjeros compran con 100% propiedad directa — en Mexico necesitas fideicomiso en zona costera que es un rollo. Precios mas bajos tambien, un 2BR aqui empieza en $180K vs $250K+ en zonas comparables de Cancun. Retorno Airbnb anda por 8-12% neto. Mexico tiene mejor infraestructura en algunas zonas eso si, pero en relacion precio-rendimiento PC esta dificil de superar ahorita",
                "tone": "helpful_expert",
                "generated_at": now,
            },
            "status": "pending",
        },
        {
            "id": "q_post_demo_009",
            "group_id": "CocotalGolfandCountryClub",
            "group_name": "Gente que vive en Cocotal",
            "post_url": "https://facebook.com/groups/CocotalGolfandCountryClub/posts/demo_009",
            "author": "Jennifer Walsh",
            "text": "How reliable is the electricity in Punta Cana? I work remotely and need stable internet and power. Are there a lot of outages?",
            "language": "en",
            "topic": "utilities",
            "relevance": 4,
            "detected_at": now,
            "reply": {
                "text": "Honestly the public grid has outages yeah but most modern condos have backup generators that kick in automatically so you barely notice. Internet is solid — fiber optic in most Bavaro developments, I get 100+ Mbps for like $40/month. Keep a mobile hotspot as backup just in case and you're good. I work remote from here daily and rarely have issues in the main developments. Electric bill is $80-200/month tho, AC is the killer",
                "tone": "helpful_expert",
                "generated_at": now,
            },
            "status": "pending",
        },
        {
            "id": "q_post_demo_010",
            "group_id": "264786824583749",
            "group_name": "Punta Cana Travel",
            "post_url": "https://facebook.com/groups/264786824583749/posts/demo_010",
            "author": "David Kim",
            "text": "What's the healthcare situation like in Punta Cana? Are there good hospitals nearby? How much does health insurance cost?",
            "language": "en",
            "topic": "healthcare",
            "relevance": 4,
            "detected_at": now,
            "reply": {
                "text": "Healthcare has gotten way better here. Theres a few good private clinics in Bavaro — Centro Medico Punta Cana and Hospiten are the main ones, they handle most stuff. For anything serious Santo Domingo is 2hrs and has legit hospitals. Insurance runs $50-150/month depending on age. Even without insurance a doctor visit is like $30-50 so its pretty affordable. Dental is crazy cheap too compared to the US btw",
                "tone": "helpful_expert",
                "generated_at": now,
            },
            "status": "pending",
        },
    ]

    groups = [
        {"id": "312506675935209", "name": "Punta Cana Expats", "url": "https://facebook.com/groups/312506675935209"},
        {"id": "878923082826821", "name": "Real Estate Dominican Republic", "url": "https://facebook.com/groups/878923082826821"},
        {"id": "3474701412856852", "name": "Quebecois a Punta Cana, Republique Dominicaine", "url": "https://facebook.com/groups/3474701412856852"},
        {"id": "587885753186026", "name": "Punta Cana Airbnb (owners/renters)", "url": "https://facebook.com/groups/587885753186026"},
        {"id": "339282416279056", "name": "Expats Punta Cana / Bavaro", "url": "https://facebook.com/groups/339282416279056"},
        {"id": "CanadiansLivingInDominicanRepublic", "name": "Canadians Living in the Dominican Republic", "url": "https://facebook.com/groups/CanadiansLivingInDominicanRepublic"},
        {"id": "604142596286067", "name": "Expats living in The Dominican Republic", "url": "https://facebook.com/groups/604142596286067"},
        {"id": "1502081570566337", "name": "Dominican Expats Buy, Sell or Rent", "url": "https://facebook.com/groups/1502081570566337"},
        {"id": "CocotalGolfandCountryClub", "name": "Gente que vive en Cocotal", "url": "https://facebook.com/groups/CocotalGolfandCountryClub"},
        {"id": "264786824583749", "name": "Punta Cana Travel", "url": "https://facebook.com/groups/264786824583749"},
    ]

    data = {
        "last_scan": now,
        "groups": groups,
        "questions": demo_questions,
    }

    save_json(QUESTIONS_FILE, data)
    print(f"Generated {len(demo_questions)} demo questions across {len(groups)} groups")
    print(f"Saved to {QUESTIONS_FILE}")


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(description="Group Engagement Assistant")
    parser.add_argument("--classify-only", action="store_true", help="Classify posts without generating replies")
    parser.add_argument("--status", action="store_true", help="Show stats")
    parser.add_argument("--demo", action="store_true", help="Generate demo data for dashboard testing")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.status:
        show_status()
        return

    if args.demo:
        generate_demo()
        return

    # Full pipeline requires API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    usage_log = load_json(USAGE_FILE, [])
    today_spend = get_today_spend(usage_log)
    print(f"Daily budget: ${DAILY_BUDGET} — Spent today: ${today_spend:.4f}")

    if today_spend >= DAILY_BUDGET:
        print("Budget cap reached for today. Exiting.")
        return

    usage_log = run_pipeline(client, classify_only=args.classify_only, usage_log=usage_log)

    final_spend = get_today_spend(usage_log)
    print(f"\nDone. Daily spend: ${final_spend:.4f} / ${DAILY_BUDGET}")


if __name__ == "__main__":
    main()
