#!/usr/bin/env python3
"""analyze_rollouts.py — statistics across repeated rollouts of the same trials.

Single-rollout runs of this environment are too noisy to read: with n=60 the S6
accuracy of unchanged code moved 56.7% -> 70.0% across four runs, and the S1->S6
relationship reversed sign. This script consumes a `-r K` run and reports intervals
and a permutation test instead of point estimates.

Stdlib only — no numpy/scipy in the eval venv.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

REWARDS = [
    "s1_trial_recall",
    "s2_reference_class",
    "s3_base_rate",
    "s4_success_criteria",
    "s5_risk_factors",
    "s6_outcome",
]
PERMUTATIONS = 20000
BOOTSTRAP = 20000
SEED = 2026


EXPECTED_STEPS = 6


def load(run_dir: Path) -> tuple[list[dict], list[dict]]:
    """(complete, incomplete) traces.

    An episode killed mid-chain by a provider error still carries rewards, all
    scored 0.0 because the replies are missing. Averaging those in would report
    infrastructure failure as model failure, so they are separated here and only
    complete chains are analysed.
    """
    path = run_dir / "traces.jsonl"
    if not path.exists():
        raise SystemExit(f"no traces.jsonl in {run_dir}")
    traces = []
    for line in path.read_text().splitlines():
        if line.strip():
            traces.extend(json.loads(line).get("traces", []))
    complete, incomplete = [], []
    for trace in traces:
        sampled = sum(1 for n in trace.get("nodes", []) if n.get("sampled"))
        (complete if sampled == EXPECTED_STEPS else incomplete).append(trace)
    return complete, incomplete


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — behaves near 0 and 1 where the normal one does not."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def bootstrap_ci(values: list[float], rng: random.Random) -> tuple[float, float]:
    """Percentile bootstrap CI for a mean."""
    if not values:
        return (0.0, 0.0)
    n = len(values)
    means = sorted(
        sum(rng.choice(values) for _ in range(n)) / n for _ in range(BOOTSTRAP)
    )
    return (means[int(0.025 * BOOTSTRAP)], means[int(0.975 * BOOTSTRAP)])


def cluster_bootstrap_ci(
    by_trial: dict[str, list[float]], rng: random.Random
) -> tuple[float, float]:
    """Bootstrap resampling TRIALS, not episodes.

    The 300 episodes are 5 correlated draws on each of 60 trials; treating them as
    independent understates the interval. Resampling whole trials respects that.
    """
    keys = list(by_trial)
    means = []
    for _ in range(BOOTSTRAP):
        picked = [rng.choice(keys) for _ in keys]
        values = [v for k in picked for v in by_trial[k]]
        means.append(sum(values) / len(values))
    means.sort()
    return (means[int(0.025 * BOOTSTRAP)], means[int(0.975 * BOOTSTRAP)])


def permutation_p(a: list[float], b: list[float], rng: random.Random) -> float:
    """Two-sided permutation test on the difference of means."""
    observed = abs(st.mean(a) - st.mean(b))
    pool = a + b
    cut = len(a)
    hits = 0
    for _ in range(PERMUTATIONS):
        rng.shuffle(pool)
        if abs(st.mean(pool[:cut]) - st.mean(pool[cut:])) >= observed - 1e-12:
            hits += 1
    return (hits + 1) / (PERMUTATIONS + 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--rows",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "trials.jsonl",
    )
    args = parser.parse_args()
    rng = random.Random(SEED)

    meta = {}
    for line in args.rows.read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            meta[record["nct_id"]] = record

    traces, dropped = load(args.run_dir)
    error_types: dict[str, int] = defaultdict(int)
    for trace in dropped:
        for err in trace.get("errors") or []:
            error_types[str(err.get("type"))] += 1

    s6_by_trial: dict[str, list[float]] = defaultdict(list)
    s1_by_trial: dict[str, list[float]] = defaultdict(list)
    reward_values: dict[str, list[float]] = defaultdict(list)
    reward_by_trial: dict[str, dict[str, list[float]]] = {r: defaultdict(list) for r in REWARDS}
    base_rate_by_phase: dict[str, list[float]] = defaultdict(list)

    for trace in traces:
        nct = (trace.get("task") or {}).get("data", {}).get("nct_id")
        rewards = trace.get("rewards") or {}
        for name in REWARDS:
            entry = rewards.get(name)
            if entry is not None:
                reward_values[name].append(entry["score"])
                reward_by_trial[name][nct].append(entry["score"])
        if "s6_outcome" in rewards:
            s6_by_trial[nct].append(rewards["s6_outcome"]["score"])
        if "s1_trial_recall" in rewards:
            s1_by_trial[nct].append(rewards["s1_trial_recall"]["score"])
        rate = (trace.get("metrics") or {}).get("s3_stated_base_rate")
        if rate is not None and rate >= 0:
            base_rate_by_phase[meta.get(nct, {}).get("phase", "?")].append(rate)

    episodes = len(traces)
    covered = len(s6_by_trial)
    print(f"RUN {args.run_dir.name}")
    print(f"  complete episodes  {episodes}  ·  dropped mid-chain {len(dropped)}")
    if error_types:
        print(f"  drop causes        {dict(error_types)}")
    print(f"  trials analysed    {covered}/{len(meta)}  "
          f"({len(meta) - covered} lost every rollout)")
    counts: dict[int, int] = defaultdict(int)
    for values in s6_by_trial.values():
        counts[len(values)] += 1
    print(f"  rollouts per trial {dict(sorted(counts.items()))}")
    analysed = {n for n in s6_by_trial}
    for field in ("label", "phase"):
        kept: dict[str, int] = defaultdict(int)
        lost: dict[str, int] = defaultdict(int)
        for nct, row in meta.items():
            (kept if nct in analysed else lost)[row.get(field, "?")] += 1
        print(f"  {field:<18} kept {dict(sorted(kept.items()))}  "
              f"lost {dict(sorted(lost.items()))}")

    # --- 1. S6 accuracy with intervals -----------------------------------
    s6_all = reward_values["s6_outcome"]
    correct = int(sum(s6_all))
    lo_w, hi_w = wilson(correct, len(s6_all))
    lo_c, hi_c = cluster_bootstrap_ci(s6_by_trial, rng)
    print("\n1. S6 ACCURACY")
    print(f"   mean                       {st.mean(s6_all):.3f}  ({correct}/{len(s6_all)})")
    print(f"   95% Wilson (episodes)      [{lo_w:.3f}, {hi_w:.3f}]   <- assumes independence")
    print(f"   95% bootstrap (by trial)   [{lo_c:.3f}, {hi_c:.3f}]   <- the honest one")

    # --- 1b. S6 broken down ------------------------------------------------
    print("\n1b. S6 ACCURACY BY SUBGROUP (Wilson CI over episodes)")
    for field in ("label", "phase", "split"):
        groups: dict[str, list[float]] = defaultdict(list)
        for nct, values in s6_by_trial.items():
            groups[meta.get(nct, {}).get(field, "?")].extend(values)
        print(f"   by {field}:")
        for key in sorted(groups):
            values = groups[key]
            hits = int(sum(values))
            lo, hi = wilson(hits, len(values))
            print(f"     {key:<10} {hits:>3}/{len(values):<4} {st.mean(values):.3f}"
                  f"   [{lo:.3f}, {hi:.3f}]")
    held_out = [v for nct, values in s6_by_trial.items()
                if meta.get(nct, {}).get("split") == "test" for v in values]
    seen = [v for nct, values in s6_by_trial.items()
            if meta.get(nct, {}).get("split") in ("train", "val") for v in values]
    if held_out and seen:
        p = permutation_p(list(held_out), list(seen), rng)
        print(f"   test vs train+val: {st.mean(held_out):.3f} vs {st.mean(seen):.3f}"
              f"  (diff {st.mean(held_out) - st.mean(seen):+.3f}, permutation p {p:.4f})")

    # --- 2. per-trial consistency ----------------------------------------
    print("\n2. PER-TRIAL CONSISTENCY (agreement of the 5 rollouts)")
    buckets: dict[str, int] = defaultdict(int)
    disagreement = []
    for nct, values in s6_by_trial.items():
        n = len(values)
        majority = max(sum(values), n - sum(values))
        buckets[f"{int(majority)}/{n}"] += 1
        disagreement.append((majority / n, nct, sum(values), n))
    for key in sorted(buckets, reverse=True):
        print(f"   {key} agree : {buckets[key]:>3} trials")
    print("   least consistent trials:")
    for _, nct, correct_n, n in sorted(disagreement)[:5]:
        row = meta.get(nct, {})
        print(f"     {nct}  {int(correct_n)}/{n} correct  "
              f"[{row.get('label','?'):<7} {row.get('phase','?'):<7}] "
              f"{(row.get('trial_title') or '')[:52]}")

    # --- 3. S1 -> S6 --------------------------------------------------------
    print("\n3. S1 RECALL -> S6 ACCURACY (per trial, averaged over rollouts)")
    remembered, forgotten = [], []
    for nct, s1_values in s1_by_trial.items():
        s6_mean = st.mean(s6_by_trial[nct])
        (remembered if st.mean(s1_values) > 0.5 else forgotten).append(s6_mean)
    print(f"   remembered (S1 > 0.5)  n={len(remembered):<3} S6 mean {st.mean(remembered):.3f}"
          if remembered else "   remembered: none")
    print(f"   forgotten  (S1 <= 0.5) n={len(forgotten):<3} S6 mean {st.mean(forgotten):.3f}"
          if forgotten else "   forgotten: none")
    if remembered and forgotten:
        diff = st.mean(remembered) - st.mean(forgotten)
        p = permutation_p(list(remembered), list(forgotten), rng)
        print(f"   difference             {diff:+.3f}")
        print(f"   permutation p          {p:.4f}  ({PERMUTATIONS} shuffles)")
        print(f"   verdict                {'significant at 0.05' if p < 0.05 else 'NOT significant'}")

    # --- 4. per-step reward stability ---------------------------------------
    print("\n4. PER-STEP REWARD (95% bootstrap CI over trials)")
    print(f"   {'reward':<22}{'mean':>7}{'95% CI':>22}{'width':>8}")
    for name in REWARDS:
        values = reward_values[name]
        lo, hi = cluster_bootstrap_ci(reward_by_trial[name], rng)
        print(f"   {name:<22}{st.mean(values):>7.3f}   [{lo:.3f}, {hi:.3f}]{hi - lo:>10.3f}")

    # --- 5. S3 calibration by phase ------------------------------------------
    print("\n5. S3 STATED BASE RATE BY PHASE")
    targets = {"PHASE1": 0.52, "PHASE2": 0.29, "PHASE3": 0.58}
    print(f"   {'phase':<10}{'n':>5}{'mean':>8}{'std':>8}{'median':>8}{'target':>9}{'error':>8}")
    for phase in sorted(base_rate_by_phase):
        values = base_rate_by_phase[phase]
        target = targets.get(phase, float("nan"))
        std = st.stdev(values) if len(values) > 1 else 0.0
        print(f"   {phase:<10}{len(values):>5}{st.mean(values):>8.3f}{std:>8.3f}"
              f"{st.median(values):>8.3f}{target:>9.2f}{st.mean(values) - target:>+8.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
