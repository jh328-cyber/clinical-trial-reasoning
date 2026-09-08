#!/usr/bin/env python3
"""analyze_run.py — per-step breakdown of an eval run's traces.jsonl.

Reports what the aggregate reward line cannot: accuracy by label and phase, the
S1 recall score stratified by whether the drug name was already visible in the
title, and the S2 reference-class NCT IDs (optionally resolved against
ClinicalTrials.gov to separate well-formed from real).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

NCT_RE = re.compile(r"NCT\d{8}")
CTG_URL = "https://clinicaltrials.gov/api/v2/studies/{}?fields=NCTId"


def load_traces(run_dir: Path) -> list[dict]:
    path = run_dir / "traces.jsonl"
    if not path.exists():
        raise SystemExit(f"no traces.jsonl in {run_dir}")
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        episode = json.loads(line)
        for trace in episode.get("traces", []):
            rows.append(trace)
    return rows


def reward(trace: dict, name: str) -> float | None:
    entry = (trace.get("rewards") or {}).get(name)
    return None if entry is None else entry.get("score")


def s2_ids(trace: dict) -> list[str]:
    """NCT IDs from the second sampled assistant message."""
    sampled = [n["message"] for n in trace.get("nodes", []) if n.get("sampled")]
    if len(sampled) < 2:
        return []
    return sorted(set(NCT_RE.findall(sampled[1].get("content") or "")))


def nct_exists(nct_id: str, timeout: float = 15.0) -> bool | None:
    """True/False if the registry answered, None if the lookup itself failed."""
    try:
        with urllib.request.urlopen(CTG_URL.format(nct_id), timeout=timeout) as fh:
            return fh.status == 200
    except urllib.error.HTTPError as exc:
        return False if exc.code == 404 else None
    except Exception:
        return None


def pct(numerator: float, denominator: float) -> str:
    return f"{numerator / denominator:.1%}" if denominator else "n/a"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--rows", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data" / "trials.jsonl")
    parser.add_argument("--verify-ncts", type=int, default=0,
                        help="Sample this many S2 NCT IDs and resolve them against CTG.")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    meta = {}
    for line in args.rows.read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            meta[record["nct_id"]] = record

    traces = load_traces(args.run_dir)
    by_label: dict[str, list[float]] = defaultdict(list)
    by_phase: dict[str, list[float]] = defaultdict(list)
    s1_split: dict[bool, list[float]] = defaultdict(list)
    all_ids: list[str] = []
    per_trial_ids: list[int] = []
    predicted_success = 0
    parsed = 0

    for trace in traces:
        nct = (trace.get("task") or {}).get("data", {}).get("nct_id")
        row = meta.get(nct, {})
        correct = reward(trace, "s6_outcome")
        metrics = trace.get("metrics") or {}
        if correct is not None:
            by_label[row.get("label", "?")].append(correct)
            by_phase[row.get("phase", "?")].append(correct)
        s1 = reward(trace, "s1_trial_recall")
        if s1 is not None:
            s1_split[bool(metrics.get("drug_name_in_title"))].append(s1)
        ids = s2_ids(trace)
        all_ids.extend(ids)
        per_trial_ids.append(len(ids))
        predicted_success += int(metrics.get("s6_predicted_success") or 0)
        parsed += int(metrics.get("s6_parsed") or 0)

    n = len(traces)
    correct_all = [v for values in by_label.values() for v in values]
    print(f"RUN {args.run_dir.name}")
    print(f"  traces                 : {n}")
    print(f"  S6 parsed              : {parsed}/{n}")
    print(f"  S6 accuracy            : {sum(correct_all):.0f}/{len(correct_all)} "
          f"({pct(sum(correct_all), len(correct_all))})")
    print(f"  predicted SUCCESS      : {predicted_success}/{n} ({pct(predicted_success, n)})")
    print("  accuracy by true label :")
    for label, values in sorted(by_label.items()):
        print(f"      {label:<8} {sum(values):.0f}/{len(values)}  ({pct(sum(values), len(values))})")
    print("  accuracy by phase      :")
    for phase, values in sorted(by_phase.items()):
        print(f"      {phase:<8} {sum(values):.0f}/{len(values)}  ({pct(sum(values), len(values))})")

    print("  S1 recall (drug named) :")
    for visible, values in sorted(s1_split.items()):
        tag = "drug IN title (copyable)" if visible else "drug NOT in title (real recall)"
        print(f"      {tag:<32} {sum(values):.0f}/{len(values)}  ({pct(sum(values), len(values))})")

    unique = sorted(set(all_ids))
    print("  S2 reference class     :")
    print(f"      NCT IDs emitted (total / unique) : {len(all_ids)} / {len(unique)}")
    print(f"      per trial: mean {sum(per_trial_ids)/n:.2f}, "
          f"min {min(per_trial_ids)}, max {max(per_trial_ids)}, "
          f"zero-ID trials {sum(1 for c in per_trial_ids if c == 0)}")

    if args.verify_ncts and unique:
        random.seed(args.seed)
        sample = random.sample(unique, min(args.verify_ncts, len(unique)))
        real = sum(1 for i in sample if nct_exists(i) is True)
        failed = sum(1 for i in sample if nct_exists(i) is None)
        print(f"      registry check on {len(sample)} sampled IDs: "
              f"{real} resolve, {len(sample) - real} do not "
              f"({pct(len(sample) - real, len(sample))} fabricated)"
              + (f"; {failed} lookups errored" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
