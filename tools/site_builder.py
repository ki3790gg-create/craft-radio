"""Build the weekly report website.

Keeps one JSON file per week in site/reports/, deletes reports older than
RETENTION_DAYS (max MAX_REPORTS), and regenerates site/index.html.

    python tools/site_builder.py --add .tmp/weekly_report_20260928_184208.json
    python tools/site_builder.py --rebuild
"""
import argparse
from datetime import datetime, timedelta, timezone
from html import escape, unescape
import json
from pathlib import Path
from typing import Any

from config import MAX_REPORTS, RETENTION_DAYS, SITE_DIR

KST = timezone(timedelta(hours=9))

DEFAULT_IDEAS = [
    "반응이 반복되는 아이템을 1인 제작 시간과 재료비 기준으로 다시 계산한다.",
    "완성품만 보여주기보다 짧은 제작 과정, 포장, 선물 상황을 함께 보여주는 포맷을 시험한다.",
    "소규모 채널 급상승 영상은 첫 3초의 소재와 썸네일 문구를 기록해 다음 상품 영상에 적용한다.",
]


def report_date(data: dict[str, Any]) -> str:
    collected = datetime.fromisoformat(data["collected_at"].replace("Z", "+00:00"))
    return collected.astimezone(KST).date().isoformat()


def _video(item: dict[str, Any], rising_ids: set[str]) -> dict[str, Any]:
    return {
        "video_id": item["video_id"],
        # The YouTube search API returns HTML-encoded titles (e.g. "can&#39;t").
        "title": unescape(item.get("title", "")),
        "channel_title": unescape(item.get("channel_title", "")),
        "channel_url": item.get("channel_url", ""),
        "url": item.get("url") or f"https://www.youtube.com/watch?v={item['video_id']}",
        "published_at": item.get("published_at", ""),
        "view_count": item.get("view_count", 0),
        "views_per_hour": item.get("views_per_hour", 0),
        "embeddable": item.get("embeddable", True),
        "is_short": item.get("is_short", "#short" in item.get("title", "").lower()),
        "rising": item["video_id"] in rising_ids,
    }


def slim_report(data: dict[str, Any], ideas: list[str] | None = None) -> dict[str, Any]:
    """Keep only what the site shows, so the stored files stay small."""
    rising_ids = {item["video_id"] for item in data.get("rising_small_channels", [])}
    channels = []
    for channel in data.get("top_channels", []):
        top_video = (channel.get("videos") or [None])[0]
        channels.append(
            {
                "channel_title": channel["channel_title"],
                "channel_url": channel.get("channel_url", ""),
                "subscriber_count": channel.get("subscriber_count"),
                "total_views": channel.get("total_views", 0),
                "relevant_video_count": channel.get("relevant_video_count", 0),
                "cover_video_id": top_video["video_id"] if top_video else None,
                "cover_is_short": bool(top_video) and top_video.get(
                    "is_short", "#short" in top_video.get("title", "").lower()
                ),
            }
        )
    return {
        "date": report_date(data),
        "collected_at": data["collected_at"],
        "record_count": data.get("record_count", 0),
        "item_signals": [list(pair) for pair in data.get("item_signals", [])[:10]],
        "top_channels": channels,
        "videos": [_video(item, rising_ids) for item in data.get("popular_videos", [])],
        "ideas": ideas or data.get("ideas") or DEFAULT_IDEAS,
    }


def save_report(report: dict[str, Any], site_dir: Path = SITE_DIR) -> Path:
    reports_dir = site_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report['date']}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def prune_reports(site_dir: Path = SITE_DIR, today: datetime | None = None) -> list[Path]:
    """Delete reports older than RETENTION_DAYS, and anything beyond the newest MAX_REPORTS."""
    today_date = (today or datetime.now(KST)).date()
    files = sorted((site_dir / "reports").glob("*.json"), reverse=True)
    removed = []
    kept = 0
    for path in files:
        try:
            age = (today_date - datetime.fromisoformat(path.stem).date()).days
        except ValueError:
            continue
        if age >= RETENTION_DAYS or kept >= MAX_REPORTS:
            path.unlink()
            removed.append(path)
        else:
            kept += 1
    return removed


def load_reports(site_dir: Path = SITE_DIR) -> list[dict[str, Any]]:
    files = sorted((site_dir / "reports").glob("*.json"), reverse=True)
    return [json.loads(path.read_text(encoding="utf-8")) for path in files]


# ---------- HTML ----------

def korean_count(value: int | None) -> str:
    if value is None:
        return "비공개"
    if value >= 100_000_000:
        return f"{value / 100_000_000:.1f}억".replace(".0억", "억")
    if value >= 10_000:
        return f"{value / 10_000:.1f}만".replace(".0만", "만")
    return f"{value:,}"


def thumb(video_id: str, size: str = "hqdefault") -> str:
    return f"https://i.ytimg.com/vi/{escape(video_id)}/{size}.jpg"


def dot_date(iso_date: str) -> str:
    return iso_date.replace("-", ".")


def render_record(first: dict[str, Any] | None) -> str:
    """Clear vinyl: the current thumbnail shows through the whole disc."""
    art = thumb(first["video_id"]) if first else ""
    play = (
        '<button class="disc-play" type="button" data-step="0" aria-label="영상 팝업으로 재생">'
        '<span class="big-play" aria-hidden="true"></span></button>' if first else ""
    )
    short = " short" if first and first.get("is_short") else ""
    return (
        f'<div class="record{short}">'
        '<div class="vinyl" aria-hidden="true">'
        f'<img class="disc-art" src="{art}" alt="">'
        '<span class="grooves"></span>'
        f'<span class="label"><img class="label-art" src="{art}" alt=""></span>'
        '</div>'
        f'<span class="sheen" aria-hidden="true"></span>{play}</div>'
    )


# Polaroid pile: horizontal position (0 = far left, 1 = far right of the free space) and tilt.
SNAP_LAYOUT = [(0.02, -5), (0.96, 4), (0.2, -2), (1, 3), (0.08, -4)]


def render_tracks(week_id: str, videos: list[dict[str, Any]]) -> str:
    rows = []
    for index, video in enumerate(videos):
        x, tilt = SNAP_LAYOUT[index % len(SNAP_LAYOUT)]
        badge = '<span class="badge">급상승</span>' if video["rising"] else ""
        short = " short" if video.get("is_short") else ""
        rows.append(
            # Earlier photos sit on top, so overlaps hit the next photo's picture corner, never a caption.
            f'<li class="snap-item" style="--x:{x};--r:{tilt}deg;--z:{len(videos) - index}">'
            f'<button class="snap{short}" type="button" data-play="{index}">'
            f'<span class="tape" aria-hidden="true"></span>'
            f'<span class="snap-photo"><img src="{thumb(video["video_id"])}" alt="" loading="lazy">'
            f'<span class="snap-play" aria-hidden="true"></span></span>'
            f'<span class="snap-title">{escape(video["title"])}</span>'
            f'<span class="snap-meta">{escape(video["channel_title"])} · 조회수 {korean_count(video["view_count"])}'
            f' {badge}</span></button></li>'
        )
    return f'<ol class="snaps">{"".join(rows)}</ol>'


def render_keywords(signals: list[list[Any]]) -> str:
    if signals:
        chips = "".join(
            f'<li><span>{escape(str(word))}</span><b>{count}</b></li>' for word, count in signals
        )
    else:
        chips = '<li class="none">이번 주는 반복된 아이템 단어가 없어요</li>'
    return (
        '<div class="search-pill"><div class="search-inner">'
        '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/>'
        '<path d="M15.5 15.5 21 21"/></svg>'
        f'<span class="search-label">Keywords of the week.</span></div>'
        f'<ul class="chips">{chips}</ul></div>'
    )


def render_polaroids(channels: list[dict[str, Any]]) -> str:
    cards = []
    for index, channel in enumerate(channels):
        cover = (
            f'<img src="{thumb(channel["cover_video_id"])}" alt="" loading="lazy">'
            if channel.get("cover_video_id") else '<span class="no-photo"></span>'
        )
        cards.append(
            f'<a class="polaroid" style="--tilt:{(-3, 2.5, -1.5, 3)[index % 4]}deg" '
            f'href="{escape(channel["channel_url"])}" target="_blank" rel="noopener">'
            f'<span class="photo{" short" if channel.get("cover_is_short") else ""}">{cover}</span>'
            f'<span class="caption">{escape(unescape(channel["channel_title"]))}</span>'
            f'<span class="caption-sub">구독자 {korean_count(channel["subscriber_count"])}'
            f' · 관련 영상 {channel["relevant_video_count"]}개</span></a>'
        )
    return f'<div class="polaroids">{"".join(cards)}</div>'


def render_week(report: dict[str, Any], active: bool) -> str:
    week_id = report["date"]
    # Older stored reports still hold HTML-encoded titles; decode before re-escaping.
    videos = [
        {**video, "title": unescape(video["title"]), "channel_title": unescape(video["channel_title"])}
        for video in report["videos"]
    ]
    ideas = "".join(f"<li>{escape(idea)}</li>" for idea in report["ideas"])
    video_json = json.dumps(videos, ensure_ascii=False).replace("</", "<\\/")
    return f"""
<section class="week" id="w{week_id}" data-week="{week_id}"{'' if active else ' hidden'}>
  <div class="stage">
    <div class="deck">
      <nav class="dots" aria-label="주차 선택">{{{{TABS}}}}</nav>
      <h1 class="brand">Bubble House</h1>
      {render_record(videos[0] if videos else None)}
      <div class="np-block">
        <p class="now-playing"><span>NOW PLAYING</span> <em class="np-title">{escape(videos[0]['title']) if videos else '이번 주 영상이 없어요'}</em></p>
        <div class="controls">
          <button type="button" class="ctl" data-step="-1" aria-label="이전 영상"><svg viewBox="0 0 24 24"><path d="M7 5v14M19 5 9 12l10 7z"/></svg></button>
          <button type="button" class="ctl play" data-step="0" aria-label="재생"><svg viewBox="0 0 24 24"><path d="M7 4l13 8-13 8z"/></svg></button>
          <button type="button" class="ctl" data-step="1" aria-label="다음 영상"><svg viewBox="0 0 24 24"><path d="M17 5v14M5 5l10 7-10 7z"/></svg></button>
        </div>
        <div class="stamp"><span>WEEKLY CRAFT REPORT<br>UPDATED {{{{UPDATED}}}}</span><span class="disc" aria-hidden="true"></span></div>
      </div>
    </div>
    <div class="playlist">
      <div class="playlist-head">
        <h2 class="display">Playlist!</h2>
        <p class="sub">이번 주 추천 영상 {len(videos)}개<br>누르면 바로 재생돼요</p>
      </div>
      {render_tracks(week_id, videos)}
    </div>
  </div>
  {render_keywords(report["item_signals"])}
  <div class="lower">
    <div>
      <h2 class="display small">Channels</h2>
      <p class="sub">주목할 채널</p>
      {render_polaroids(report["top_channels"])}
    </div>
    <div>
      <h2 class="display small">Notes</h2>
      <p class="sub">1인 제작 사업 실행 아이디어</p>
      <ol class="notes">{ideas}</ol>
    </div>
  </div>
  <script type="application/json" class="week-data">{video_json}</script>
</section>"""


# Clip angles in degrees: tossed-on-the-desk look, but all centred on one line.
# A clip turned 180° looks almost the same, so keep the angles spread apart modulo 180.
CLIP_ANGLES = [-72, 48, 168, -142]
CLIP_SVG = (
    '<svg width="16" height="37" viewBox="0 0 12 28" aria-hidden="true">'
    '<path d="M8.5 9v11a2.5 2.5 0 0 1-5 0V6a4 4 0 0 1 8 0v15a5.5 5.5 0 0 1-11 0V9"/></svg>'
)


def render_site(reports: list[dict[str, Any]]) -> str:
    if reports:
        # One paperclip per stored week, newest first, each at its own angle; the date is a tooltip only.
        current = ' aria-current="page"'
        tabs = "".join(
            f'<a class="dot" href="#w{r["date"]}" data-tab="{r["date"]}" style="--r:{CLIP_ANGLES[i % len(CLIP_ANGLES)]}deg" '
            f'title="{dot_date(r["date"])}" aria-label="{dot_date(r["date"])} 리포트"{current if i == 0 else ""}>{CLIP_SVG}</a>'
            for i, r in enumerate(reports)
        )
        weeks = "".join(render_week(r, i == 0) for i, r in enumerate(reports))
        latest = reports[0]
        updated = dot_date(latest["date"])
        footer = (
            f"최근 {len(reports)}주 보관 · 4주가 지난 리포트는 자동 삭제돼요 · "
            f"최신 수집 영상 {latest['record_count']}개"
        )
    else:
        tabs, weeks, updated = "", '<p class="empty-site">아직 리포트가 없어요</p>', "-"
        footer = ""
    # WEEKS first: each week's deck carries {{TABS}} / {{UPDATED}} placeholders of its own.
    return PAGE.replace("{{WEEKS}}", weeks).replace("{{TABS}}", tabs) \
        .replace("{{UPDATED}}", updated).replace("{{FOOTER}}", escape(footer))


GLASS_W, GLASS_H = 1200, 2400  # one big piece, scaled to the page width and repeated downwards

# Everything stays inside y = 150..2250 (blur included) so the piece repeats downwards with no seam.
# Reflections like those on a clear glass ball: (curve, band width). Each becomes a broad soft
# white band with a pastel iridescent film beside it. (No hairline edges: the user asked for none.)
GLASS_REFLECTIONS = [
    ("M-80 390C260 200 760 180 1280 340", 110),
    ("M1000 480C900 780 920 1060 1060 1300", 70),
    ("M-60 1180C300 980 640 1000 980 1160", 90),
    ("M180 1480C130 1720 160 1920 280 2080", 60),
    ("M380 1980C700 1830 1000 1850 1300 1960", 100),
]
# Window glare on the tabletop: straight diagonal soft bands (path, width, opacity).
GLASS_GLARES = [
    ("M780 260L300 1060", 150, .20),
    ("M1150 880L720 1640", 60, .30),
    ("M620 1500L300 2080", 110, .18),
]
# Short, soft bright spots where the glass catches the light: (x, y, rx, ry, angle, opacity).
GLASS_SPECULARS = [
    (840, 330, 70, 18, -18, .5), (1040, 760, 50, 14, 70, .45), (260, 1110, 64, 16, -12, .45),
    (760, 1650, 56, 14, -58, .42), (430, 1960, 76, 18, -10, .45), (150, 640, 44, 12, -60, .38),
]
GLASS_GLINTS = [(820, 250, 9), (1068, 1240, 7), (300, 1052, 6), (296, 2080, 8), (1180, 1935, 7), (560, 548, 5)]


def glass_svg() -> str:
    """Clear-glass texture: soft curved reflections, iridescent film, window glare,
    soft specular spots and a few glints.

    Transparent everywhere else, so it sits on top of the sky-blue page colour.
    """
    bands = []
    for d, w in GLASS_REFLECTIONS:
        bands.append(
            f'<path d="{d}" stroke="#fff" stroke-width="{w}" opacity=".30" filter="url(#soft)"/>'
            f'<path d="{d}" transform="translate(0 {w * .42:.0f})" stroke="url(#iris)" stroke-width="{w * .6:.0f}" opacity=".42" filter="url(#mid)"/>'
        )
    glares = "".join(
        f'<path d="{d}" stroke="#fff" stroke-width="{w}" opacity="{o}" filter="url(#soft)"/>' for d, w, o in GLASS_GLARES
    )
    speculars = "".join(
        f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" transform="rotate({a} {x} {y})" fill="#fff" opacity="{o}" filter="url(#spec)"/>'
        for x, y, rx, ry, a, o in GLASS_SPECULARS
    )
    glints = "".join(
        f'<g transform="translate({x} {y})"><circle r="{s * .45:.1f}" fill="url(#glint)"/>'
        f'<path d="M0 {-s}L{s * .09:.1f} 0 0 {s} {-s * .09:.1f} 0ZM{-s} 0 0 {s * .09:.1f} {s} 0 0 {-s * .09:.1f}Z" fill="#fff"/></g>'
        for x, y, s in GLASS_GLINTS
    )
    # Blur regions cover the whole canvas (userSpaceOnUse): a region sized to each shape's own
    # box clips wide blurs into hard straight edges.
    region = f'filterUnits="userSpaceOnUse" x="-300" y="-300" width="{GLASS_W + 600}" height="{GLASS_H + 600}"'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{GLASS_W}" height="{GLASS_H}" viewBox="0 0 {GLASS_W} {GLASS_H}">
<defs>
  <filter id="soft" {region}><feGaussianBlur stdDeviation="26"/></filter>
  <filter id="mid" {region}><feGaussianBlur stdDeviation="16"/></filter>
  <filter id="spec" {region}><feGaussianBlur stdDeviation="9"/></filter>
  <!-- thin-film iridescence: the faint pink / lilac / mint / butter sheen on clear glass -->
  <linearGradient id="iris" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{GLASS_W}" y2="{GLASS_H // 3}" spreadMethod="reflect">
    <stop offset="0" stop-color="#ffd6ec"/>
    <stop offset=".3" stop-color="#e2d6ff"/>
    <stop offset=".55" stop-color="#c7f4ec"/>
    <stop offset=".8" stop-color="#fff3c6"/>
    <stop offset="1" stop-color="#ffd6ec"/>
  </linearGradient>
  <radialGradient id="glint"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
</defs>
<g fill="none" stroke-linecap="round">{glares}{"".join(bands)}</g>
{speculars}
{glints}
</svg>"""


# Light the clear LP throws onto the table: wobbly concentric rings of refracted light.
# (radius, ring width, opacity, x-offset) - offsets make the rings swirl slightly, like a glass bowl's.
LP_LIGHT_RINGS = [
    (52, 10, .75, 6), (88, 7, .62, 3), (104, 14, .36, 9), (141, 8, .68, 4), (178, 12, .58, 8),
]


def lp_light_svg() -> str:
    """The clear LP's shadow: a faint blue disc with rippling arcs of light and a bright focus.

    The rings are strongest on the side facing the light and fade out on the far side,
    so they read as arcs of refracted light rather than tree rings.
    """
    rings = "".join(
        # each ring: a wide soft glow plus a narrower brighter core
        f'<circle cx="{200 + dx}" cy="200" r="{r}" stroke-width="{w * 2.2:.0f}" opacity="{o * .5:.2f}"/>'
        f'<circle cx="{200 + dx}" cy="200" r="{r}" stroke-width="{w * .55:.1f}" opacity="{min(o * 1.2, 1):.2f}"/>'
        for r, w, o, dx in LP_LIGHT_RINGS
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">
<defs>
  <radialGradient id="shade" r=".5">
    <stop offset="0" stop-color="#fff" stop-opacity=".55"/>
    <stop offset=".35" stop-color="#3060b0" stop-opacity=".08"/>
    <stop offset=".85" stop-color="#3060b0" stop-opacity=".26"/>
    <stop offset=".97" stop-color="#3060b0" stop-opacity=".1"/>
    <stop offset="1" stop-color="#3060b0" stop-opacity="0"/>
  </radialGradient>
  <!-- ripple: bend the rings with a little noise, then soften so they read as light, not lines -->
  <filter id="ripple" filterUnits="userSpaceOnUse" x="-20" y="-20" width="440" height="440">
    <feTurbulence type="fractalNoise" baseFrequency=".009" numOctaves="2" seed="4"/>
    <feDisplacementMap in="SourceGraphic" scale="26" xChannelSelector="R" yChannelSelector="G"/>
    <feGaussianBlur stdDeviation="2.2"/>
  </filter>
  <!-- light side (top left) strong, far side fades away -->
  <linearGradient id="side" x1=".15" y1=".1" x2=".85" y2=".95">
    <stop offset="0" stop-color="#fff"/>
    <stop offset=".55" stop-color="#fff" stop-opacity=".7"/>
    <stop offset="1" stop-color="#fff" stop-opacity=".2"/>
  </linearGradient>
  <mask id="fade" maskUnits="userSpaceOnUse" x="0" y="0" width="400" height="400"><rect width="400" height="400" fill="url(#side)"/></mask>
  <filter id="glow" filterUnits="userSpaceOnUse" x="-20" y="-20" width="440" height="440"><feGaussianBlur stdDeviation="10"/></filter>
  <filter id="edge" filterUnits="userSpaceOnUse" x="-20" y="-20" width="440" height="440"><feGaussianBlur stdDeviation="4"/></filter>
</defs>
<circle cx="200" cy="200" r="197" fill="url(#shade)" filter="url(#edge)"/>
<g mask="url(#fade)"><g fill="none" stroke="#fff" filter="url(#ripple)">{rings}</g></g>
<ellipse cx="176" cy="170" rx="46" ry="26" transform="rotate(-24 176 170)" fill="#fff" opacity=".8" filter="url(#glow)"/>
</svg>"""


def build_site(site_dir: Path = SITE_DIR) -> Path:
    site_dir.mkdir(parents=True, exist_ok=True)
    index = site_dir / "index.html"
    index.write_text(render_site(load_reports(site_dir)), encoding="utf-8")
    (site_dir / "glass.svg").write_text(glass_svg(), encoding="utf-8")
    (site_dir / "lp-light.svg").write_text(lp_light_svg(), encoding="utf-8")
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")
    return index


def publish(data: dict[str, Any], ideas: list[str] | None = None, site_dir: Path = SITE_DIR,
            today: datetime | None = None) -> tuple[Path, list[Path]]:
    save_report(slim_report(data, ideas), site_dir)
    removed = prune_reports(site_dir, today)
    return build_site(site_dir), removed


PAGE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bubble House · 주간 공예 리포트</title>
<meta name="description" content="매주 월요일 업데이트되는 매듭·비즈·뜨개 공예 유튜브 트렌드 리포트">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=League+Spartan:wght@500;700;800&family=Dancing+Script:wght@700&display=swap" rel="stylesheet">
<style>
/* 오뮤 다예쁨체 (diary handwriting). Its glyphs run small, so scale them up. */
@font-face{font-family:"omyu_pretty";src:url("https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2304-01@1.0/omyu_pretty.woff2") format("woff2");
  font-display:swap;size-adjust:115%}
:root{
  --sky:#bcd3ef; --sky-deep:#a9c4e8; --sky-soft:#dbe7f7;
  --navy:#1f3864; --navy-deep:#142848; --ink:#0f1f3a;
  --paper:#fbfaf6; --muted:#5a6f93; --accent:#f4d46b;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;color:var(--ink);
  font-family:"omyu_pretty",system-ui,sans-serif;line-height:1.5;overflow-x:hidden}

/* ---- glass tabletop ----
   glass.svg (generated by glass_svg()) adds clear-glass reflections - soft curved bands,
   iridescent film and glints, like a glass ball - over
   soft window light and long reflections. The surface scrolls with the page, like a photo of a table.
   Objects get two shadows: a crisp one on the glass and a faint, offset, blurred one on the
   floor seen through the glass - the tell-tale look of a glass table. */
html{background:var(--sky)}
body{position:relative;min-height:100vh}
:root{
  /* sunlit shadows are cool blue, not grey, and all fall the same way (light from the top left) */
  --shade:48,96,176;
  --on-glass:0 1px 2px rgba(var(--shade),.3),0 3px 8px rgba(var(--shade),.24),8px 12px 16px -5px rgba(var(--shade),.36);
  --through-glass:18px 26px 22px rgba(var(--shade),.22);
  --grain:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .5 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}
body::before{content:"";position:absolute;inset:0;z-index:-1;pointer-events:none;
  background:
    /* glass reflections, iridescence, window glare, specular spots, glints (seamless when repeated) */
    url("glass.svg"),
    /* window light falling in from the top left; fades out fully inside its box, so no edge */
    radial-gradient(ellipse 70% 45% at 8% -8%,rgba(255,255,255,.62),rgba(255,255,255,0) 70%),
    /* depth: the glass gets a touch deeper and bluer further from the light */
    radial-gradient(ellipse 90% 70% at 100% 110%,rgba(95,138,198,.28),transparent 70%),
    /* very fine surface grain so it reads as a material, not a flat colour */
    var(--grain),
    var(--sky);
  background-size:max(100%,900px) auto,100% 1400px,100% 100%,180px 180px,auto;
  background-position:center top,0 0,0 0,0 0,0 0;
  background-repeat:repeat-y,no-repeat,no-repeat,repeat,repeat;
  background-blend-mode:normal,normal,normal,soft-light,normal}
button{font:inherit;color:inherit;border:0;background:none;cursor:pointer;padding:0}
a{color:inherit}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px}

/* header */
main.wrap{padding-top:64px}
/* site title sits centred above the LP */
.brand{margin:0 0 36px;font:700 46px/1.1 "Dancing Script",cursive;color:var(--navy);text-align:center}
/* bold script titles sit on the glass too: a faint blue shadow falling the same way as everything else */
.brand,.display,.search-label{text-shadow:1px 2px 1px rgba(var(--shade),.18),3px 5px 6px rgba(var(--shade),.24)}
/* week switcher: white paperclips at mixed angles under the LP; the selected week turns navy.
   Clip centres ~132px apart, well wider than the ⏮ ▶ ⏭ icons (72px). */
.dots{display:flex;justify-content:center;align-items:center;gap:120px;height:52px;margin:0 0 80px}
.dot{display:block;transform:rotate(var(--r));transition:transform .15s}
.dot svg{display:block;fill:none;stroke:#fff;stroke-width:2.2;stroke-linecap:round;
  filter:drop-shadow(0 1.5px 2px rgba(var(--shade),.45)) drop-shadow(5px 7px 4px rgba(var(--shade),.3));transition:stroke .15s}
.dot:hover{transform:rotate(var(--r)) scale(1.15)}
.dot:focus-visible{outline:2px solid var(--navy);outline-offset:3px;border-radius:4px}
.dot[aria-current] svg,.dot:active svg{stroke:var(--navy)}
.stamp{display:flex;align-items:center;gap:10px;text-align:right;font:700 11px/1.3 "League Spartan",sans-serif;
  letter-spacing:.06em;color:var(--navy)}
.stamp .disc{flex:none;width:44px;height:44px;border-radius:50%;border:3px solid var(--navy);
  background:repeating-radial-gradient(circle,#1b1b22 0 2px,#2a2a33 2px 3px);position:relative;
  box-shadow:0 1px 2px rgba(var(--shade),.3),3px 4px 6px rgba(var(--shade),.28)}
.stamp .disc::after{content:"";position:absolute;inset:14px;border-radius:50%;background:var(--sky-soft)}

/* stage */
.stage{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:40px;align-items:start;padding:28px 0 88px}
.deck{--disc:560px;display:flex;flex-direction:column;align-items:center;padding-top:14px}

/* clear vinyl: thumbnail shows through a tinted, grooved disc */
.record{position:relative;width:min(var(--disc),100%);aspect-ratio:1;border-radius:50%;
  filter:drop-shadow(0 2px 4px rgba(var(--shade),.3))}
/* the clear LP throws light, not just shadow: rippling rings of refracted light (lp-light.svg,
   generated by lp_light_svg()) with a bright focus, offset towards the bottom right */
.record::before{content:"";position:absolute;inset:0;z-index:-1;transform:translate(5%,6%);
  background:url("lp-light.svg") center/100% 100% no-repeat}
/* the disc is milky but see-through, so its own light pattern on the table shows through it */
.vinyl{position:absolute;inset:0;border-radius:50%;overflow:hidden;background:rgba(255,255,255,.24);
  animation:spin 12s linear infinite;animation-play-state:paused}
.week.playing .vinyl{animation-play-state:running}
/* hqdefault thumbnails carry black letterbox bars; zoom past them (Shorts need more) */
.record{--zoom:1.34}
.record.short{--zoom:2.4}
.disc-art,.label-art{transform:scale(var(--zoom))}
.disc-art{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.4;filter:saturate(1.1) blur(.5px)}
/* clear glass disc: faint grooves, a bright polished rim, and a slightly darker far edge where light bends */
.grooves{position:absolute;inset:0;border-radius:50%;
  background:
    radial-gradient(circle closest-side,transparent 0 33%,rgba(255,255,255,.12) 33.5% 100%),
    repeating-radial-gradient(circle,rgba(255,255,255,.26) 0 1px,transparent 1px 3px,rgba(31,56,100,.05) 3px 4px);
  box-shadow:inset 0 0 0 2px rgba(255,255,255,.9),inset 0 0 0 10px rgba(255,255,255,.22),
    inset 0 0 28px rgba(255,255,255,.55),inset -12px -16px 44px rgba(var(--shade),.2)}
.label{position:absolute;inset:33%;border-radius:50%;overflow:hidden;border:6px solid #fff;background:#fff;
  box-shadow:0 0 0 1px rgba(31,56,100,.15)}
.label-art{width:100%;height:100%;object-fit:cover}
.sheen{position:absolute;inset:0;border-radius:50%;pointer-events:none;
  background:
    conic-gradient(from 20deg,transparent 0 8%,rgba(255,255,255,.55) 12%,transparent 18% 52%,rgba(255,255,255,.42) 58%,transparent 64%),
    radial-gradient(circle at 30% 25%,rgba(255,255,255,.45),transparent 45%);
  -webkit-mask:radial-gradient(circle closest-side,transparent 0 33%,#000 33.5%);mask:radial-gradient(circle closest-side,transparent 0 33%,#000 33.5%)}
@keyframes spin{to{transform:rotate(360deg)}}
.disc-play{position:absolute;left:50%;top:50%;width:92px;height:92px;margin:-46px;border-radius:50%}
.big-play{position:absolute;left:50%;top:50%;width:74px;height:74px;margin:-37px;border-radius:50%;
  background:rgba(251,250,246,.92);box-shadow:0 0 0 6px rgba(188,211,239,.55);transition:transform .15s}
.big-play::after{content:"";position:absolute;left:29px;top:22px;border-style:solid;border-width:15px 0 15px 24px;border-color:transparent transparent transparent var(--navy)}
.disc-play:hover .big-play{background:#fff;transform:scale(1.06)}
/* shrink-wraps the title, so the stamp's right edge follows the title's right end */
.np-block{display:grid;grid-template-columns:minmax(0,1fr);justify-items:center;max-width:min(calc(var(--disc) - 48px),100%);margin-top:26px}
/* zero width + flex-end: the stamp never widens the block, it just hangs left from the right edge */
.np-block .stamp{justify-self:end;width:0;justify-content:flex-end;white-space:nowrap;margin-top:18px}
.now-playing{margin:0;max-width:100%;text-align:center;font:700 20px/1.3 "omyu_pretty",sans-serif;color:var(--navy);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.now-playing span{font:800 11px "League Spartan",sans-serif;letter-spacing:.14em;color:var(--muted);margin-right:6px}
.now-playing em{font-style:normal}
.controls{display:flex;align-items:center;gap:28px;margin:14px 0 0}
.ctl{width:44px;height:44px;display:grid;place-items:center;border-radius:50%;transition:transform .15s,opacity .15s}
.ctl:hover{transform:scale(1.12)}
.ctl:active{transform:scale(.94)}
.ctl:focus-visible{outline:2px solid var(--navy);outline-offset:2px}
.ctl svg{width:30px;height:30px;fill:var(--navy);stroke:var(--navy);stroke-width:2;stroke-linejoin:round;transition:fill .15s,stroke .15s}
/* 3D player icons (still frameless): lit navy at the top, deep navy below, a thin darker
   "thickness" under the shape and a blue shadow on the glass. Pressed: sinks in and turns white. */
.controls .ctl svg{fill:url(#btn3d);stroke:url(#btn3d);
  filter:drop-shadow(0 1.5px 0 #0f1f3a) drop-shadow(0 1px 0 #0f1f3a) drop-shadow(3px 5px 5px rgba(var(--shade),.4))}
.controls .ctl:hover{transform:translateY(-2px) scale(1.08)}
.controls .ctl:active,.controls .ctl.pressed{transform:translateY(2px) scale(.96)}
.controls .ctl:active svg,.controls .ctl.pressed svg{fill:#fff;stroke:#fff;
  filter:drop-shadow(0 .5px 0 #c9d8ee) drop-shadow(1px 2px 2px rgba(var(--shade),.35))}

/* popup player */
.modal{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;padding:20px;
  background:rgba(20,40,72,.55);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}
.modal[hidden]{display:none}
.modal-card{position:relative;width:min(880px,100%);min-width:0;background:var(--paper);border-radius:18px;padding:14px 14px 16px;
  box-shadow:0 30px 70px rgba(15,31,58,.45);animation:pop .18s ease-out}
@keyframes pop{from{transform:scale(.96);opacity:0}}
.screen{position:relative;aspect-ratio:16/9;background:#000;overflow:hidden;border-radius:10px}
/* Shorts: tall popup sized so the whole card fits the screen height */
.modal-card.vertical{width:min(420px,100%,calc((100vh - 150px) * 9 / 16 + 28px))}
.modal-card.vertical .screen{aspect-ratio:9/16}
.screen iframe,.screen img{position:absolute;inset:0;width:100%;height:100%;border:0;object-fit:cover}
.blocked{position:absolute;inset:0;display:grid;place-items:center;text-align:center;background:rgba(15,31,58,.72);color:#fff;padding:20px}
.blocked a{display:inline-block;margin-top:10px;background:#fff;color:var(--navy);padding:8px 16px;border-radius:999px;text-decoration:none;font-weight:700}
.modal-info{display:flex;align-items:center;gap:12px;margin-top:12px;padding:0 4px}
.modal-text{min-width:0;flex:1}
.modal-title{margin:0;font:700 18px/1.3 "omyu_pretty",sans-serif;color:var(--navy);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.modal-channel{margin:2px 0 0;font-size:13px;color:var(--muted)}
.modal-info .ctl{width:36px;height:36px;flex:none}
.modal-info .ctl svg{width:22px;height:22px}
.modal-close{position:absolute;top:-14px;right:-14px;width:40px;height:40px;border-radius:50%;background:var(--paper);
  color:var(--navy);font:700 20px/40px sans-serif;text-align:center;box-shadow:0 6px 16px rgba(15,31,58,.3)}
body.modal-open{overflow:hidden}

/* playlist */
.display{font:700 60px/1.1 "Dancing Script",cursive;color:var(--navy);margin:0;
  display:inline-block}
.display.small{font-size:42px}
.sub{margin:8px 0 18px;color:var(--muted);font-size:14px}
.playlist-head{display:flex;align-items:center;gap:18px;margin-bottom:40px}
.playlist-head .sub{margin:6px 0 0;text-align:left;line-height:1.45}
/* polaroid pile: zigzag, each photo overlaps the corner of the previous one */
/* Shadows live on a layer under every photo, so a photo never casts its shadow onto another one:
   each item's ::before draws only the shadow (z 0), the photos themselves sit above (z 1..5). */
.snaps{--w:54%;--lift:-118px;position:relative;z-index:0;max-width:560px;list-style:none;margin:10px 0 0;padding:0 0 10px}
/* 4% is left free so the tilted corners never poke past the column edge */
.snap-item{position:relative;width:var(--w);margin-left:calc((96% - var(--w)) * var(--x) + 2%)}
.snap-item+.snap-item{margin-top:var(--lift)}
.snap-item::before{content:"";position:absolute;inset:0;z-index:0;border-radius:3px;pointer-events:none;
  box-shadow:var(--on-glass),var(--through-glass);transform:rotate(var(--r));transition:transform .2s,box-shadow .2s}
/* each photo keeps only a small, soft shadow of its own, just enough to show where it overlaps
   the one below; the long dark shadows stay on the layer underneath */
.snap{position:relative;z-index:var(--z);display:block;width:100%;text-align:left;background:var(--paper);color:var(--navy);
  padding:10px 10px 14px;border-radius:3px;transform:rotate(var(--r));transition:transform .2s;
  box-shadow:0 1px 2px rgba(var(--shade),.2),2px 4px 8px rgba(var(--shade),.16)}
.snap-item:hover .snap,.snap-item:focus-within .snap{z-index:10}
/* picked up off the glass: the photo lifts, its shadow softens and drifts further away */
.snap:hover,.snap:focus-visible{transform:rotate(0) translateY(-6px) scale(1.04)}
.snap-item:hover::before,.snap-item:focus-within::before{transform:rotate(0) translateY(-6px) scale(1.04);
  box-shadow:0 4px 10px rgba(var(--shade),.2),14px 20px 26px -6px rgba(var(--shade),.36),26px 36px 32px rgba(var(--shade),.16)}
.snap:focus-visible{outline:2px solid var(--navy);outline-offset:3px}
.snap[aria-pressed="true"]{box-shadow:0 0 0 3px var(--navy),2px 4px 8px rgba(var(--shade),.16)}
/* translucent green washi tape */
.tape{position:absolute;top:-12px;left:50%;z-index:1;width:78px;height:26px;margin-left:-39px;transform:rotate(calc(var(--r) * -1.4));
  background:rgba(143,196,150,.72);box-shadow:0 2px 4px rgba(20,40,72,.12)}
.snap-photo{position:relative;display:block;aspect-ratio:4/3;overflow:hidden;background:var(--sky-deep)}
/* hqdefault thumbnails carry black bars; crop past them (Shorts need more) */
.snap-photo img{width:100%;height:100%;object-fit:cover;transform:scale(1.34)}
.snap.short .snap-photo img{transform:scale(2.37)}
.snap-play{position:absolute;left:50%;top:50%;width:52px;height:52px;margin:-26px;border-radius:50%;
  background:rgba(251,250,246,.9);opacity:0;transition:opacity .2s}
.snap-play::after{content:"";position:absolute;left:20px;top:15px;border-style:solid;border-width:11px 0 11px 17px;border-color:transparent transparent transparent var(--navy)}
.snap:hover .snap-play,.snap:focus-visible .snap-play{opacity:1}
.snap-title{display:-webkit-box;margin-top:10px;font:700 16px/1.3 "omyu_pretty",sans-serif;
  -webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.snap-meta{display:block;margin-top:4px;font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.badge{display:inline-block;margin-left:4px;background:var(--accent);color:var(--ink);font-size:11px;font-weight:700;padding:1px 8px;border-radius:999px}

/* keywords pill */
.search-pill{background:var(--paper);border-radius:36px;padding:14px 18px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin:10px 0 44px;box-shadow:var(--on-glass),var(--through-glass)}
.search-inner{display:flex;align-items:center;gap:10px;background:var(--sky-soft);border-radius:999px;padding:10px 22px 10px 16px}
.search-inner svg{width:22px;height:22px;fill:none;stroke:var(--navy);stroke-width:2.6;stroke-linecap:round}
.search-label{font:700 24px/1 "Dancing Script",cursive;color:var(--navy)}
.chips{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:8px}
.chips li{display:flex;align-items:center;gap:6px;background:var(--paper);color:var(--navy);border:2px solid var(--sky);border-radius:999px;padding:4px 6px 4px 14px;font-size:14px}
.chips li b{background:var(--sky);color:var(--navy);border-radius:999px;min-width:24px;text-align:center;font:800 12px/20px "League Spartan",sans-serif;padding:0 6px}
.chips li.none{padding:6px 14px;color:var(--muted)}

/* polaroids + notes */
.lower{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:48px;padding-bottom:40px}
.polaroids{display:flex;gap:26px;flex-wrap:wrap;padding-top:6px}
.polaroid{width:220px;background:var(--paper);padding:12px 12px 16px;border-radius:3px;text-decoration:none;
  box-shadow:var(--on-glass),var(--through-glass);transform:rotate(var(--tilt));transition:transform .2s}
.polaroid:hover{transform:rotate(0) scale(1.03)}
.photo{display:block;aspect-ratio:1;background:var(--sky-deep);overflow:hidden}
/* square crop past the thumbnail's black bars (Shorts need more) */
.photo img{width:100%;height:100%;object-fit:cover;transform:scale(1.34)}
.photo.short img{transform:scale(1.8)}
.caption{display:block;margin-top:10px;font:700 19px/1.2 "omyu_pretty",sans-serif;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.caption-sub{display:block;font-size:12px;color:var(--muted)}
.notes{list-style:none;counter-reset:n;margin:6px 0 0;padding:0;display:grid;gap:14px}
.notes li{counter-increment:n;position:relative;background:var(--paper);padding:14px 16px 14px 56px;border-radius:4px;
  box-shadow:var(--on-glass),var(--through-glass);
  font-size:15px;line-height:28px}
.notes li::before{content:counter(n,decimal-leading-zero);position:absolute;left:14px;top:14px;font:800 20px/28px "League Spartan",sans-serif;color:var(--navy)}
/* ruled lines sit exactly inside the text box, one under each 28px text line */
.notes li::after{content:"";position:absolute;inset:14px 16px 14px 56px;pointer-events:none;
  background:repeating-linear-gradient(transparent 0 27px,#dbe5f3 27px 28px)}

footer.wrap{padding-top:40px;padding-bottom:48px;font-size:13px;color:#fff;
  text-shadow:0 1px 2px rgba(31,56,100,.45),0 0 8px rgba(31,56,100,.25)}
.empty-site{padding:80px 0;text-align:center;font-size:18px}

@media (max-width:900px){
  .stage{grid-template-columns:minmax(0,1fr);gap:28px;padding-bottom:64px}
  .deck{--disc:460px}
  .lower{grid-template-columns:minmax(0,1fr)}
  .display{font-size:50px}
}
@media (max-width:560px){
  .wrap{padding:0 16px}
  .disc-play{transform:scale(.8)}
  .modal{padding:12px}
  .modal-card{padding:8px 8px 12px;border-radius:14px}
  .modal-close{top:-12px;right:-6px}
  .brand{font-size:38px;margin-bottom:28px}
  .dots{gap:72px}
  .snaps{--w:64%;--lift:-96px}
  .snap-title{font-size:15px}
  .tape{width:62px;height:22px;margin-left:-31px}
  .polaroid{width:calc(50% - 13px)}
  .search-label{font-size:21px}
}
@media (prefers-reduced-motion:reduce){.vinyl{animation:none}}
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>
  <linearGradient id="btn3d" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#5474ad"/><stop offset=".45" stop-color="#2a4a82"/><stop offset="1" stop-color="#132646"/>
  </linearGradient>
</defs></svg>
<main class="wrap">{{WEEKS}}</main>
<footer class="wrap">{{FOOTER}}</footer>
<div class="modal" id="player" role="dialog" aria-modal="true" aria-label="영상 재생" hidden>
  <div class="modal-card">
    <button type="button" class="modal-close" aria-label="닫기">✕</button>
    <div class="screen"></div>
    <div class="modal-info">
      <button type="button" class="ctl" data-modal-step="-1" aria-label="이전 영상"><svg viewBox="0 0 24 24"><path d="M7 5v14M19 5 9 12l10 7z"/></svg></button>
      <div class="modal-text"><p class="modal-title"></p><p class="modal-channel"></p></div>
      <button type="button" class="ctl" data-modal-step="1" aria-label="다음 영상"><svg viewBox="0 0 24 24"><path d="M17 5v14M5 5l10 7-10 7z"/></svg></button>
    </div>
  </div>
</div>
<script>
(function(){
  function embedUrl(id){return "https://www.youtube-nocookie.com/embed/"+encodeURIComponent(id)+"?autoplay=1&rel=0&playsinline=1";}
  function thumbUrl(id){return "https://i.ytimg.com/vi/"+encodeURIComponent(id)+"/hqdefault.jpg";}
  var modal=document.getElementById("player"), screen=modal.querySelector(".screen"), active=null, lastFocus=null;

  function closeModal(){
    if(modal.hidden)return;
    modal.hidden=true;screen.innerHTML="";document.body.classList.remove("modal-open");
    if(active)active.section.classList.remove("playing");
    if(lastFocus)lastFocus.focus();
  }
  function fillModal(week){
    var v=week.videos[week.current];
    screen.innerHTML="";
    modal.querySelector(".modal-card").classList.toggle("vertical",!!v.is_short);
    if(v.embeddable===false){
      var img=document.createElement("img");img.src=thumbUrl(v.video_id);img.alt="";screen.appendChild(img);
      var box=document.createElement("div");box.className="blocked";
      box.innerHTML='<div>이 영상은 유튜브에서만 볼 수 있어요<br><a target="_blank" rel="noopener">유튜브에서 보기 ↗</a></div>';
      box.querySelector("a").href=v.url;screen.appendChild(box);
      week.section.classList.remove("playing");
    }else{
      var f=document.createElement("iframe");
      f.src=embedUrl(v.video_id);f.title=v.title;
      f.allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
      f.allowFullscreen=true;f.referrerPolicy="strict-origin-when-cross-origin";
      screen.appendChild(f);week.section.classList.add("playing");
    }
    modal.querySelector(".modal-title").textContent=v.title;
    modal.querySelector(".modal-channel").textContent=v.channel_title;
  }
  function openModal(week){
    active=week;lastFocus=document.activeElement;
    modal.hidden=false;document.body.classList.add("modal-open");
    fillModal(week);modal.querySelector(".modal-close").focus();
  }

  function setupWeek(section){
    var week={section:section,videos:JSON.parse(section.querySelector(".week-data").textContent),current:0};
    if(!week.videos.length)return;
    function select(index){
      week.current=(index+week.videos.length)%week.videos.length;
      var v=week.videos[week.current];
      section.querySelector(".np-title").textContent=v.title;
      section.querySelectorAll(".disc-art,.label-art").forEach(function(img){img.src=thumbUrl(v.video_id);});
      section.querySelector(".record").classList.toggle("short",!!v.is_short);
      section.querySelectorAll(".snap").forEach(function(t,i){t.setAttribute("aria-pressed",i===week.current?"true":"false");});
    }
    week.select=select;
    section.addEventListener("click",function(e){
      var t=e.target.closest("[data-play]");
      if(t){select(+t.dataset.play);openModal(week);return;}
      var c=e.target.closest("[data-step]");
      if(!c)return;
      // Keep the white "pressed" colour visible briefly, also on touch screens.
      c.classList.add("pressed");setTimeout(function(){c.classList.remove("pressed");},300);
      var s=+c.dataset.step;
      if(s===0)openModal(week);else select(week.current+s);
    });
  }

  modal.addEventListener("click",function(e){
    if(e.target===modal||e.target.closest(".modal-close")){closeModal();return;}
    var c=e.target.closest("[data-modal-step]");
    if(c&&active){active.select(active.current+(+c.dataset.modalStep));fillModal(active);}
  });
  addEventListener("keydown",function(e){if(e.key==="Escape")closeModal();});

  function show(id){
    var target=document.getElementById("w"+id)?id:null;
    closeModal();
    document.querySelectorAll(".week").forEach(function(s,i){
      s.hidden=!(target?s.dataset.week===target:i===0);
    });
    var weekId=target||(document.querySelector(".week")||{dataset:{}}).dataset.week;
    document.querySelectorAll(".dot").forEach(function(a){
      if(a.dataset.tab===weekId)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");
    });
  }
  document.querySelectorAll(".week").forEach(setupWeek);
  function fromHash(){show(location.hash.replace(/^#w/,""));}
  addEventListener("hashchange",fromHash);fromHash();
})();
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the weekly report website")
    parser.add_argument("--add", nargs="*", default=[], help="Raw report JSON files (from .tmp/) to add")
    parser.add_argument("--rebuild", action="store_true", help="Only regenerate index.html")
    parser.add_argument("--site-dir", type=Path, default=SITE_DIR)
    args = parser.parse_args()
    for path in args.add:
        report = slim_report(json.loads(Path(path).read_text(encoding="utf-8")))
        print(f"Added: {save_report(report, args.site_dir)}")
    for path in prune_reports(args.site_dir):
        print(f"Deleted (older than {RETENTION_DAYS} days): {path.name}")
    print(f"Site: {build_site(args.site_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
