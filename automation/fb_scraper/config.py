"""
config.py — Configuration for FB group scraper.
Loads from config.json + environment variables.
Supports multi-account with per-account session files and proxies.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).parent / "config.json"
SESSIONS_DIR = Path(__file__).parent / "sessions"


@dataclass
class ProxyConfig:
    server: str
    username: Optional[str] = None
    password: Optional[str] = None


@dataclass
class AccountConfig:
    email: str
    password: str
    label: str = "burner"
    disabled: bool = False
    proxy: Optional[ProxyConfig] = None
    session_file: Optional[str] = None  # auto-set to sessions/<label>.json

    def get_session_path(self) -> Path:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        if self.session_file:
            return SESSIONS_DIR / self.session_file
        safe_label = re.sub(r'[^\w\-]', '_', self.label)
        return SESSIONS_DIR / f"{safe_label}.json"

    def has_session(self) -> bool:
        return self.get_session_path().exists()


@dataclass
class GroupConfig:
    url: str
    name: str
    group_id: Optional[str] = None
    max_scrolls: int = 50
    max_posts: int = 200


# Generic answers for group membership questions
JOIN_GROUP_ANSWERS = [
    "Looking to invest in Punta Cana real estate",
    "Interested in buying property in Punta Cana",
    "Searching for rental opportunities in Bavaro/Punta Cana area",
    "Real estate investor exploring the Dominican Republic market",
]


@dataclass
class ScraperConfig:
    accounts: list[AccountConfig] = field(default_factory=list)
    groups: list[GroupConfig] = field(default_factory=list)
    headless: bool = True
    viewport_width: int = 1366
    viewport_height: int = 768
    # Scroll timing — human-like
    scroll_delay_min: float = 2.0
    scroll_delay_max: float = 4.0
    # Between-group pauses
    between_groups_delay_min: float = 30.0
    between_groups_delay_max: float = 60.0
    max_posts_per_group: int = 200
    user_agents: list[str] = field(default_factory=lambda: [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    ])


def _parse_proxy(proxy_data) -> Optional[ProxyConfig]:
    """Parse proxy config from dict or string."""
    if not proxy_data:
        return None
    if isinstance(proxy_data, str):
        return ProxyConfig(server=proxy_data)
    return ProxyConfig(
        server=proxy_data["server"],
        username=proxy_data.get("username"),
        password=proxy_data.get("password"),
    )


def load_config() -> ScraperConfig:
    """Load config from config.json, override accounts with env vars."""
    cfg = ScraperConfig()

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            data = json.load(f)

        # Groups
        for g in data.get("groups", []):
            group_id = None
            url = g["url"]
            m = re.search(r'/groups/([^/?#]+)', url)
            if m:
                group_id = m.group(1)
            cfg.groups.append(GroupConfig(
                url=url,
                name=g.get("name", group_id or "unknown"),
                group_id=group_id,
                max_scrolls=g.get("max_scrolls", 50),
                max_posts=g.get("max_posts", 200),
            ))

        # Scraper settings
        cfg.headless = data.get("headless", True)
        cfg.viewport_width = data.get("viewport_width", 1366)
        cfg.viewport_height = data.get("viewport_height", 768)
        cfg.scroll_delay_min = data.get("scroll_delay_min", 2.0)
        cfg.scroll_delay_max = data.get("scroll_delay_max", 4.0)
        cfg.between_groups_delay_min = data.get("between_groups_delay_min", 30.0)
        cfg.between_groups_delay_max = data.get("between_groups_delay_max", 60.0)
        cfg.max_posts_per_group = data.get("max_posts_per_group", 200)

        if "user_agents" in data:
            cfg.user_agents = data["user_agents"]

        # Accounts from config.json (with proxy + session support)
        for acc in data.get("accounts", []):
            if acc.get("email") and acc.get("password"):
                cfg.accounts.append(AccountConfig(
                    email=acc["email"],
                    password=acc["password"],
                    label=acc.get("label", "config"),
                    disabled=acc.get("disabled", False),
                    proxy=_parse_proxy(acc.get("proxy")),
                    session_file=acc.get("session_file"),
                ))

    # Load accounts from env vars (override/supplement config.json)
    # Primary: FB_EMAIL, FB_PASSWORD, FB_PROXY
    primary_email = os.environ.get("FB_EMAIL")
    primary_pass = os.environ.get("FB_PASSWORD")
    if primary_email and primary_pass:
        if not any(a.email == primary_email for a in cfg.accounts):
            proxy = None
            proxy_env = os.environ.get("FB_PROXY")
            if proxy_env:
                proxy = ProxyConfig(server=proxy_env)
            cfg.accounts.append(AccountConfig(
                email=primary_email,
                password=primary_pass,
                label="primary",
                proxy=proxy,
            ))

    # Numbered: FB_EMAIL_1..9, FB_PASSWORD_1..9, FB_PROXY_1..9
    for i in range(1, 10):
        email = os.environ.get(f"FB_EMAIL_{i}")
        passwd = os.environ.get(f"FB_PASSWORD_{i}")
        if email and passwd:
            if not any(a.email == email for a in cfg.accounts):
                proxy = None
                proxy_env = os.environ.get(f"FB_PROXY_{i}")
                if proxy_env:
                    proxy = ProxyConfig(server=proxy_env)
                cfg.accounts.append(AccountConfig(
                    email=email,
                    password=passwd,
                    label=f"burner_{i}",
                    proxy=proxy,
                ))

    return cfg
