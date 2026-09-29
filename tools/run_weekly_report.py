import argparse
import json
from datetime import datetime
from pathlib import Path

from config import ROOT, SEARCH_TERMS, SITE_DIR, Settings
from site_builder import DEFAULT_IDEAS, publish
from youtube_research import YouTubeResearch, analyze_records


def fixture_data() -> dict:
    records = [
        {
            "video_id": "dQw4w9WgXcQ",
            "title": "비즈 키링 만들기: 작은 선물용품 제작",
            "description": "비즈와 끈으로 만드는 키링",
            "channel_id": "channel-1",
            "channel_title": "Craft Studio",
            "channel_url": "https://www.youtube.com/channel/channel-1",
            "published_at": "2026-09-15T08:00:00Z",
            "view_count": 42000,
            "like_count": 1200,
            "comment_count": 90,
            "embeddable": True,
            "channel": {"subscriber_count": 850, "video_count": 20},
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        },
        {
            "video_id": "jNQXAC9IVRw",
            "title": "뜨개 파우치 하루 만에 완성하기",
            "description": "knitting pouch tutorial",
            "channel_id": "channel-2",
            "channel_title": "Knit Room",
            "channel_url": "https://www.youtube.com/channel/channel-2",
            "published_at": "2026-09-14T08:00:00Z",
            "view_count": 18000,
            "like_count": 900,
            "comment_count": 60,
            "embeddable": False,
            "channel": {"subscriber_count": 12000, "video_count": 80},
            "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        },
    ]
    return analyze_records(records)


def report_markdown(data: dict) -> str:
    lines = [
        f"# 주간 공예 사업 리포트 ({data['collected_at'][:10]})",
        "",
        f"수집 영상 수: {data['record_count']}",
        "",
        "## 아이템 관심 신호",
    ]
    lines.extend(f"- {item}: {count}건 언급" for item, count in data["item_signals"][:10])
    lines.append("\n## 주목할 채널")
    for channel in data["top_channels"]:
        channel_url = channel.get("channel_url") or f"https://www.youtube.com/channel/{channel['channel_title']}"
        lines.append(f"- [{channel['channel_title']}]({channel_url})")
    lines.append("\n## 추천 영상 5개")
    for video in data["popular_videos"]:
        rising_marker = " [급상승 후보]" if video in data["rising_small_channels"] else ""
        lines.append(
            f"- [{video['title']}]({video['url']}){rising_marker}"
        )
    lines.append("\n## 실행 아이디어")
    lines.extend(f"- {idea}" for idea in DEFAULT_IDEAS)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the weekly craft YouTube report")
    parser.add_argument("--dry-run", action="store_true", help="Use local fixture data and skip external APIs")
    parser.add_argument("--site-dir", type=Path, help="Where to build the website (dry run: .tmp/site)")
    args = parser.parse_args()
    settings = Settings()
    output_dir = ROOT / ".tmp"
    output_dir.mkdir(exist_ok=True)
    # Fake dry-run data must never land in the real site.
    site_dir = args.site_dir or (output_dir / "site" if args.dry_run else SITE_DIR)

    data = (
        fixture_data()
        if args.dry_run
        else YouTubeResearch(settings.youtube_api_key, settings.max_results_per_query).collect(
            SEARCH_TERMS, settings.lookback_days
        )
    )
    markdown = report_markdown(data)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"weekly_report_{stamp}.md"
    report_path.write_text(markdown, encoding="utf-8")
    (output_dir / f"weekly_report_{stamp}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    index, removed = publish(data, DEFAULT_IDEAS, site_dir)
    for path in removed:
        print(f"Deleted old report: {path.name}")
    print(f"Site: {index}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
