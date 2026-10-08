#!/usr/bin/env python3
"""fetch_trial_specs.py — pull registered protocol text for the 100 dev trials.

Writes data/trial_specs.jsonl, one JSON object per line, in the SAME ORDER and
with the same nct_ids as data/trials.jsonl, so the two files can be zipped
row-for-row.

Leakage policy (this is arm A; the environment is closed-book):
    overallStatus, whyStopped, startDate, completionDate and resultsSection all
    encode the outcome. Rather than fetch the full record and strip them, this
    asks the API for only the modules it needs via `?fields=`, so the outcome-
    bearing fields never cross the network, never reach the cache, and never
    reach disk. That follows prepare_data.py: drop at the source, so a later
    edit downstream cannot reintroduce the leak by reading a cached copy.

    Every module below is protocol/registration-time content. statusModule --
    which holds overallStatus, whyStopped and all three date structs -- is
    deliberately absent from FIELDS, as are the top-level `hasResults` flag and
    `resultsSection`. A guard re-checks the extracted output for forbidden keys
    before anything is written.

No credential is required by this API. If one is ever needed, read it from
os.environ; never hardcode one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROWS = PROJECT_ROOT / "data" / "trials.jsonl"
DEFAULT_OUT = PROJECT_ROOT / "data" / "trial_specs.jsonl"
DEFAULT_CACHE = PROJECT_ROOT / "data" / "ctg_cache"

API_URL = "https://clinicaltrials.gov/api/v2/studies/{nct_id}"
REQUEST_DELAY_SECONDS = 1.0
TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3

# Only these modules are requested. statusModule is omitted on purpose.
FIELDS = ",".join(
    f"protocolSection.{module}"
    for module in (
        "identificationModule",
        "sponsorCollaboratorsModule",
        "descriptionModule",
        "conditionsModule",
        "designModule",
        "armsInterventionsModule",
        "outcomesModule",
        "eligibilityModule",
    )
)

# Any of these appearing anywhere in a cached or extracted object is a leak.
FORBIDDEN_KEYS = {
    "overallstatus",
    "whystopped",
    "startdate",
    "startdatestruct",
    "completiondate",
    "completiondatestruct",
    "primarycompletiondate",
    "primarycompletiondatestruct",
    "resultssection",
    "hasresults",
    "statusmodule",
    "lastknownstatus",
}


def find_forbidden(obj, path: str = "") -> list[str]:
    """Every forbidden key found anywhere in a nested structure."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else key
            if key.lower() in FORBIDDEN_KEYS:
                hits.append(here)
            hits.extend(find_forbidden(value, here))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            hits.extend(find_forbidden(item, f"{path}[{i}]"))
    return hits


def api_key_headers() -> dict[str, str]:
    """No credential is needed today; honour one from the environment if set."""
    token = os.environ.get("CTG_API_KEY")
    return {"Authorization": f"Bearer {token}"} if token else {}


def fetch(nct_id: str, cache_dir: Path, session: requests.Session) -> tuple[dict | None, str]:
    """(record, provenance) for one NCT. provenance is 'cache' | 'api' | 'error: ...'."""
    cache_path = cache_dir / f"{nct_id}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text()), "cache"
        except json.JSONDecodeError:
            cache_path.unlink()  # corrupt cache entry; refetch below

    last_error = "unknown"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(
                API_URL.format(nct_id=nct_id),
                params={"fields": FIELDS, "format": "json"},
                timeout=TIMEOUT_SECONDS,
                headers=api_key_headers(),
            )
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}"
            time.sleep(REQUEST_DELAY_SECONDS * attempt)
            continue
        if response.status_code == 200:
            record = response.json()
            leaks = find_forbidden(record)
            if leaks:
                # The field filter should make this impossible. If the API ever
                # returns an outcome-bearing key anyway, refuse to cache it.
                return None, f"error: response carried forbidden keys {leaks[:3]}"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(record, indent=1))
            return record, "api"
        if response.status_code == 404:
            return None, "error: 404 not found"
        last_error = f"HTTP {response.status_code}"
        time.sleep(REQUEST_DELAY_SECONDS * attempt)
    return None, f"error: {last_error}"


def text(value) -> str:
    return (value or "").strip() if isinstance(value, str) else ""


def extract(nct_id: str, record: dict) -> dict:
    """The requested protocol fields, flattened. No outcome-bearing field is read."""
    protocol = record.get("protocolSection") or {}
    description = protocol.get("descriptionModule") or {}
    conditions = protocol.get("conditionsModule") or {}
    design = protocol.get("designModule") or {}
    design_info = design.get("designInfo") or {}
    masking_info = design_info.get("maskingInfo") or {}
    arms_module = protocol.get("armsInterventionsModule") or {}
    outcomes = protocol.get("outcomesModule") or {}
    eligibility = protocol.get("eligibilityModule") or {}
    sponsor = (protocol.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}

    def outcome_list(key: str) -> list[dict]:
        return [
            {
                "measure": text(item.get("measure")),
                "timeFrame": text(item.get("timeFrame")),
            }
            for item in (outcomes.get(key) or [])
            if text(item.get("measure"))
        ]

    arm_groups = [
        {
            "label": text(arm.get("label")),
            "type": text(arm.get("type")),
            "description": text(arm.get("description")),
        }
        for arm in (arms_module.get("armGroups") or [])
    ]
    interventions = [
        {
            "name": text(item.get("name")),
            "type": text(item.get("type")),
            "description": text(item.get("description")),
        }
        for item in (arms_module.get("interventions") or [])
    ]

    return {
        "nct_id": nct_id,
        "briefSummary": text(description.get("briefSummary")),
        "detailedDescription": text(description.get("detailedDescription")),
        "eligibilityCriteria": text(eligibility.get("eligibilityCriteria")),
        "sex": text(eligibility.get("sex")),
        "minimumAge": text(eligibility.get("minimumAge")),
        "maximumAge": text(eligibility.get("maximumAge")),
        # Only the count. `enrollmentInfo.type` (ACTUAL vs ESTIMATED) is left out:
        # it hints at whether enrolment ever finished, which brushes against the
        # outcome, and the inventory does not need it.
        "enrollmentCount": design.get("enrollmentInfo", {}).get("count"),
        "armGroups": arm_groups,
        "interventions": interventions,
        "primaryOutcomes": outcome_list("primaryOutcomes"),
        "secondaryOutcomes": outcome_list("secondaryOutcomes"),
        "allocation": text(design_info.get("allocation")),
        "interventionModel": text(design_info.get("interventionModel")),
        "masking": text(masking_info.get("masking")),
        "phases": design.get("phases") or [],
        "conditions": conditions.get("conditions") or [],
        "leadSponsor": text(sponsor.get("name")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=Path, default=DEFAULT_ROWS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()

    nct_ids = [
        json.loads(line)["nct_id"]
        for line in args.rows.read_text().splitlines()
        if line.strip()
    ]
    print(f"{len(nct_ids)} trials to fetch (order taken from {args.rows.name})")

    session = requests.Session()
    session.headers.update({"User-Agent": "clinical-trial-reasoning/0.1 (research)"})

    specs: list[dict] = []
    failures: list[tuple[str, str]] = []
    from_cache = from_api = 0

    for i, nct_id in enumerate(nct_ids, 1):
        record, provenance = fetch(nct_id, args.cache, session)
        if record is None:
            failures.append((nct_id, provenance))
            print(f"  [{i:>3}/{len(nct_ids)}] {nct_id}  FAILED  {provenance}")
            continue
        if provenance == "api":
            from_api += 1
            # Politeness delay only after a real network call.
            time.sleep(REQUEST_DELAY_SECONDS)
        else:
            from_cache += 1
        specs.append(extract(nct_id, record))
        if i % 20 == 0 or i == len(nct_ids):
            print(f"  [{i:>3}/{len(nct_ids)}] {nct_id}  ok ({provenance})")

    # Leakage guard on everything about to be written.
    leaks = find_forbidden(specs)
    if leaks:
        raise SystemExit(f"leakage guard: forbidden keys in output {leaks[:5]}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        for spec in specs:
            fh.write(json.dumps(spec) + "\n")

    print("\nSUMMARY")
    print(f"  requested        : {len(nct_ids)}")
    print(f"  succeeded        : {len(specs)}  (api {from_api}, cache {from_cache})")
    print(f"  failed           : {len(failures)}")
    for nct_id, reason in failures:
        print(f"      {nct_id}  {reason}")
    print(f"  leakage guard    : clean (no forbidden keys in {len(specs)} rows)")
    print(f"  written          : {args.out}")
    print(f"  cache            : {args.cache}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
