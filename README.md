# Craft Radio — Weekly Craft Business Report

A small Python automation that researches YouTube content for a one-person craft business and publishes a weekly report website (GitHub Pages). Only the latest 4 weeks are kept; videos play inside the page.

## Weekly run (GitHub Actions)

`.github/workflows/weekly-report.yml` runs every Monday 08:00 KST, updates `site/`, and deploys it.

One-time GitHub setup:

1. Settings → Secrets and variables → Actions → New repository secret: `YOUTUBE_API_KEY`.
2. Settings → Pages → Source: **GitHub Actions**.
3. Settings → Actions → General → Workflow permissions: **Read and write permissions**.
4. Actions → "Weekly craft report" → **Run workflow** to test.

## Local run

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py tools\run_weekly_report.py --dry-run   # fake data → .tmp\site\index.html
py tools\site_builder.py --rebuild        # regenerate site\index.html from site\reports
```

See `workflows/weekly_craft_report.md` for the report contract, retention rule, and troubleshooting.
