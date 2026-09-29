from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import re
from typing import Any

import requests


class YouTubeResearchError(RuntimeError):
    pass


class YouTubeResearch:
    endpoint = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str, max_results: int = 25, region: str = "", language: str = "") -> None:
        self.api_key = api_key
        self.max_results = max_results
        self.region = region
        self.language = language

    def collect(self, search_terms: list[str], lookback_days: int) -> dict[str, Any]:
        if not self.api_key:
            raise YouTubeResearchError("YOUTUBE_API_KEY is not configured")

        published_after = (
            datetime.now(timezone.utc) - timedelta(days=lookback_days)
        ).isoformat().replace("+00:00", "Z")
        found: dict[str, dict[str, Any]] = {}

        for term in search_terms:
            params = {
                "part": "snippet",
                "q": term,
                "type": "video",
                "order": "relevance",
                "publishedAfter": published_after,
                "maxResults": self.max_results,
            }
            if self.region:
                params["regionCode"] = self.region
            if self.language:
                params["relevanceLanguage"] = self.language
            response = self._get("/search", params)
            for item in response.get("items", []):
                video_id = item["id"].get("videoId")
                if video_id:
                    found[video_id] = {
                        "video_id": video_id,
                        "title": item["snippet"]["title"],
                        "description": item["snippet"].get("description", ""),
                        "channel_id": item["snippet"]["channelId"],
                        "channel_title": item["snippet"]["channelTitle"],
                        "published_at": item["snippet"]["publishedAt"],
                        "matched_terms": sorted(
                            set(found.get(video_id, {}).get("matched_terms", [])) | {term}
                        ),
                    }

        videos = self._video_details(list(found))
        channels = self._channel_details(sorted({item["channel_id"] for item in found.values()}))
        records = []
        for video_id, item in found.items():
            record = {**item, **videos.get(video_id, {})}
            record["channel"] = channels.get(item["channel_id"], {})
            record["channel_url"] = f"https://www.youtube.com/channel/{item['channel_id']}"
            record["url"] = f"https://www.youtube.com/watch?v={video_id}"
            records.append(record)

        if self.region:
            records = keep_local(records, self.region)

        result = analyze_records(records)
        covers = [channel["videos"][0] for channel in result["top_channels"] if channel.get("videos")]
        for item in result["popular_videos"] + covers:
            if "is_short" not in item:
                item["is_short"] = is_short(item["video_id"], item.get("title", ""))
        return result

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = requests.get(
            f"{self.endpoint}{path}",
            params={**params, "key": self.api_key},
            timeout=30,
        )
        if not response.ok:
            raise YouTubeResearchError(f"YouTube API error {response.status_code}: {response.text[:300]}")
        return response.json()

    def _video_details(self, video_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not video_ids:
            return {}
        details = {}
        for batch_start in range(0, len(video_ids), 50):
            data = self._get(
                "/videos",
                {
                    "part": "statistics,contentDetails,status",
                    "id": ",".join(video_ids[batch_start:batch_start + 50]),
                },
            )
            for item in data.get("items", []):
                stats = item.get("statistics", {})
                details[item["id"]] = {
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "embeddable": item.get("status", {}).get("embeddable", True),
                }
        return details

    def _channel_details(self, channel_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not channel_ids:
            return {}
        details = {}
        for batch_start in range(0, len(channel_ids), 50):
            data = self._get(
                "/channels",
                {
                    "part": "statistics,snippet",
                    "id": ",".join(channel_ids[batch_start:batch_start + 50]),
                },
            )
            for item in data.get("items", []):
                stats = item.get("statistics", {})
                details[item["id"]] = {
                    "country": item.get("snippet", {}).get("country"),
                    "subscriber_count": int(stats["subscriberCount"])
                    if "subscriberCount" in stats
                    else None,
                    "video_count": int(stats.get("videoCount", 0)),
                }
        return details


HANGUL = re.compile(r"[가-힣]")
MIN_LOCAL_RECORDS = 5


def keep_local(records: list[dict[str, Any]], region: str) -> list[dict[str, Any]]:
    """Keep videos with a Korean title or from a channel registered in `region`.

    Falls back to all records if too few remain, so the weekly report is never empty.
    """
    local = [
        record for record in records
        if HANGUL.search(record.get("title", ""))
        or record.get("channel", {}).get("country") == region
    ]
    return local if len(local) >= MIN_LOCAL_RECORDS else records


def is_short(video_id: str, title: str = "") -> bool:
    """Shorts answer /shorts/<id> directly; regular videos redirect to /watch. No API quota used."""
    try:
        response = requests.head(
            f"https://www.youtube.com/shorts/{video_id}", allow_redirects=False, timeout=15
        )
        if response.status_code in (200, 301, 302, 303, 307, 308):
            return response.status_code == 200
    except requests.RequestException:
        pass
    return "#short" in title.lower()


def analyze_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    for record in records:
        published = datetime.fromisoformat(record["published_at"].replace("Z", "+00:00"))
        age_hours = max((now - published).total_seconds() / 3600, 1)
        record["views_per_hour"] = round(record.get("view_count", 0) / age_hours, 2)

    item_signals = Counter()
    for record in records:
        text = f"{record['title']} {record.get('description', '')}"
        for match in re.findall(
            r"([가-힣A-Za-z0-9]+\s+(?:끈갈피|키링|북마크|파우치|가방|지갑|머리핀|bookmark|keychain|pouch|bag|wallet|hairpin))",
            text,
            flags=re.IGNORECASE,
        ):
            signal = re.sub(r"\s+", " ", match).strip().lower()
            if signal.split()[0] not in {"만드는", "만들기", "만들어요", "making", "diy"}:
                item_signals[signal] += 1

    channels = defaultdict(list)
    for record in records:
        channels[record["channel_title"]].append(record)
    top_channels = []
    for title, channel_records in channels.items():
        stats = channel_records[0].get("channel", {})
        top_channels.append(
            {
                "channel_title": title,
                "subscriber_count": stats.get("subscriber_count"),
                "video_count": stats.get("video_count"),
                "relevant_video_count": len(channel_records),
                "total_views": sum(item.get("view_count", 0) for item in channel_records),
                "channel_url": channel_records[0].get("channel_url", ""),
                "videos": sorted(channel_records, key=lambda item: item.get("view_count", 0), reverse=True)[:5],
            }
        )

    rising = sorted(
        [
            item for item in records
            if item.get("channel", {}).get("subscriber_count") in (None, 0)
            or item.get("channel", {}).get("subscriber_count", 0) <= 1000
        ],
        key=lambda item: item.get("views_per_hour", 0),
        reverse=True,
    )[:5]
    popular = sorted(records, key=lambda item: item.get("view_count", 0), reverse=True)
    recommended = []
    for item in rising + popular:
        if item not in recommended:
            recommended.append(item)
        if len(recommended) == 5:
            break
    return {
        "collected_at": now.isoformat(),
        "record_count": len(records),
        "top_channels": sorted(
            top_channels,
            key=lambda item: (item["subscriber_count"] or 0, item["total_views"]),
            reverse=True,
        )[:2],
        "popular_videos": recommended,
        "rising_small_channels": rising,
        "item_signals": item_signals.most_common(),
    }
