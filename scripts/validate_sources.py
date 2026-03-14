"""Validate configured monitor sources and emit a production-suitability report."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree


@dataclass
class SourceResult:
    source_name: str
    source_group: str
    url: str
    status_code: int | None
    parse_success: bool
    suitable_for_production: bool
    reason: str


def load_config(path: str = "config.json") -> Dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def fetch_url(url: str, timeout: int = 20) -> Tuple[int, str]:
    with urlopen(url, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        body = response.read().decode("utf-8", errors="replace")
        return status, body


def validate_feed(url: str, source_name: str, source_group: str) -> SourceResult:
    try:
        status_code, body = fetch_url(url)
    except Exception as exc:
        return SourceResult(
            source_name=source_name,
            source_group=source_group,
            url=url,
            status_code=None,
            parse_success=False,
            suitable_for_production=False,
            reason=f"request failed: {exc}",
        )

    if status_code < 200 or status_code >= 300:
        return SourceResult(
            source_name=source_name,
            source_group=source_group,
            url=url,
            status_code=status_code,
            parse_success=False,
            suitable_for_production=False,
            reason=f"non-success status code: {status_code}",
        )

    try:
        root = ElementTree.fromstring(body)
        has_items = bool(root.findall(".//item"))
        has_entries = bool(root.findall(".//{http://www.w3.org/2005/Atom}entry"))
        parse_success = has_items or has_entries
        reason = "parsed as RSS/Atom with entries" if parse_success else "parsed XML but no RSS/Atom entries"
        return SourceResult(
            source_name=source_name,
            source_group=source_group,
            url=url,
            status_code=status_code,
            parse_success=parse_success,
            suitable_for_production=parse_success,
            reason=reason,
        )
    except Exception as exc:
        return SourceResult(
            source_name=source_name,
            source_group=source_group,
            url=url,
            status_code=status_code,
            parse_success=False,
            suitable_for_production=False,
            reason=f"parse failed: {exc}",
        )


def validate_fred_series(base_url: str, api_key: str, series_id: str, source_name: str) -> SourceResult:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "limit": 5,
        "sort_order": "desc",
    }
    url = f"{base_url}?{urlencode(params)}"

    if not api_key:
        return SourceResult(
            source_name=source_name,
            source_group="energy",
            url=url,
            status_code=None,
            parse_success=False,
            suitable_for_production=False,
            reason="FRED_API_KEY missing",
        )

    try:
        status_code, body = fetch_url(url)
    except Exception as exc:
        return SourceResult(
            source_name=source_name,
            source_group="energy",
            url=url,
            status_code=None,
            parse_success=False,
            suitable_for_production=False,
            reason=f"request failed: {exc}",
        )

    try:
        payload = json.loads(body)
        observations = payload.get("observations", [])
        valid_observations = [row for row in observations if row.get("value") not in (".", None)]
        ok = status_code == 200 and len(valid_observations) > 0
        reason = "received valid observations" if ok else "no valid observations returned"
        return SourceResult(
            source_name=source_name,
            source_group="energy",
            url=url,
            status_code=status_code,
            parse_success=ok,
            suitable_for_production=ok,
            reason=reason,
        )
    except Exception as exc:
        return SourceResult(
            source_name=source_name,
            source_group="energy",
            url=url,
            status_code=status_code,
            parse_success=False,
            suitable_for_production=False,
            reason=f"json parse failed: {exc}",
        )


def build_recommendations(results: List[SourceResult]) -> Dict[str, List[str]]:
    enabled: List[str] = []
    disabled: List[str] = []
    for result in results:
        label = f"{result.source_name} ({result.url})"
        if result.suitable_for_production:
            enabled.append(label)
        else:
            disabled.append(f"{label} — {result.reason}")
    return {"keep_enabled": enabled, "disable_or_fix": disabled}


def markdown_summary(results: List[SourceResult], recommendations: Dict[str, List[str]]) -> str:
    lines = [
        "## Source Validation Report",
        "",
        "| Source | Group | URL | Status | Parse | Suitable | Reason |",
        "|---|---|---|---:|---|---|---|",
    ]
    for r in results:
        status = str(r.status_code) if r.status_code is not None else "N/A"
        lines.append(
            f"| {r.source_name} | {r.source_group} | {r.url} | {status} | "
            f"{'yes' if r.parse_success else 'no'} | {'yes' if r.suitable_for_production else 'no'} | {r.reason} |"
        )

    lines.extend(["", "### Recommendations", "", "**Keep enabled**"])
    if recommendations["keep_enabled"]:
        lines.extend([f"- {item}" for item in recommendations["keep_enabled"]])
    else:
        lines.append("- None")

    lines.extend(["", "**Disable or fix before production**"])
    if recommendations["disable_or_fix"]:
        lines.extend([f"- {item}" for item in recommendations["disable_or_fix"]])
    else:
        lines.append("- None")

    return "\n".join(lines)


def run(config_path: str, output_json: str, output_md: str, fail_on_unsuitable: bool = False) -> int:
    config = load_config(config_path)
    results: List[SourceResult] = []

    fred = config.get("fred", {})
    fred_series = fred.get("series", {})
    fred_key = os.getenv("FRED_API_KEY", "")
    for series_name in ("brent", "treasury_2y"):
        if series_name in fred_series:
            results.append(
                validate_fred_series(
                    base_url=fred["base_url"],
                    api_key=fred_key,
                    series_id=fred_series[series_name],
                    source_name=f"fred_{series_name}",
                )
            )

    rss = config.get("rss", {})
    for idx, url in enumerate(rss.get("shipping_feeds", []), start=1):
        results.append(validate_feed(url, source_name=f"shipping_feed_{idx}", source_group="shipping"))

    for idx, url in enumerate(rss.get("geopolitical_feeds", []), start=1):
        results.append(validate_feed(url, source_name=f"geopolitical_feed_{idx}", source_group="geopolitical"))

    recommendations = build_recommendations(results)

    json_payload = {
        "results": [asdict(r) for r in results],
        "recommendations": recommendations,
    }
    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(output_md).parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as handle:
        json.dump(json_payload, handle, indent=2)

    md = markdown_summary(results, recommendations)
    with open(output_md, "w", encoding="utf-8") as handle:
        handle.write(md + "\n")

    print(md)

    has_unsuitable = any(not r.suitable_for_production for r in results)
    return 1 if (fail_on_unsuitable and has_unsuitable) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate monitor source health and parseability.")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--output-json", default="data/source_validation_report.json")
    parser.add_argument("--output-md", default="data/source_validation_report.md")
    parser.add_argument("--fail-on-unsuitable", action="store_true")
    args = parser.parse_args()

    raise SystemExit(
        run(
            config_path=args.config,
            output_json=args.output_json,
            output_md=args.output_md,
            fail_on_unsuitable=args.fail_on_unsuitable,
        )
    )


if __name__ == "__main__":
    main()
