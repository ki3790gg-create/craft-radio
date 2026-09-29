from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    lookback_days: int = int(os.getenv("REPORT_LOOKBACK_DAYS", "7"))
    max_results_per_query: int = int(os.getenv("YOUTUBE_MAX_RESULTS_PER_QUERY", "25"))


# Reports older than this many days are deleted from the site.
RETENTION_DAYS = 28
MAX_REPORTS = 4

# Korea-focused: Korean search terms, searched with region KR / language ko,
# and results kept only if the title is Korean or the channel is registered in Korea.
SEARCH_TERMS = [
    "끈갈피 만들기",
    "비즈 소품 만들기",
    "뜨개 소품 만들기",
    "마크라메 만들기",
    "비즈 키링 만들기",
    "핸드메이드 소품 판매",
]
SEARCH_REGION = "KR"
SEARCH_LANGUAGE = "ko"
