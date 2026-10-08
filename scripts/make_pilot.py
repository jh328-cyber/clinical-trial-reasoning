#!/usr/bin/env python3
"""make_pilot.py — pick a small, balanced trial subset for a pilot run and write
spec-mode input files restricted to it.

Picks N trials (default 20) balanced 50/50 SUCCESS/FAILURE and spread across
phases, deterministically (seeded). Writes:
  data/pilot_baseline_specs_v0.jsonl   (N rows)
  data/pilot_perturbed_specs_v0.jsonl  (all perturbed cases on those N trials)
Both are subsets of the full files, so perturbed_specs_v0.map.jsonl still joins.

Usage: python3 scripts/make_pilot.py [--n 20] [--seed 0]
"""
import argparse, json, random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=20); ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()

trials = [json.loads(l) for l in (ROOT/"data/trials.jsonl").read_text().splitlines() if l.strip()]
buckets = defaultdict(list)
for t in trials: buckets[(t["phase"], t["label"])].append(t["nct_id"])
rng = random.Random(a.seed)
for k in buckets: rng.shuffle(buckets[k])
keys = sorted(buckets); chosen = []
while len(chosen) < a.n and any(buckets[k] for k in keys):
    for k in keys:                      # round-robin across (phase,label) cells
        if buckets[k] and len(chosen) < a.n: chosen.append(buckets[k].pop())
chosen = set(chosen)

base = [json.loads(l) for l in (ROOT/"data/baseline_specs_v0.jsonl").read_text().splitlines() if l.strip()]
pert = [json.loads(l) for l in (ROOT/"data/perturbed_specs_v0.jsonl").read_text().splitlines() if l.strip()]
pb = [r for r in base if r["spec"]["nct_id"] in chosen]
pp = [r for r in pert if r["spec"]["nct_id"] in chosen]
(ROOT/"data/pilot_baseline_specs_v0.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in pb))
(ROOT/"data/pilot_perturbed_specs_v0.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in pp))
lab = {t["nct_id"]: (t["phase"], t["label"]) for t in trials}
from collections import Counter
print("pilot trials:", len(pb), dict(Counter(lab[n] for n in chosen)))
print("pilot perturbed cases:", len(pp))
print("wrote data/pilot_baseline_specs_v0.jsonl, data/pilot_perturbed_specs_v0.jsonl")
