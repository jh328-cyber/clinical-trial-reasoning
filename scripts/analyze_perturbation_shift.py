#!/usr/bin/env python3
"""analyze_perturbation_shift.py — how does the model's answer move when one
perturbation is applied to a trial specification?

Inputs (all produced earlier):
  results/spec/<model>/<baseline-run>/traces.jsonl    unperturbed specs (arm B)
  results/spec/<model>/<perturbed-run>/traces.jsonl   perturbed specs (arm B)
  data/perturbed_specs_v0.map.jsonl                   row_id -> case_id
  docs/perturbations/perturbations_v0.json            catalogue (expected direction, expert label)

For every perturbed case we join to the same trial's baseline rollout and compute:
  * prediction shift  dP = P(SUCCESS | perturbed) - P(SUCCESS | baseline),
                      where P(SUCCESS) = CONFIDENCE if PREDICTION is SUCCESS else 1 - CONFIDENCE
  * flip              did PREDICTION change?
  * direction agreement with expected_direction (and expert_label once filled):
                      harmful -> dP < -TOL, helpful -> dP > +TOL, neutral -> |dP| <= TOL
  * reasoning shift   per step S2..S5, 1 - Jaccard(word set baseline reply, word set perturbed reply)
  * signal pickup     fraction of the inserted sentence's content words that appear in the S5 reply
                      (did the model's risk list actually mention the signal we added?)

Outputs:
  <out-dir>/perturbation_shift_cases.csv    one row per perturbed case
  <out-dir>/perturbation_shift_report.md    per-perturbation and per-category tables
  stdout: the per-perturbation table

Usage (from repo root):
  python3 scripts/analyze_perturbation_shift.py \\
      --baseline results/spec/deepseek-chat/pilot_baseline/traces.jsonl \\
      --perturbed results/spec/deepseek-chat/pilot_perturbed/traces.jsonl \\
      --out-dir results/spec/deepseek-chat
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOL = 0.05          # |dP| <= TOL counts as "no meaningful movement"
STEP_NAMES = ["s1_recall", "s2_reference", "s3_base_rate", "s4_criteria", "s5_risks", "s6_outcome"]
STOP = set("""a an the and or of to in on for with by from at as is are was were be been being this that these those
it its into over under than then there here which who whom whose what when where why how not no nor all any each
both few more most other some such only own same so too very can will just should now during after before within
subjects subject patients patient study trial treatment treated dosing dose cohort preceding first within weeks
week days day initiation reported observed showed revealed data analysis identified""".split())


# ----------------------------------------------------------------------------- parsing

def load_traces(path: Path) -> list[dict]:
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        for tr in rec.get("traces", [rec]):
            out.append(tr)
    return out


def reply(tr: dict, step: str) -> str | None:
    """Assistant reply for a step. Nodes alternate user/assistant; assistant for step k is node 2k+1."""
    i = STEP_NAMES.index(step)
    nodes = tr.get("nodes") or []
    j = 2 * i + 1
    if j >= len(nodes):
        return None
    m = nodes[j].get("message") or {}
    if m.get("role") != "assistant":
        return None
    c = m.get("content")
    if isinstance(c, list):  # content blocks
        c = " ".join(b.get("text", "") for b in c if isinstance(b, dict))
    return c


def parse_s6(text: str | None) -> tuple[str | None, float | None]:
    if not text:
        return None, None
    t = text.upper()
    pred = None
    if "PREDICTION:" in t:
        line = t.split("PREDICTION:", 1)[1].split("\n", 1)[0]
        hs, hf = "SUCCESS" in line, "FAILURE" in line
        if hs != hf:
            pred = "SUCCESS" if hs else "FAILURE"
    conf = None
    m = re.search(r"CONFIDENCE:\s*([01](?:\.\d+)?|\.\d+)", t)
    if m:
        try:
            conf = float(m.group(1))
        except ValueError:
            pass
    return pred, conf


def p_success(pred: str | None, conf: float | None) -> float | None:
    if pred is None or conf is None:
        return None
    return conf if pred == "SUCCESS" else 1.0 - conf


def words(text: str | None) -> set[str]:
    return set(re.findall(r"[a-z][a-z\-]{2,}", (text or "").lower())) - STOP


def jaccard_distance(a: str | None, b: str | None) -> float | None:
    A, B = words(a), words(b)
    if not A and not B:
        return None
    return 1.0 - len(A & B) / len(A | B)


def content_words(text: str) -> set[str]:
    return {w for w in words(text) if len(w) >= 5}


# ----------------------------------------------------------------------------- main

def noise_floor(a_path: Path, b_path: Path) -> int:
    """Two baseline runs of the SAME trials, different samples. Everything that differs
    between them is sampling noise; this is the floor a perturbation effect must clear."""
    def by_nct(path):
        out = {}
        for tr in load_traces(path):
            d = tr["task"]["data"]
            pred, conf = parse_s6(reply(tr, "s6_outcome"))
            p = p_success(pred, conf)
            if p is not None:
                out[d["nct_id"]] = {"pred": pred, "conf": conf, "p": p, "replies": {s: reply(tr, s) for s in STEP_NAMES}}
        return out
    A, B = by_nct(a_path), by_nct(b_path)
    common = sorted(set(A) & set(B))
    if not common:
        print("no common trials"); return 1
    dps = [B[n]["p"] - A[n]["p"] for n in common]
    flips = [A[n]["pred"] != B[n]["pred"] for n in common]
    confs = [A[n]["conf"] for n in common] + [B[n]["conf"] for n in common]
    print(f"noise floor on {len(common)} trials (run A vs run B, same specs):")
    print(f"  flip rate             {100*st.mean(flips):.0f}%")
    print(f"  mean dP               {st.mean(dps):+.3f}   (regression-to-mean drift)")
    print(f"  mean |dP|             {st.mean(abs(x) for x in dps):.3f}")
    print(f"  share |dP| > {TOL}      {100*st.mean(abs(x) > TOL for x in dps):.0f}%")
    print(f"  dP range              {min(dps):+.2f} .. {max(dps):+.2f}")
    print(f"  CONFIDENCE values     min {min(confs):.2f}  median {st.median(confs):.2f}  max {max(confs):.2f}  "
          f"(distinct: {sorted(set(round(c,2) for c in confs))})")
    for step in STEP_NAMES[1:5]:
        js = [jaccard_distance(A[n]["replies"][step], B[n]["replies"][step]) for n in common]
        js = [j for j in js if j is not None]
        print(f"  {step:14s} shift  {st.mean(js):.2f}   (same prompt, two samples)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--perturbed", type=Path, required=False)
    ap.add_argument("--noise-floor", type=Path, default=None,
                    help="a second baseline run of the same trials; prints the sampling-noise floor and exits")
    ap.add_argument("--map", type=Path, default=ROOT / "data" / "perturbed_specs_v0.map.jsonl")
    ap.add_argument("--catalogue", type=Path, default=ROOT / "docs" / "perturbations" / "perturbations_v0.json")
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args()
    if a.noise_floor is not None:
        return noise_floor(a.baseline, a.noise_floor)
    if a.perturbed is None:
        ap.error("--perturbed is required unless --noise-floor is given")
    out_dir = a.out_dir or a.perturbed.parent.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    cat = {p["id"]: p for p in json.loads(a.catalogue.read_text())}
    row2case = {}
    for line in a.map.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            row2case[r["row_id"]] = r["case_id"]

    # ---- baseline: one rollout per nct_id ----
    base = {}
    n_base_bad = 0
    for tr in load_traces(a.baseline):
        d = tr["task"]["data"]
        pred, conf = parse_s6(reply(tr, "s6_outcome"))
        p = p_success(pred, conf)
        if p is None:
            n_base_bad += 1
            continue
        base[d["nct_id"]] = {"pred": pred, "conf": conf, "p": p, "label": d.get("label"), "phase": d.get("phase"),
                            "replies": {s: reply(tr, s) for s in STEP_NAMES}}

    # ---- perturbed cases ----
    rows = []
    skipped = defaultdict(int)
    for tr in load_traces(a.perturbed):
        d = tr["task"]["data"]
        rid = d.get("row_id", "")
        cid = row2case.get(rid)
        if cid is None:
            skipped["row_id not in map"] += 1
            continue
        nct, pid = cid.split("__", 1)
        if pid == "BASELINE" or pid not in cat:
            skipped["not a catalogue perturbation"] += 1
            continue
        b = base.get(nct)
        if b is None:
            skipped["no baseline rollout for trial"] += 1
            continue
        pred, conf = parse_s6(reply(tr, "s6_outcome"))
        p = p_success(pred, conf)
        if p is None:
            skipped["S6 unparseable"] += 1
            continue
        pert = cat[pid]
        s5 = reply(tr, "s5_risks") or ""
        cw = content_words(pert["perturbation_text"])
        pickup = (len(cw & words(s5)) / len(cw)) if cw else None
        shift = {s: jaccard_distance(b["replies"][s], reply(tr, s)) for s in STEP_NAMES[1:5]}
        rows.append({
            "case_id": cid, "nct_id": nct, "perturbation_id": pid, "type": pert["type"],
            "expected_direction": pert["expected_direction"], "expert_label": pert.get("yousef_label"),
            "label": b["label"], "phase": b["phase"],
            "pred_base": b["pred"], "conf_base": b["conf"], "p_base": round(b["p"], 3),
            "pred_pert": pred, "conf_pert": conf, "p_pert": round(p, 3),
            "dP": round(p - b["p"], 3), "flipped": int(pred != b["pred"]),
            "s2_shift": shift["s2_reference"], "s3_shift": shift["s3_base_rate"],
            "s4_shift": shift["s4_criteria"], "s5_shift": shift["s5_risks"],
            "s5_signal_pickup": None if pickup is None else round(pickup, 3),
        })

    if not rows:
        print("no joined cases; skipped:", dict(skipped))
        return 1

    # ---- per-perturbation aggregates ----
    def agrees(direction: str | None, dP: float) -> int | None:
        if direction == "harmful":
            return int(dP < -TOL)
        if direction == "helpful":
            return int(dP > TOL)
        if direction == "neutral":
            return int(abs(dP) <= TOL)
        return None

    by_p = defaultdict(list)
    for r in rows:
        by_p[r["perturbation_id"]].append(r)

    def agg(rs: list[dict]) -> dict:
        dps = [r["dP"] for r in rs]
        ag = [agrees(r["expected_direction"], r["dP"]) for r in rs]
        ex = [agrees(r["expert_label"], r["dP"]) for r in rs if r["expert_label"]]
        pk = [r["s5_signal_pickup"] for r in rs if r["s5_signal_pickup"] is not None]
        s5 = [r["s5_shift"] for r in rs if r["s5_shift"] is not None]
        return {
            "n": len(rs),
            "mean_dP": st.mean(dps), "median_dP": st.median(dps),
            "flip_rate": st.mean(r["flipped"] for r in rs),
            "toward_fail": st.mean(r["dP"] < -TOL for r in rs),
            "toward_success": st.mean(r["dP"] > TOL for r in rs),
            "agree_expected": st.mean(ag) if ag else None,
            "agree_expert": st.mean(ex) if ex else None,
            "s5_shift": st.mean(s5) if s5 else None,
            "s5_pickup": st.mean(pk) if pk else None,
        }

    per_p = {pid: agg(rs) for pid, rs in by_p.items()}
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["type"]].append(r)
    per_cat = {c: agg(rs) for c, rs in by_cat.items()}

    # ---- CSV ----
    csv_path = out_dir / "perturbation_shift_cases.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # ---- report ----
    def pct(x):
        return "—" if x is None else f"{100*x:.0f}%"

    L = []
    L.append(f"# Perturbation shift report — {a.perturbed.parent.parent.name} / {a.perturbed.parent.name}\n")
    L.append(f"Baseline rollouts: {len(base)} trials ({n_base_bad} with unparseable S6 dropped). "
             f"Perturbed cases joined: {len(rows)}. Skipped: {dict(skipped) or 'none'}.\n")
    L.append(f"dP = P(SUCCESS | perturbed) − P(SUCCESS | baseline). Tolerance for 'no movement': ±{TOL}. "
             f"'agree' = sign of dP matches the stated direction (harmful ⇒ dP < −{TOL}, helpful ⇒ dP > +{TOL}, neutral ⇒ |dP| ≤ {TOL}).\n")
    base_rate = st.mean(b["pred"] == "SUCCESS" for b in base.values())
    L.append(f"Baseline predicted-SUCCESS rate: {pct(base_rate)}; baseline S6 accuracy: "
             f"{pct(st.mean(b['pred'] == b['label'] for b in base.values()))}.\n")

    L.append("## Per perturbation\n")
    L.append("| ID | type | expected | n | mean dP | median dP | flip | → fail | → success | agree (expected) | agree (expert) | S5 reasoning shift | S5 mentions signal |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for pid in sorted(per_p):
        s = per_p[pid]; c = cat[pid]
        L.append(f"| {pid} | {c['type']} | {c['expected_direction']} | {s['n']} | {s['mean_dP']:+.3f} | {s['median_dP']:+.3f} | "
                 f"{pct(s['flip_rate'])} | {pct(s['toward_fail'])} | {pct(s['toward_success'])} | {pct(s['agree_expected'])} | "
                 f"{pct(s['agree_expert'])} | {'—' if s['s5_shift'] is None else f'{s['s5_shift']:.2f}'} | {pct(s['s5_pickup'])} |")

    L.append("\n## Per category\n")
    L.append("| type | n | mean dP | flip | → fail | → success | agree (expected) | S5 reasoning shift | S5 mentions signal |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for c in sorted(per_cat):
        s = per_cat[c]
        L.append(f"| {c} | {s['n']} | {s['mean_dP']:+.3f} | {pct(s['flip_rate'])} | {pct(s['toward_fail'])} | {pct(s['toward_success'])} | "
                 f"{pct(s['agree_expected'])} | {'—' if s['s5_shift'] is None else f'{s['s5_shift']:.2f}'} | {pct(s['s5_pickup'])} |")

    L.append("\n## Largest movers (mean dP)\n")
    order = sorted(per_p.items(), key=lambda kv: kv[1]["mean_dP"])
    L.append("Most toward FAILURE: " + ", ".join(f"{pid} ({s['mean_dP']:+.2f})" for pid, s in order[:5]))
    L.append("\nMost toward SUCCESS: " + ", ".join(f"{pid} ({s['mean_dP']:+.2f})" for pid, s in order[-5:][::-1]))

    L.append("\n## Reading guide\n")
    L.append("- A perturbation the model *reasons about* should show (a) dP in the stated direction, (b) a high S5 signal-mention rate, and (c) a non-trivial S5 reasoning shift.")
    L.append("- dP ≈ 0 with high S5 signal-mention = the model saw the signal, discussed it, and did not change its answer (reasoning–answer disconnect, as in arm A).")
    L.append("- dP ≈ 0 with low S5 signal-mention = the model did not pick the signal up at all.")
    L.append("- 'agree (expert)' fills in once expert_label is set in the catalogue; until then it is —.")

    rep = out_dir / "perturbation_shift_report.md"
    rep.write_text("\n".join(L) + "\n")

    # ---- stdout ----
    print(f"baseline trials: {len(base)}   perturbed cases joined: {len(rows)}   skipped: {dict(skipped) or 'none'}")
    print(f"baseline predicted-SUCCESS: {pct(base_rate)}\n")
    print(f"{'ID':5s} {'expected':9s} {'n':>3s} {'mean dP':>8s} {'flip':>5s} {'→fail':>6s} {'→succ':>6s} {'agree':>6s} {'S5shift':>8s} {'S5pick':>7s}")
    for pid in sorted(per_p):
        s = per_p[pid]
        print(f"{pid:5s} {cat[pid]['expected_direction']:9s} {s['n']:3d} {s['mean_dP']:+8.3f} {pct(s['flip_rate']):>5s} {pct(s['toward_fail']):>6s} "
              f"{pct(s['toward_success']):>6s} {pct(s['agree_expected']):>6s} {('—' if s['s5_shift'] is None else f'{s['s5_shift']:.2f}'):>8s} {pct(s['s5_pickup']):>7s}")
    print(f"\nwrote {csv_path}\nwrote {rep}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
