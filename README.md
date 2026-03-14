# Gulf Energy Shock Early-Warning Monitor

A lightweight Python monitoring system that tracks emerging conditions for a sustained global energy shock after disruption to Gulf energy flows (for example, Strait of Hormuz closure risk).

## What it monitors

The monitor computes three daily scores:

1. **energy_stress_score**
   - FRED Brent series (`DCOILBRENTEU`) and 2-year Treasury yield (`DGS2`)
   - Rules: Brent absolute threshold, weekly change threshold, sustained upward trend
   - Data-quality gate requires valid observations from both FRED series
2. **shipping_disruption_score**
   - Reputable keyword-based news fallback via Google News RSS queries (V1)
   - Keyword-based mention counting (hormuz, tanker, convoy, naval escort, etc.)
3. **geopolitical_escalation_score**
   - Official RSS/machine-readable feeds only (White House / State Dept / GOV.UK when validated)
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
  "notification_cooldown_minutes": 60,
  "fail_on_unhealthy_sources": true
}
```

## Secrets (GitHub)

Store sensitive values in GitHub Secrets:

- `FRED_API_KEY` (required; run fails if missing)
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
- Writes `data/latest_snapshot.json` (including `data_health`, `confidence`, and `operations` blocks)
- Maintains `data/previous_snapshot.json` for alert-level change detection and cooldown tracking

## GitHub Actions schedule

Workflow runs every **10 minutes** (`*/10 * * * *`) and can also be triggered manually (`workflow_dispatch`).
It uploads the latest JSON snapshot as an artifact.


## Source validation script

Use the validator to test every configured source before trusting results:

```bash
python scripts/validate_sources.py --fail-on-unsuitable
```

The script writes:
- `data/source_validation_report.json`
- `data/source_validation_report.md`

Each source report includes source name, URL, HTTP status, parse success/failure, production suitability, and a reason.
It also includes recommendations for which sources to keep enabled versus disable/fix.

In GitHub Actions, this markdown report is appended to the job summary (`$GITHUB_STEP_SUMMARY`).

## Notification behavior

- Notifications are sent only when alert level changes.
- Notification channels: Telegram, GitHub issue, SMTP email (when configured).
- Cooldown suppresses repeated notifications when configured (`operations.notification_cooldown_minutes`).

## Data trustworthiness behavior

- Confidence is computed as `HIGH` / `MEDIUM` / `LOW` from critical-source availability.
- Critical-source policy requires: FRED energy data, at least one shipping source, and at least one geopolitical source.
- If `operations.fail_on_unhealthy_sources` is true (default), the run exits non-zero when critical sources are unavailable, so CI turns red.
- FRED is mandatory: run exits non-zero when `FRED_API_KEY` is missing, or when Brent/2Y Treasury return no valid observations.

## Add new indicators

- Energy: add a new FRED series in `config.json` and implement rule checks in `analysis/scoring.py`
- Shipping/geopolitical: add RSS/Atom feeds and keywords in `config.json`
- Alerts: add a new notifier function in `alerts/notifier.py` and call it from `monitor.py` when level changes

## Reliability notes

- Only HTTP GET requests are used for external data collection.
- Parsing/fetch failures degrade gracefully for collection, but trust gates can fail the run.
- Defaults intentionally disable unresolved official geopolitical feeds until validated in-environment.
- Shipping V1 uses resilient keyword-news fallback feeds rather than brittle maritime endpoints.

## Source validation notes (V1 defaults)

- Removed default feeds that were returning 4xx/5xx or non-parseable content in this environment.
- Shipping defaults now use Google News RSS keyword queries as a temporary reputable fallback.
- Geopolitical defaults are empty until official White House/State/GOV.UK machine-readable endpoints are validated in this environment.
