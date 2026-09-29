"""Build the weekly report website.

Keeps one JSON file per week in site/reports/, deletes reports older than
RETENTION_DAYS (max MAX_REPORTS), and regenerates site/index.html.

    python tools/site_builder.py --add .tmp/weekly_report_20260928_184208.json
    python tools/site_builder.py --rebuild
"""
import argparse
from datetime import datetime, timedelta, timezone
from html import escape
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
        "title": item.get("title", ""),
        "channel_title": item.get("channel_title", ""),
        "channel_url": item.get("channel_url", ""),
        "url": item.get("url") or f"https://www.youtube.com/watch?v={item['video_id']}",
        "published_at": item.get("published_at", ""),
        "view_count": item.get("view_count", 0),
        "views_per_hour": item.get("views_per_hour", 0),
        "embeddable": item.get("embeddable", True),
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


def render_player(week_id: str, first: dict[str, Any] | None) -> str:
    if not first:
        return '<div class="screen empty">이번 주 영상이 없어요</div>'
    return (
        f'<div class="screen" id="screen-{week_id}">'
        f'<button class="cover" type="button" data-play="0" aria-label="첫 번째 영상 재생">'
        f'<img src="{thumb(first["video_id"])}" alt="" loading="lazy">'
        f'<span class="big-play" aria-hidden="true"></span></button></div>'
    )


def render_tracks(week_id: str, videos: list[dict[str, Any]]) -> str:
    rows = []
    for index, video in enumerate(videos):
        badge = '<span class="badge">급상승</span>' if video["rising"] else ""
        rows.append(
            f'<li><button class="track" type="button" data-play="{index}" style="--i:{index}">'
            f'<img src="{thumb(video["video_id"], "mqdefault")}" alt="" loading="lazy">'
            f'<span class="track-text"><span class="track-title">{escape(video["title"])}</span>'
            f'<span class="track-artist">{escape(video["channel_title"])}</span>'
            f'<span class="track-meta">조회수 {korean_count(video["view_count"])}'
            f' · 시간당 {korean_count(int(video["views_per_hour"]))}회 {badge}</span></span>'
            f'</button></li>'
        )
    return f'<ol class="tracks">{"".join(rows)}</ol>'


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
        f'<span class="search-label">KEYWORDS OF THE WEEK.</span></div>'
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
            f'<span class="photo">{cover}</span>'
            f'<span class="caption">{escape(channel["channel_title"])}</span>'
            f'<span class="caption-sub">구독자 {korean_count(channel["subscriber_count"])}'
            f' · 관련 영상 {channel["relevant_video_count"]}개</span></a>'
        )
    return f'<div class="polaroids">{"".join(cards)}</div>'


def render_week(report: dict[str, Any], active: bool) -> str:
    week_id = report["date"]
    videos = report["videos"]
    ideas = "".join(f"<li>{escape(idea)}</li>" for idea in report["ideas"])
    video_json = json.dumps(videos, ensure_ascii=False).replace("</", "<\\/")
    return f"""
<section class="week" id="w{week_id}" data-week="{week_id}"{'' if active else ' hidden'}>
  <div class="stage">
    <div class="deck">
      <div class="vinyl" aria-hidden="true"><div class="label"><img src="{thumb(videos[0]['video_id']) if videos else ''}" alt=""></div></div>
      <div class="player-frame">
        {render_player(week_id, videos[0] if videos else None)}
        <p class="now-playing"><span>NOW PLAYING</span> <em class="np-title">{escape(videos[0]['title']) if videos else ''}</em></p>
      </div>
      <div class="controls">
        <button type="button" class="ctl" data-step="-1" aria-label="이전 영상"><svg viewBox="0 0 24 24"><path d="M7 5v14M19 5 9 12l10 7z"/></svg></button>
        <button type="button" class="ctl" data-step="0" aria-label="재생"><svg viewBox="0 0 24 24"><path d="M7 4l13 8-13 8z"/></svg></button>
        <button type="button" class="ctl" data-step="1" aria-label="다음 영상"><svg viewBox="0 0 24 24"><path d="M17 5v14M5 5l10 7-10 7z"/></svg></button>
      </div>
    </div>
    <div class="playlist">
      <h2 class="display">PLAYLIST!</h2>
      <p class="sub">이번 주 추천 영상 {len(videos)}개 · 누르면 바로 재생돼요</p>
      {render_tracks(week_id, videos)}
    </div>
  </div>
  {render_keywords(report["item_signals"])}
  <div class="lower">
    <div>
      <h2 class="display small">CHANNELS</h2>
      <p class="sub">주목할 채널</p>
      {render_polaroids(report["top_channels"])}
    </div>
    <div>
      <h2 class="display small">NOTES</h2>
      <p class="sub">1인 제작 사업 실행 아이디어</p>
      <ol class="notes">{ideas}</ol>
    </div>
  </div>
  <script type="application/json" class="week-data">{video_json}</script>
</section>"""


def render_site(reports: list[dict[str, Any]]) -> str:
    if reports:
        current = ' aria-current="page"'
        tabs = "".join(
            f'<a href="#w{r["date"]}" data-tab="{r["date"]}"{current if i == 0 else ""}>'
            f'{dot_date(r["date"])[5:]}{" 이번 주" if i == 0 else ""}</a>'
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
    return PAGE.replace("{{TABS}}", tabs).replace("{{WEEKS}}", weeks) \
        .replace("{{UPDATED}}", updated).replace("{{FOOTER}}", escape(footer))


def build_site(site_dir: Path = SITE_DIR) -> Path:
    site_dir.mkdir(parents=True, exist_ok=True)
    index = site_dir / "index.html"
    index.write_text(render_site(load_reports(site_dir)), encoding="utf-8")
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
<title>Craft Radio · 주간 공예 리포트</title>
<meta name="description" content="매주 월요일 업데이트되는 매듭·비즈·뜨개 공예 유튜브 트렌드 리포트">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=League+Spartan:wght@500;700;800&family=Gowun+Dodum&family=Gaegu:wght@700&display=swap" rel="stylesheet">
<style>
:root{
  --sky:#bcd3ef; --sky-deep:#a9c4e8; --sky-soft:#dbe7f7;
  --navy:#1f3864; --navy-deep:#142848; --ink:#0f1f3a;
  --paper:#fbfaf6; --muted:#5a6f93; --accent:#f4d46b;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--sky);color:var(--ink);
  font-family:"Gowun Dodum",system-ui,sans-serif;line-height:1.5;overflow-x:hidden}
button{font:inherit;color:inherit;border:0;background:none;cursor:pointer;padding:0}
a{color:inherit}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px}

/* header */
header{padding:22px 0 8px}
.bar{display:flex;align-items:center;gap:24px;flex-wrap:wrap}
.brand{font:800 15px "League Spartan",sans-serif;letter-spacing:.14em;color:var(--navy);margin-right:auto;text-decoration:none}
nav{display:flex;gap:6px 22px;flex-wrap:wrap}
nav a{font:700 13px "League Spartan","Gowun Dodum",sans-serif;letter-spacing:.08em;color:var(--navy);
  text-decoration:none;padding:4px 0;border-bottom:2px solid transparent}
nav a[aria-current]{border-color:var(--navy)}
.stamp{display:flex;align-items:center;gap:10px;text-align:right;font:700 11px/1.3 "League Spartan",sans-serif;
  letter-spacing:.06em;color:var(--navy)}
.stamp .disc{width:44px;height:44px;border-radius:50%;border:3px solid var(--navy);
  background:repeating-radial-gradient(circle,#1b1b22 0 2px,#2a2a33 2px 3px);position:relative}
.stamp .disc::after{content:"";position:absolute;inset:14px;border-radius:50%;background:var(--sky-soft)}

/* stage */
.stage{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:40px;align-items:start;padding:28px 0 36px}
.deck{position:relative;padding:40px 0 0 0;min-height:560px}
.vinyl{position:absolute;left:-260px;top:0;width:620px;height:620px;border-radius:50%;
  background:
    radial-gradient(circle at 35% 30%,rgba(255,255,255,.18),transparent 40%),
    repeating-radial-gradient(circle,#111118 0 2px,#1d1d26 2px 4px);
  box-shadow:0 20px 50px rgba(20,40,72,.35);animation:spin 9s linear infinite;animation-play-state:paused}
.week.playing .vinyl{animation-play-state:running}
.vinyl .label{position:absolute;inset:34%;border-radius:50%;overflow:hidden;border:6px solid #e8eef8}
.vinyl .label img{width:100%;height:100%;object-fit:cover;filter:grayscale(.35)}
.vinyl .label::after{content:"";position:absolute;left:50%;top:50%;width:14px;height:14px;margin:-7px;border-radius:50%;background:var(--sky)}
@keyframes spin{to{transform:rotate(360deg)}}
.player-frame{position:relative;margin-left:22%;background:var(--paper);padding:14px 14px 10px;border-radius:6px;
  box-shadow:0 18px 40px rgba(20,40,72,.3);transform:rotate(-1.2deg)}
.screen{position:relative;aspect-ratio:16/9;background:#000;overflow:hidden;border-radius:2px}
.screen iframe,.screen .cover,.screen .cover img{position:absolute;inset:0;width:100%;height:100%;border:0;object-fit:cover}
.screen.empty{display:grid;place-items:center;color:#fff}
.big-play{position:absolute;left:50%;top:50%;width:74px;height:74px;margin:-37px;border-radius:50%;
  background:rgba(251,250,246,.92);box-shadow:0 0 0 6px rgba(188,211,239,.55)}
.big-play::after{content:"";position:absolute;left:29px;top:22px;border-style:solid;border-width:15px 0 15px 24px;border-color:transparent transparent transparent var(--navy)}
.cover:hover .big-play{background:#fff}
.blocked{position:absolute;inset:0;display:grid;place-items:center;text-align:center;background:rgba(15,31,58,.72);color:#fff;padding:20px}
.blocked a{display:inline-block;margin-top:10px;background:#fff;color:var(--navy);padding:8px 16px;border-radius:999px;text-decoration:none;font-weight:700}
.now-playing{margin:10px 2px 2px;font:700 22px/1.2 "Gaegu",cursive;color:var(--navy);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.now-playing span{font:800 11px "League Spartan",sans-serif;letter-spacing:.14em;color:var(--muted);margin-right:6px}
.now-playing em{font-style:normal}
.controls{position:relative;display:flex;gap:12px;margin:26px 0 0 22%}
.ctl{width:50px;height:50px;border-radius:10px;background:var(--paper);display:grid;place-items:center;
  box-shadow:0 0 0 3px var(--sky),0 0 0 5px var(--paper),0 8px 18px rgba(20,40,72,.2);transition:transform .15s}
.ctl:hover{transform:translateY(-2px)}
.ctl svg{width:20px;height:20px;fill:var(--navy);stroke:var(--navy);stroke-width:2;stroke-linejoin:round}

/* playlist */
.display{font:800 52px/1 "League Spartan",sans-serif;color:var(--navy);margin:0;letter-spacing:.01em;
  display:inline-block;border-bottom:5px solid var(--navy);padding-bottom:4px}
.display.small{font-size:34px;border-width:4px}
.sub{margin:8px 0 18px;color:var(--muted);font-size:14px}
.tracks{list-style:none;margin:0;padding:0;display:grid;gap:14px}
.track{display:flex;gap:14px;align-items:center;text-align:left;background:var(--paper);color:var(--navy);
  padding:12px 16px 12px 12px;border-radius:14px;width:100%;transition:transform .15s,box-shadow .15s;box-shadow:0 8px 18px rgba(20,40,72,.15)}
.tracks li:nth-child(even) .track{margin-left:24px;width:calc(100% - 24px)}
.track:hover{transform:translateX(-4px);box-shadow:0 12px 24px rgba(20,40,72,.22)}
.track[aria-pressed="true"]{outline:3px solid var(--navy);outline-offset:2px}
.track img{width:74px;height:74px;flex:none;object-fit:cover;border-radius:10px;border:3px solid var(--sky-soft)}
.track-text{min-width:0;display:grid;gap:2px}
.track-title{font:700 17px/1.25 "League Spartan","Gowun Dodum",sans-serif;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.track-artist{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track-meta{font-size:12px;color:var(--muted)}
.badge{display:inline-block;margin-left:4px;background:var(--accent);color:var(--ink);font-size:11px;font-weight:700;padding:1px 8px;border-radius:999px}

/* keywords pill */
.search-pill{background:var(--paper);border-radius:36px;padding:14px 18px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin:10px 0 44px;box-shadow:0 10px 24px rgba(20,40,72,.15)}
.search-inner{display:flex;align-items:center;gap:10px;background:var(--sky-soft);border-radius:999px;padding:10px 22px 10px 16px}
.search-inner svg{width:22px;height:22px;fill:none;stroke:var(--navy);stroke-width:2.6;stroke-linecap:round}
.search-label{font:800 18px "League Spartan",sans-serif;color:var(--navy);letter-spacing:.03em}
.chips{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:8px}
.chips li{display:flex;align-items:center;gap:6px;background:var(--paper);color:var(--navy);border:2px solid var(--sky);border-radius:999px;padding:4px 6px 4px 14px;font-size:14px}
.chips li b{background:var(--sky);color:var(--navy);border-radius:999px;min-width:24px;text-align:center;font:800 12px/20px "League Spartan",sans-serif;padding:0 6px}
.chips li.none{padding:6px 14px;color:var(--muted)}

/* polaroids + notes */
.lower{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:48px;padding-bottom:40px}
.polaroids{display:flex;gap:26px;flex-wrap:wrap;padding-top:6px}
.polaroid{width:220px;background:var(--paper);padding:12px 12px 16px;border-radius:3px;text-decoration:none;
  box-shadow:0 14px 28px rgba(20,40,72,.28);transform:rotate(var(--tilt));transition:transform .2s}
.polaroid:hover{transform:rotate(0) scale(1.03)}
.photo{display:block;aspect-ratio:1;background:var(--sky-deep);overflow:hidden}
.photo img{width:100%;height:100%;object-fit:cover}
.caption{display:block;margin-top:10px;font:700 22px/1.1 "Gaegu",cursive;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.caption-sub{display:block;font-size:12px;color:var(--muted)}
.notes{list-style:none;counter-reset:n;margin:6px 0 0;padding:0;display:grid;gap:14px}
.notes li{counter-increment:n;position:relative;background:var(--paper);padding:14px 16px 14px 56px;border-radius:4px;
  box-shadow:0 8px 18px rgba(20,40,72,.15);
  background-image:repeating-linear-gradient(transparent 0 27px,#dbe5f3 27px 28px);background-position:0 14px;
  font-size:15px;line-height:28px}
.notes li::before{content:counter(n,decimal-leading-zero);position:absolute;left:14px;top:14px;font:800 20px/28px "League Spartan",sans-serif;color:var(--navy)}

footer{border-top:2px solid var(--navy);padding:16px 0 40px;font-size:13px;color:var(--navy)}
.empty-site{padding:80px 0;text-align:center;font-size:18px}

@media (max-width:900px){
  .stage{grid-template-columns:minmax(0,1fr);gap:28px}
  .deck{min-height:0;padding-top:24px}
  .vinyl{width:420px;height:420px;left:-200px;top:-10px}
  .player-frame{margin-left:12%}
  .controls{margin-left:12%}
  .lower{grid-template-columns:minmax(0,1fr)}
  .display{font-size:42px}
}
@media (max-width:560px){
  .wrap{padding:0 16px}
  .vinyl{width:300px;height:300px;left:-170px;top:0}
  .player-frame{margin-left:0;transform:none;padding:10px 10px 6px}
  .controls{margin:18px 0 0}
  .tracks li:nth-child(even) .track{margin-left:0;width:100%}
  .track img{width:60px;height:60px}
  .track-title{font-size:15px}
  .polaroid{width:calc(50% - 13px)}
  .search-label{font-size:15px}
  .stamp .disc{display:none}
}
@media (prefers-reduced-motion:reduce){.vinyl{animation:none}}
</style>
</head>
<body>
<header class="wrap">
  <div class="bar">
    <a class="brand" href="#">CRAFT RADIO</a>
    <nav aria-label="주차 선택">{{TABS}}</nav>
    <div class="stamp"><span>WEEKLY CRAFT REPORT<br>UPDATED {{UPDATED}}</span><span class="disc" aria-hidden="true"></span></div>
  </div>
</header>
<main class="wrap">{{WEEKS}}</main>
<footer class="wrap">{{FOOTER}}</footer>
<script>
(function(){
  function embedUrl(id){return "https://www.youtube-nocookie.com/embed/"+encodeURIComponent(id)+"?autoplay=1&rel=0&playsinline=1";}
  function setupWeek(section){
    var videos=JSON.parse(section.querySelector(".week-data").textContent);
    var screen=section.querySelector(".screen"), current=0;
    if(!screen||!videos.length)return;
    function play(index){
      current=(index+videos.length)%videos.length;
      var v=videos[current];
      screen.innerHTML="";
      if(v.embeddable===false){
        screen.innerHTML='<img src="https://i.ytimg.com/vi/'+v.video_id+'/hqdefault.jpg" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover">'+
          '<div class="blocked"><div>이 영상은 유튜브에서만 볼 수 있어요<br><a target="_blank" rel="noopener"></a></div></div>';
        var a=screen.querySelector(".blocked a");a.href=v.url;a.textContent="유튜브에서 보기 ↗";
        section.classList.remove("playing");
      }else{
        var f=document.createElement("iframe");
        f.src=embedUrl(v.video_id);f.title=v.title;
        f.allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
        f.allowFullscreen=true;f.referrerPolicy="strict-origin-when-cross-origin";
        screen.appendChild(f);section.classList.add("playing");
      }
      section.querySelector(".np-title").textContent=v.title;
      section.querySelector(".vinyl .label img").src="https://i.ytimg.com/vi/"+v.video_id+"/hqdefault.jpg";
      section.querySelectorAll(".track").forEach(function(t,i){t.setAttribute("aria-pressed",i===current?"true":"false");});
    }
    section.addEventListener("click",function(e){
      var t=e.target.closest("[data-play]");
      if(t){play(+t.dataset.play);if(t.classList.contains("track")&&innerWidth<900)screen.scrollIntoView({behavior:"smooth",block:"center"});return;}
      var c=e.target.closest("[data-step]");
      if(c){var s=+c.dataset.step;play(s===0?current:current+s);}
    });
  }
  function show(id){
    var target=document.getElementById("w"+id)?id:null;
    document.querySelectorAll(".week").forEach(function(s,i){
      var on=target?s.dataset.week===target:i===0;
      if(!on&&!s.hidden){var f=s.querySelector("iframe");if(f){f.remove();s.classList.remove("playing");}}
      s.hidden=!on;
    });
    document.querySelectorAll("nav a").forEach(function(a,i){
      if(target?a.dataset.tab===target:i===0)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current");
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
