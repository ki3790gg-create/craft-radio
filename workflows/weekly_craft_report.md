# Weekly Craft Business Report

## Goal

Every Monday at 08:00 KST, collect YouTube signals for one-person craft businesses selling products made with cord, beads, and knitting. Publish the result to the report website (GitHub Pages), keeping only the latest 4 weeks.

## How it runs

- GitHub Actions (`.github/workflows/weekly-report.yml`) runs every Sunday 23:00 UTC = Monday 08:00 KST. The PC does not need to be on.
- Steps: `tools/run_weekly_report.py` collects data → `tools/site_builder.py` saves `site/reports/YYYY-MM-DD.json`, deletes old reports, rebuilds `site/index.html` → the bot commits `site/` → the site is deployed.
- Manual run: GitHub repo → Actions → "Weekly craft report" → "Run workflow".
- The old Windows scheduled task `CraftBusinessWeeklyReport` is disabled so the report is not collected twice.

## Collection scope

- Korea-focused (since 2026-09-29): Korean search terms only for cord crafts, bead accessories, knitting goods, macrame, and handmade selling (`tools/config.py` → `SEARCH_TERMS`), searched with `regionCode=KR` and `relevanceLanguage=ko`.
- After collection, `keep_local()` keeps only videos with a Korean title or from a channel registered in Korea (channel `country`, fetched in the same API call — no extra quota). If fewer than 5 remain, all videos are kept so the report is never empty.
- Review window: the previous 7 days.
- Established channels: rank by subscriber count, then by relevant video views.
- High-interest items: identify repeated product words and formats among the most-viewed videos.
- Rising videos: prioritize recent videos with high views-per-hour and low or hidden subscriber counts.

## Website

- Layout: sky-blue background, white cards, navy text; footer text white (with a faint shadow for legibility).
- Glass tabletop background (referenced from a clear glass ball): `glass_svg()` writes `site/glass.svg` on every build — broad soft curved white reflections with a faint pastel iridescent film (pink/lilac/mint/butter), wide diagonal window glare, soft specular glows and a few glints, one large piece stretched to the page width and repeated downwards. No caustics or water drops (they read as "water"), and no thin white hairlines or small sharp dashes (the user asked for none).
  - Seam/edge rules: blur filters use `filterUnits="userSpaceOnUse"` over the whole canvas (a per-shape region clips wide blurs into hard straight edges), and all light stays within y 150–2250 so the repeat has no seam. Do not put repeating diagonal gradients in the page CSS — their tile edges show as seams.
- Sunlit shadows (reference: glass dessert on a sunny table): cool blue, not grey (`--shade`), all falling to the bottom right. Opaque items (polaroids, notes, keyword box, clips) cast a solid blue shadow on the glass plus a fainter, longer one; the clear LP throws light instead of a plain shadow — `lp_light_svg()` writes `site/lp-light.svg`: rippling arcs of refracted light (strong on the side facing the light, fading on the far side) with a bright focus, offset to the bottom right. The disc itself is milky but see-through (`rgba(255,255,255,.62)`) so that light shows through it.
- Polaroid pile shadows: the long dark shadows sit on a layer under every photo (`.snap-item::before`, z 0), so a photo never throws a heavy shadow onto another; each photo keeps only a small soft shadow of its own so overlaps still read.
- Left column (top → bottom): week switcher paperclips → "Bubble House" title (site name since 2026-09-30, was "Craft Radio") → clear glass LP (mostly transparent, bright polished rim, thumbnail showing through) → NOW PLAYING title (never wider than the LP) → frameless 3D ⏮ ▶ ⏭ icons (navy gradient + thin thickness + blue shadow, all the same size; pressed = sinks in and turns white) → "WEEKLY CRAFT REPORT / UPDATED" stamp, right-aligned to the title's right end.
- Right column: "Playlist!" with a two-line caption beside it, then the 5 recommended videos as a zigzag pile of tilted polaroids with green washi tape (no numbers). Earlier photos sit on top so overlaps never hide a caption.
- Below: keyword "search bar", channel polaroids, idea notes (ruled lines).
- Week switcher: one white paperclip per stored week, newest first, scattered angles (`CLIP_ANGLES`, kept apart modulo 180° because a clip turned upside down looks the same), all on one line; the selected week is navy; the date shows only as a hover tooltip.
- Bold script titles (Bubble House, Playlist!, Channels, Notes, Keywords) carry a faint blue text shadow falling bottom-right, like the objects.
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
