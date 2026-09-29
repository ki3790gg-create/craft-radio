# Weekly Craft Business Report

## Goal

Every Monday at 08:00 KST, collect YouTube signals for one-person craft businesses selling products made with cord, beads, and knitting. Publish the result to the report website (GitHub Pages), keeping only the latest 4 weeks.

## How it runs

- GitHub Actions (`.github/workflows/weekly-report.yml`) runs every Sunday 23:00 UTC = Monday 08:00 KST. The PC does not need to be on.
- Steps: `tools/run_weekly_report.py` collects data → `tools/site_builder.py` saves `site/reports/YYYY-MM-DD.json`, deletes old reports, rebuilds `site/index.html` → the bot commits `site/` → the site is deployed.
- Manual run: GitHub repo → Actions → "Weekly craft report" → "Run workflow".
- The old Windows scheduled task `CraftBusinessWeeklyReport` is disabled so the report is not collected twice.

## Collection scope

- Search terms: Korean and English terms for cord crafts, bead accessories, knitting goods, and handmade selling (`tools/config.py` → `SEARCH_TERMS`).
- Review window: the previous 7 days.
- Established channels: rank by subscriber count, then by relevant video views.
- High-interest items: identify repeated product words and formats among the most-viewed videos.
- Rising videos: prioritize recent videos with high views-per-hour and low or hidden subscriber counts.

## Website

- Layout: sky-blue background, white cards, navy text; footer text white.
- Left column (top → bottom): week switcher paperclips → "Craft Radio" title → clear white LP with the current thumbnail showing through → NOW PLAYING title (never wider than the LP) → frameless ⏮ ▶ ⏭ icons (all the same size, flash white when pressed) → "WEEKLY CRAFT REPORT / UPDATED" stamp, right-aligned to the title's right end.
- Right column: "Playlist!" with a two-line caption beside it, then the 5 recommended videos as a zigzag pile of tilted polaroids with green washi tape (no numbers). Earlier photos sit on top so overlaps never hide a caption.
- Below: keyword "search bar", channel polaroids, idea notes (ruled lines).
- Week switcher: one white paperclip per stored week, newest first, scattered angles (`CLIP_ANGLES`, kept apart modulo 180° because a clip turned upside down looks the same), all on one line; the selected week is navy; the date shows only as a hover tooltip.
- Fonts: big titles in Dancing Script; everything else in 오뮤 다예쁨체 (`omyu_pretty`, from jsDelivr, scaled 115%).
- Spacing gotcha: `.wrap` sets padding, so `main`/`footer` padding must be written as `main.wrap` / `footer.wrap` or it is silently ignored.
- Videos play in a popup (youtube-nocookie embed, loaded only when opened; closing stops playback). Shorts open in a tall 9:16 popup, other videos in 16:9.
- Shorts detection: `is_short()` in `tools/youtube_research.py` checks `youtube.com/shorts/<id>` (200 = Short, redirect = regular). No API quota. Falls back to "#short" in the title.
- YouTube `hqdefault` thumbnails contain black letterbox bars; the LP zooms the image past them (more for Shorts). The search API also returns HTML-encoded titles (`&#39;`); `site_builder.py` decodes them.
- Videos whose owner disabled embedding (`embeddable: false` from the YouTube API) show the thumbnail and a "유튜브에서 보기" button instead.

## Retention

- One file per week in `site/reports/`, named by the KST collection date.
- A report is deleted when it is 28 days old or older, and never more than 4 are kept (`RETENTION_DAYS`, `MAX_REPORTS` in `tools/config.py`).
- Deleted reports disappear from the site. They still exist in the GitHub commit history (public YouTube data only).
- Running twice on the same day overwrites that day's file.

## Operating rules

- Never store API keys in workflows or source files. Locally use `.env`; on GitHub use the repository secret `YOUTUBE_API_KEY`.
- `--dry-run` uses fake data and writes to `.tmp/site/`, never to the real `site/`.
- Keep raw API responses and generated Markdown in `.tmp/` only.
- Do not claim subscriber counts when the channel hides them; label them as "비공개".
- YouTube quota: about 600 of the free 10,000 daily units per run. No paid usage.

## Where things live

- Repository: https://github.com/ki3790gg-create/craft-radio (the source of truth — the bot commits new weekly reports there, so the local `site/` folder falls behind; that is expected)
- Live site: https://ki3790gg-create.github.io/craft-radio/
- This PC has no git. To change files, upload them on GitHub's web page ("Add file → Upload files").
- GitHub's drag-and-drop upload silently skips names starting with a dot (`.github/`, `.gitignore`). Create those with "Add file → Create new file", or open `https://github.com/<repo>/new/main?filename=<path>&value=<url-encoded content>` to prefill the editor.

## Troubleshooting

- Action fails with "YOUTUBE_API_KEY is not configured": the repository secret is missing or misnamed.
- Action fails at "Save updated reports" (push rejected): Settings → Actions → General → Workflow permissions → "Read and write permissions".
- Site not updating: Settings → Pages → Source must be "GitHub Actions".
- A video shows YouTube's "unavailable" error inside the player: it was deleted or made private after collection; the next weekly run replaces it.
