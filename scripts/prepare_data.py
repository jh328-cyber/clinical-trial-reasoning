#!/usr/bin/env python3
"""prepare_data.py — build the closed-book task rows for the reasoning environment.

Reads the frozen train/val splits from the prior labeling pipeline, joins each
NCT against that pipeline's cached ClinicalTrials.gov record, and writes one
JSON object per line to data/trials.jsonl.

Leakage policy (arm A is closed-book):
    The cached CTG record contains overall_status, why_stopped, has_results and
    the results-section flags. Those encode the answer, so ONLY the fields in
    ALLOWED_OUTPUT_FIELDS are ever written. Anything else is dropped here rather
    than filtered downstream, so a leak cannot be introduced by a later edit to
    the taskset.

The test split is deliberately not read: it stays held out.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path.home() / "clinical_data_llm_prediction"
DEFAULT_OUT = PROJECT_ROOT / "data" / "trials.jsonl"

SPLITS = ("train", "val")

# Batch output directories that carry a per-trial ctg.json, newest first.
CTG_BATCH_DIRS = ("batch_n11_b3", "batch_n9")

# The only keys allowed into trials.jsonl. See the leakage policy above.
ALLOWED_OUTPUT_FIELDS = {
    "nct_id",
    "label",
    "phase",
    "indication",
    "sponsor",
    "drug_name",
    "trial_title",
    "primary_endpoint",
    "split",
}

# Joins multiple registered primary outcomes into one field.
ENDPOINT_JOINER = " | "

DRUG_INTERVENTION_TYPES = {"DRUG", "BIOLOGICAL"}


def load_splits(source: Path) -> list[dict]:
    """The frozen split rows (nct_id, label, phase), tagged with their split."""
    rows: list[dict] = []
    for split in SPLITS:
        path = source / "data" / "processed" / "opt_03_dataset" / f"{split}.json"
        if not path.exists():
            raise SystemExit(f"split file not found: {path}")
        for row in json.loads(path.read_text()):
            rows.append({**row, "split": split})
    return rows


def find_ctg(source: Path, nct_id: str) -> tuple[dict | None, str | None]:
    """The cached CTG record for one NCT, and which batch dir it came from."""
    for batch in CTG_BATCH_DIRS:
        path = source / "data" / "processed" / batch / nct_id / "ctg.json"
        if path.exists():
            return json.loads(path.read_text()), batch
    return None, None


def extract_drug_name(ctg: dict) -> str:
    """The first DRUG/BIOLOGICAL intervention name, else the first of any type."""
    interventions = ctg.get("interventions") or []
    for item in interventions:
        if (item.get("type") or "").upper() in DRUG_INTERVENTION_TYPES:
            name = (item.get("name") or "").strip()
            if name:
                return name
    for item in interventions:
        name = (item.get("name") or "").strip()
        if name:
            return name
    return "unknown"


def extract_indication(ctg: dict) -> str:
    conditions = [c.strip() for c in (ctg.get("conditions") or []) if c and c.strip()]
    return "; ".join(conditions) if conditions else "unknown"


def extract_title(ctg: dict) -> str:
    """Prefer the brief title: shorter, and less likely to restate the design."""
    for key in ("brief_title", "official_title"):
        value = (ctg.get(key) or "").strip()
        if value:
            return value
    return "unknown"


def extract_primary_endpoint(ctg: dict) -> str:
    """The registered primary outcome measure(s), joined.

    The cached record is already flattened, so this reads `primary_outcomes[].measure`
    rather than the raw API's `protocolSection.outcomesModule.primaryOutcomes`. Only
    the measure is taken: it says WHAT was to be measured, never what the result was.
    """
    measures = [
        (outcome.get("measure") or "").strip()
        for outcome in (ctg.get("primary_outcomes") or [])
    ]
    return ENDPOINT_JOINER.join(m for m in measures if m)


def build_record(split_row: dict, ctg: dict) -> dict:
    record = {
        "nct_id": split_row["nct_id"],
        "label": split_row["label"],
        "phase": split_row.get("phase") or "unknown",
        "indication": extract_indication(ctg),
        "sponsor": (ctg.get("lead_sponsor") or "unknown").strip() or "unknown",
        "drug_name": extract_drug_name(ctg),
        "trial_title": extract_title(ctg),
        "primary_endpoint": extract_primary_endpoint(ctg),
        "split": split_row["split"],
    }
    leaked = set(record) - ALLOWED_OUTPUT_FIELDS
    if leaked:
        raise RuntimeError(f"leakage guard: unexpected output fields {sorted(leaked)}")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    split_rows = load_splits(args.source)
    records: list[dict] = []
    missing: list[str] = []
    provenance: dict[str, int] = {}

    for row in split_rows:
        ctg, batch = find_ctg(args.source, row["nct_id"])
        if ctg is None:
            missing.append(row["nct_id"])
            continue
        provenance[batch] = provenance.get(batch, 0) + 1
        records.append(build_record(row, ctg))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")

    unknown_drug = sum(1 for r in records if r["drug_name"] == "unknown")
    unknown_indication = sum(1 for r in records if r["indication"] == "unknown")
    labels: dict[str, int] = {}
    phases: dict[str, int] = {}
    for r in records:
        labels[r["label"]] = labels.get(r["label"], 0) + 1
        phases[r["phase"]] = phases.get(r["phase"], 0) + 1

    print("SUMMARY")
    print(f"  split rows read      : {len(split_rows)} ({', '.join(SPLITS)})")
    print(f"  ctg.json matched     : {len(records)}")
    print(f"  ctg.json missing     : {len(missing)}{' ' + str(missing[:5]) if missing else ''}")
    print(f"  ctg provenance       : {provenance}")
    print(f"  labels               : {labels}")
    print(f"  phases               : {phases}")
    no_endpoint = sum(1 for r in records if not r["primary_endpoint"])
    print(f"  drug_name unknown    : {unknown_drug}")
    print(f"  indication unknown   : {unknown_indication}")
    print(f"  primary_endpoint set : {len(records) - no_endpoint}/{len(records)}")
    print(f"  written              : {args.out}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
