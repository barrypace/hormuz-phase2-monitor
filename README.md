# Gulf Energy Shock Early-Warning Monitor

A lightweight Python monitoring system that tracks emerging conditions for a sustained global energy shock after disruption to Gulf energy flows (for example, Strait of Hormuz closure risk).

## What it monitors

The monitor computes three daily scores:

1. **energy_stress_score**
   - FRED Brent series (`DCOILBRENTEU`)
   - Rules: Brent absolute threshold, weekly change threshold, sustained upward trend
2. **shipping_disruption_score**
   - Public RSS feeds (Reuters + maritime feed defaults)
   - Keyword-based mention counting (hormuz, tanker, convoy, naval escort, etc.)
3. **geopolitical_escalation_score**
   - Official RSS/Atom feeds (US State Dept, White House, UK FCDO default)
   - Escalation keyword mention counting

Alert levels:
- **Level 1**: one score elevated
- **Level 2**: multiple scores elevated
- **Level 3**: all three elevated (systemic shock risk)

## Repository layout

- `data/fetch_data.py` - HTTP GET, FRED fetch, RSS/Atom parsing
- `analysis/scoring.py` - threshold evaluation, score and alert-level logic
- `alerts/notifier.py` - Telegram + GitHub issue + SMTP email notifications
- `monitor.py` - orchestration entrypoint and snapshot generation
- `.github/workflows/daily-monitor.yml` - GitHub Actions scheduled execution
- `tests/` - tests for parsing, scoring, and monitor behavior
- `config.json` - configurable thresholds, feed lists, and operations settings

## Configuration

All thresholds, feeds, and operational controls are in `config.json`.

```json
"thresholds": {
  "brent_price_alert": 120,
  "weekly_change_alert": 0.15,
  "sustained_trend_days": 3,
  "keyword_match_alert": 3,
  "score_elevated_threshold": 2
},
"operations": {
  "notification_cooldown_minutes": 60
}
```

## Secrets (GitHub)

Store sensitive values in GitHub Secrets:

- `FRED_API_KEY` (required for energy data)
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` (optional)
- `EMAIL_SMTP_HOST`
- `EMAIL_SMTP_PORT`
- `EMAIL_SMTP_USERNAME`
- `EMAIL_SMTP_PASSWORD`
- `EMAIL_SMTP_STARTTLS` (`true`/`false`, optional; default true)
- `EMAIL_FROM`
- `EMAIL_TO`

The built-in `GITHUB_TOKEN` is used for issue creation notifications.

## Run locally

```bash
export FRED_API_KEY=your_fred_key
python monitor.py
```

Output:
- Prints natural-language summary
- Writes `data/latest_snapshot.json` (including `data_health` and `operations` blocks)
- Maintains `data/previous_snapshot.json` for alert-level change detection and cooldown tracking

## GitHub Actions schedule

Workflow runs every **10 minutes** (`*/10 * * * *`) and can also be triggered manually (`workflow_dispatch`).
It uploads the latest JSON snapshot as an artifact.

## Notification behavior

- Notifications are sent only when alert level changes.
- Notification channels: Telegram, GitHub issue, SMTP email (when configured).
- Cooldown suppresses repeated notifications when configured (`operations.notification_cooldown_minutes`).

## Add new indicators

- Energy: add a new FRED series in `config.json` and implement rule checks in `analysis/scoring.py`
- Shipping/geopolitical: add RSS/Atom feeds and keywords in `config.json`
- Alerts: add a new notifier function in `alerts/notifier.py` and call it from `monitor.py` when level changes

## Reliability notes

- Only HTTP GET requests are used for external data collection.
- Parsing/fetch failures degrade gracefully (empty datasets/scores) rather than crashing.
- If no FRED key is set, energy score defaults to 0 and RSS-based signals still run.
