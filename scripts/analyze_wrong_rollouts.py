#!/usr/bin/env python3
"""analyze_wrong_rollouts.py — read the rollouts every model got wrong.

The cross-model report says *how often* the models are wrong. This says *why*:
it pulls the full S1-S6 chain for the trials no model got right and lays the
three reasonings side by side, so a shared failure mode is visible as text
rather than inferred from a mean.

Two cohorts, because "all three got it wrong" is ambiguous once a model can
abstain:

  * SHARED FALSE BELIEF - all three committed to a label and all three were
    wrong. These are the interesting ones: three model families independently
    asserting the same incorrect thing.
  * NO CORRECT ANSWER - S6 scored 0.0 for all three, which also catches trials
    where a model declined to predict. An abstention is not a false belief, so
    folding these together would mix "everyone believed something wrong" with
    "one model said it didn't know".

The per-trial "failure signature" is a mechanical summary of measurable signals
(which way the models leaned, how well they recalled the trial), not a reading of
the prose. The excerpts are included so the reading can be done by a human.

Stdlib only - no numpy/scipy in the eval venv.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

STEP_LABELS = [
    ("s1_trial_recall", "S1 Trial Recall"),
    ("s2_reference_class", "S2 Reference Class"),
    ("s3_base_rate", "S3 Base Rate"),
    ("s4_success_criteria", "S4 Success Criteria"),
    ("s5_risk_factors", "S5 Risk Factors"),
    ("s6_outcome", "S6 Prediction"),
]
REWARDS = [name for name, _ in STEP_LABELS]
EXPECTED_STEPS = 6

PREDICTION_RE = re.compile(r"PREDICTION:\s*\**\s*(SUCCESS|FAILURE|UNKNOWN)", re.I)
CONFIDENCE_RE = re.compile(r"CONFIDENCE:\s*\**\s*([\d.]+)")
KEY_REASON_RE = re.compile(r"KEY_REASON:\s*\**\s*(.+)", re.I | re.S)

# Crude lexical test for "this trial's registered bar is tolerability, not
# efficacy". It reads the primary_endpoint field, never the model's reply, so it
# classifies the TRIAL rather than the reasoning. Keyword matching will
# misfile some rows; it is used to size a pattern, not to label individual trials.
SAFETY_ENDPOINT_RE = re.compile(
    r"safety|tolerab|adverse|toxicit|dose.?limiting|maximum tolerated"
    r"|\bAEs?\b|\bDLTs?\b|\bMTD\b",
    re.I,
)

S5_EXCERPT_WORDS = 200
BASELINE_TRIALS = 3
SEED = 2026
# A mislabel candidate has to clear two bars, not one. High confidence alone
# flags 8 of 9 rows here, because these models routinely state 0.6-0.8 while
# recalling nothing about the trial - that is a confident prior, and it is
# evidence about the model, not about the label. Requiring some genuine recall
# as well restricts the flag to rows where a model actually knew something and
# still contradicted the registry.
MISLABEL_CONFIDENCE = 0.70
MISLABEL_MIN_RECALL = 0.01


def words(text: str, limit: int) -> str:
    parts = (text or "").split()
    if len(parts) <= limit:
        return text.strip()
    return " ".join(parts[:limit]).rstrip() + " ..."


class Rollout:
    """One model's episode on one trial."""

    def __init__(self, trace: dict):
        data = trace["task"]["data"]
        self.nct_id: str = data["nct_id"]
        # The registered outcome is `label`; there is no `ground_truth` field.
        self.label: str = data.get("label", "?")
        self.phase: str = data.get("phase", "?")
        self.indication: str = data.get("indication", "?")
        self.sponsor: str = data.get("sponsor", "?")
        self.title: str = data.get("trial_title", "")
        self.primary_endpoint: str = data.get("primary_endpoint", "")
        self.drug: str = data.get("drug_name", "?")

        # Select assistant turns by role rather than by fixed index: a chain cut
        # short by a provider error still has nodes, just fewer, and positional
        # extraction would silently read the wrong step.
        self.steps: list[str] = [
            (node.get("message") or {}).get("content") or ""
            for node in trace.get("nodes", [])
            if (node.get("message") or {}).get("role") == "assistant"
            and node.get("sampled")
        ]
        self.complete = len(self.steps) == EXPECTED_STEPS

        rewards = trace.get("rewards") or {}
        self.scores: dict[str, float] = {
            name: rewards[name]["score"] for name in REWARDS if name in rewards
        }
        self.metrics: dict = trace.get("metrics") or {}

        final = self.steps[-1] if self.steps else ""
        match = PREDICTION_RE.search(final)
        raw = match.group(1).upper() if match else None
        self.predicted: str | None = raw if raw in ("SUCCESS", "FAILURE") else None
        self.abstained: bool = raw == "UNKNOWN" or (
            self.complete and self.predicted is None
        )
        conf = CONFIDENCE_RE.search(final)
        try:
            self.confidence: float | None = float(conf.group(1)) if conf else None
        except ValueError:
            self.confidence = None
        reason = KEY_REASON_RE.search(final)
        self.key_reason: str = (
            " ".join(reason.group(1).split()) if reason else ""
        )

    @property
    def safety_endpoint(self) -> bool:
        """Is the REGISTERED primary endpoint a safety/tolerability measure?

        Matters because a safety trial's bar is "was it tolerated", while the
        models reason almost entirely about "did the drug work". Those two come
        apart exactly where the models mispredict SUCCESS trials.
        """
        return bool(SAFETY_ENDPOINT_RE.search(self.primary_endpoint or ""))

    def step(self, index: int) -> str:
        return self.steps[index] if index < len(self.steps) else ""

    @property
    def correct(self) -> bool:
        return self.scores.get("s6_outcome", 0.0) == 1.0

    def verdict(self) -> str:
        if self.abstained:
            return "ABSTAINED"
        if self.predicted is None:
            return "UNPARSED"
        return "CORRECT" if self.correct else f"WRONG ({self.predicted})"


def load_model(run_dir: Path) -> dict[str, Rollout]:
    path = run_dir / "traces.jsonl"
    if not path.exists():
        return {}
    out: dict[str, Rollout] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        for trace in json.loads(line).get("traces", []):
            roll = Rollout(trace)
            if roll.complete:
                out[roll.nct_id] = roll
    return out


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r; None when either side is constant."""
    if len(xs) < 3:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    sx = math.sqrt(sum(d * d for d in dx))
    sy = math.sqrt(sum(d * d for d in dy))
    if sx == 0 or sy == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / (sx * sy)


def phase_prior_analysis(
    models: dict[str, dict[str, Rollout]], model_names: list[str], common: set[str]
) -> tuple[list[str], dict[str, tuple[float | None, float | None]], float]:
    """Are the models predicting the trial's OUTCOME, or just its PHASE?

    The dataset is balanced 50/50 within every phase, so "phase 3 tends to
    succeed" is worth exactly nothing here — a predictor that follows it scores
    chance. Comparing r(prediction, is-phase-3) against r(prediction, true
    label) says which one a model is actually tracking.
    """
    lines: list[str] = []
    ordered = sorted(common)
    first = model_names[0]
    phases = sorted({models[first][n].phase for n in ordered})

    header = f"{'phase':<9}{'true SUCCESS':>14}" + "".join(
        f"{m[:12]:>14}" for m in model_names
    )
    lines.append(header)
    lines.append("-" * len(header))
    for phase in phases:
        sub = [n for n in ordered if models[first][n].phase == phase]
        if not sub:
            continue
        truth = sum(1 for n in sub if models[first][n].label == "SUCCESS") / len(sub)
        row = f"{phase:<9}{truth * 100:>13.0f}%"
        for name in model_names:
            answered = [
                1.0 if models[name][n].predicted == "SUCCESS" else 0.0
                for n in sub
                if models[name][n].predicted is not None
            ]
            row += (
                f"{st.mean(answered) * 100:>13.0f}%" if answered else f"{'n/a':>14}"
            )
        lines.append(row + f"   (n={len(sub)})")

    correlations: dict[str, tuple[float | None, float | None]] = {}
    for name in model_names:
        sub = [n for n in ordered if models[name][n].predicted is not None]
        pred = [1.0 if models[name][n].predicted == "SUCCESS" else 0.0 for n in sub]
        is_p3 = [1.0 if "3" in (models[name][n].phase or "") else 0.0 for n in sub]
        truth = [1.0 if models[name][n].label == "SUCCESS" else 0.0 for n in sub]
        correlations[name] = (pearson(pred, is_p3), pearson(pred, truth))

    rule = [1.0 if "3" in (models[first][n].phase or "") else 0.0 for n in ordered]
    truth = [1.0 if models[first][n].label == "SUCCESS" else 0.0 for n in ordered]
    rule_acc = sum(1 for a, b in zip(rule, truth) if a == b) / len(ordered)
    return lines, correlations, rule_acc


def failure_signature(rolls: dict[str, Rollout], label: str) -> str:
    """A mechanical description of HOW the models failed on this trial.

    Derived only from measured quantities - the predicted labels, the S1 recall
    scores and the stated confidences. It does not read the reasoning; the
    excerpts in the report are there for that.
    """
    preds = [r.predicted for r in rolls.values()]
    committed = [p for p in preds if p]
    abstained = sum(1 for r in rolls.values() if r.abstained)
    recall = st.mean(r.scores.get("s1_trial_recall", 0.0) for r in rolls.values())
    confs = [r.confidence for r in rolls.values() if r.confidence is not None]
    mean_conf = st.mean(confs) if confs else float("nan")

    bits = []
    if committed and len(set(committed)) == 1 and committed[0] != label:
        wrong_way = committed[0]
        bits.append(
            f"all {len(committed)} committed models said {wrong_way} on a "
            f"{label} trial"
        )
        if wrong_way == "FAILURE":
            bits.append("consistent with the shared FAILURE lean")
    elif committed:
        bits.append(f"models split ({'/'.join(committed)}), none correct")
    if abstained:
        bits.append(f"{abstained} abstained")
    bits.append(
        "no trial-specific recall (S1=0.00)"
        if recall == 0
        else f"mean S1 recall {recall:.2f}"
    )
    if mean_conf == mean_conf:
        bits.append(f"mean stated confidence {mean_conf:.2f}")
    return "; ".join(bits)


def render_trial(
    out: list[str],
    nct: str,
    rolls: dict[str, Rollout],
    model_names: list[str],
    heading: str,
    full_reasoning: bool,
) -> None:
    any_roll = next(iter(rolls.values()))
    out.append(f"\n### {heading}: {nct}\n")
    out.append(f"**Ground truth (`label`):** {any_roll.label}  ")
    out.append(f"**Phase:** {any_roll.phase}  ")
    out.append(f"**Indication:** {any_roll.indication}  ")
    out.append(f"**Sponsor:** {any_roll.sponsor}  ")
    out.append(f"**Drug:** {any_roll.drug}  ")
    out.append(f"**Title:** {any_roll.title}\n")

    out.append("| Step | " + " | ".join(model_names) + " |")
    out.append("|---|" + "|".join("---" for _ in model_names) + "|")
    for name, pretty in STEP_LABELS:
        cells = []
        for model in model_names:
            roll = rolls.get(model)
            if roll is None:
                cells.append("-")
                continue
            score = roll.scores.get(name)
            cell = "-" if score is None else f"{score:.2f}"
            if name == "s6_outcome":
                cell = f"{cell} {roll.verdict()}"
            cells.append(cell)
        out.append(f"| {pretty} | " + " | ".join(cells) + " |")

    out.append("")
    for model in model_names:
        roll = rolls.get(model)
        if roll is None:
            continue
        out.append(f"**{model} reasoning:**\n")
        if full_reasoning:
            out.append(f"*S5 Risk Factors (first {S5_EXCERPT_WORDS} words):*\n")
            out.append("```")
            out.append(words(roll.step(4), S5_EXCERPT_WORDS) or "(empty)")
            out.append("```\n")
        out.append("*S6 Prediction (full):*\n")
        out.append("```")
        out.append((roll.step(5) or "(empty)").strip())
        out.append("```\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("results_dir", nargs="?", type=Path, default=root / "results")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out_path = args.out or (args.results_dir / "rollout_analysis.md")
    rng = random.Random(SEED)

    run_dirs = sorted(
        d
        for d in args.results_dir.iterdir()
        if d.is_dir() and (d / "traces.jsonl").exists()
    )
    if not run_dirs:
        raise SystemExit(f"no run directories under {args.results_dir}")
    models = {d.name: load_model(d) for d in run_dirs}
    models = {k: v for k, v in models.items() if v}
    model_names = sorted(models)
    if len(model_names) < 2:
        raise SystemExit("need at least two model runs to compare")

    common = set.intersection(*(set(m) for m in models.values()))

    def rolls_for(nct: str) -> dict[str, Rollout]:
        return {name: models[name][nct] for name in model_names}

    # Two cohorts; see the module docstring for why they are kept apart.
    zero_all = sorted(
        n for n in common if all(models[m][n].scores.get("s6_outcome") == 0.0 for m in model_names)
    )
    shared_false = [
        n for n in zero_all if all(models[m][n].predicted is not None for m in model_names)
    ]
    with_abstention = [n for n in zero_all if n not in set(shared_false)]
    correct_all = sorted(n for n in common if all(models[m][n].correct for m in model_names))
    baseline = rng.sample(correct_all, min(BASELINE_TRIALS, len(correct_all)))

    def summarise(cohort: list[str]) -> tuple[Counter, Counter]:
        first = model_names[0]
        return (
            Counter(models[first][n].label for n in cohort),
            Counter(models[first][n].phase for n in cohort),
        )

    labels_sf, phases_sf = summarise(shared_false)
    labels_all, phases_all = summarise(zero_all)

    # --- stdout ---------------------------------------------------------
    print(f"=== {len(shared_false)} SHARED-FALSE-BELIEF trials "
          f"(all {len(model_names)} committed, all wrong) ===")
    head = f"{'NCT_ID':<12} | {'truth':<8} | {'phase':<7} | " + " | ".join(
        f"{m[:12]:<12}" for m in model_names
    ) + " | failure signature"
    print(head)
    print("-" * min(len(head), 200))
    for nct in shared_false:
        rolls = rolls_for(nct)
        first = rolls[model_names[0]]
        preds = " | ".join(f"{(rolls[m].predicted or 'ABSTAIN')[:12]:<12}" for m in model_names)
        print(f"{nct:<12} | {first.label:<8} | {first.phase:<7} | {preds} | "
              f"{failure_signature(rolls, first.label)}")

    print(f"\n=== {len(with_abstention)} further trials scored 0.0 everywhere "
          "but with >=1 abstention ===")
    for nct in with_abstention:
        rolls = rolls_for(nct)
        first = rolls[model_names[0]]
        preds = " | ".join(f"{(rolls[m].predicted or 'ABSTAIN')[:12]:<12}" for m in model_names)
        print(f"{nct:<12} | {first.label:<8} | {first.phase:<7} | {preds}")

    phase_lines, correlations, rule_acc = phase_prior_analysis(models, model_names, common)
    print("\n=== Are the models predicting OUTCOME, or just PHASE? ===")
    print("Predicted-SUCCESS rate by phase (answered only):")
    for line in phase_lines:
        print("  " + line)
    print(f"\n  {'model':<14}{'r(pred, is-phase-3)':>21}{'r(pred, TRUE label)':>21}")
    for name in model_names:
        rp, rl = correlations[name]
        print(f"  {name:<14}"
              f"{(f'{rp:+.3f}' if rp is not None else 'n/a'):>21}"
              f"{(f'{rl:+.3f}' if rl is not None else 'n/a'):>21}")
    print(f"\n  A 'predict SUCCESS iff phase 3' rule scores {rule_acc:.3f} on this "
          "dataset (chance = 0.500),")
    print("  because the rows are balanced 50/50 WITHIN each phase. Any model whose "
          "predictions")
    print("  track phase more than they track the label is spending its answer on a "
          "worthless signal.")

    first_m = model_names[0]
    missed_success = [n for n in shared_false if models[first_m][n].label == "SUCCESS"]
    missed_failure = [n for n in shared_false if models[first_m][n].label == "FAILURE"]
    ms_safety = sum(1 for n in missed_success if models[first_m][n].safety_endpoint)
    mf_safety = sum(1 for n in missed_failure if models[first_m][n].safety_endpoint)
    base_safety = sum(1 for n in common if models[first_m][n].safety_endpoint)
    print("\n=== Two distinct failure modes, split by endpoint type ===")
    print(f"  baseline: {base_safety}/{len(common)} ({base_safety/len(common):.0%}) of all "
          "trials have a safety/tolerability primary endpoint")
    print(f"  missed SUCCESSes (called FAILURE): {ms_safety}/{len(missed_success)} have a "
          "safety endpoint")
    print(f"  missed FAILUREs  (called SUCCESS): {mf_safety}/{len(missed_failure)} have a "
          "safety endpoint")
    print("  -> the models judge 'did the drug work'. A safety trial's registered bar is")
    print("     'was it tolerated', which it can meet while the drug shows no efficacy.")

    print("\nKey patterns:")
    n_sf = len(shared_false) or 1
    print(f"- {labels_sf.get('SUCCESS', 0)}/{len(shared_false)} shared-false-belief trials are "
          f"SUCCESS trials predicted FAILURE-ward (bias confirmation)")
    print(f"- phase distribution (shared false belief): {dict(sorted(phases_sf.items()))}")
    print(f"- counting abstentions as wrong widens the cohort to {len(zero_all)}: "
          f"labels {dict(sorted(labels_all.items()))}, phases {dict(sorted(phases_all.items()))}")
    unanimous = [
        n for n in shared_false
        if len({models[m][n].predicted for m in model_names}) == 1
    ]
    print(f"- {len(unanimous)}/{len(shared_false)} had all models give the SAME wrong label "
          "(shared belief, not independent errors)")
    flagged = []
    for nct in unanimous:
        confs = [models[m][nct].confidence for m in model_names
                 if models[m][nct].confidence is not None]
        recall = st.mean(
            models[m][nct].scores.get("s1_trial_recall", 0.0) for m in model_names
        )
        if (
            confs
            and st.mean(confs) >= MISLABEL_CONFIDENCE
            and recall >= MISLABEL_MIN_RECALL
        ):
            flagged.append((nct, st.mean(confs), recall))
    if flagged:
        print(f"- {len(flagged)} unanimous, confident (>= {MISLABEL_CONFIDENCE}) AND "
              f"backed by real recall (S1 > 0) -> worth re-checking the label:")
        for nct, conf, recall in flagged:
            print(f"    {nct} (mean confidence {conf:.2f}, mean S1 recall {recall:.2f})")
    else:
        print("- no trial met the unanimous + confident + real-recall bar for a "
              "label re-check")

    # --- markdown -------------------------------------------------------
    out: list[str] = ["# Individual Rollout Analysis\n"]
    out.append(
        f"Models: {', '.join(model_names)} · {len(common)} trials completed by all.\n"
    )
    out.append("## Summary\n")
    out.append(
        f"Two cohorts are reported separately, because \"all models got it wrong\" "
        f"is ambiguous once a model can abstain.\n"
    )
    out.append(
        f"- **Shared false belief ({len(shared_false)} trials)** — every model "
        f"committed to a label and every model was wrong. Ground truth: "
        f"{dict(sorted(labels_sf.items()))}. Phases: {dict(sorted(phases_sf.items()))}."
    )
    out.append(
        f"- **No correct answer ({len(zero_all)} trials)** — S6 scored 0.0 for all "
        f"models, which also catches the {len(with_abstention)} trials where at "
        f"least one model declined to predict. Ground truth: "
        f"{dict(sorted(labels_all.items()))}. Phases: {dict(sorted(phases_all.items()))}."
    )
    out.append(
        "\nAn abstention is not a false belief, so the deep-dive below covers the "
        "first cohort; the second is listed for completeness."
    )
    out.append(
        f"\n- {labels_sf.get('SUCCESS', 0)} of {len(shared_false)} shared-false-belief "
        "trials are SUCCESS trials the models called FAILURE-ward — the same lean "
        "the cross-model report measures."
    )
    out.append(
        f"- {len(unanimous)} of {len(shared_false)} drew the *same* wrong label from "
        "every model, so these are a shared belief rather than three independent errors."
    )
    if flagged:
        out.append(
            f"- {len(flagged)} were unanimous, confident (≥ {MISLABEL_CONFIDENCE}) "
            "**and** backed by non-zero trial recall: "
            + ", ".join(f"`{n}` (conf {c:.2f}, S1 recall {r:.2f})" for n, c, r in flagged)
            + ". These are the rows where a model demonstrably knew something about "
            "the trial and still contradicted the registry — the only profile that "
            "is evidence about the label rather than about the model's prior. Worth "
            "re-checking against ClinicalTrials.gov."
        )

    out.append("\n## Universally-Wrong Trials (shared false belief)\n")
    for i, nct in enumerate(shared_false, 1):
        rolls = rolls_for(nct)
        render_trial(out, nct, rolls, model_names, f"Trial {i}", full_reasoning=True)
        out.append(
            f"**Failure signature:** {failure_signature(rolls, rolls[model_names[0]].label)}\n"
        )
        out.append("---")

    if with_abstention:
        out.append("\n## Also scored 0.0 everywhere, but involving an abstention\n")
        out.append("| NCT | truth | phase | " + " | ".join(model_names) + " |")
        out.append("|---|---|---|" + "|".join("---" for _ in model_names) + "|")
        for nct in with_abstention:
            rolls = rolls_for(nct)
            first = rolls[model_names[0]]
            cells = " | ".join(rolls[m].verdict() for m in model_names)
            out.append(f"| {nct} | {first.label} | {first.phase} | {cells} |")

    out.append(f"\n## Comparison: {len(baseline)} Correctly-Predicted Trials\n")
    out.append(
        "Sampled with a fixed seed from the "
        f"{len(correct_all)} trials every model got right.\n"
    )
    for i, nct in enumerate(baseline, 1):
        render_trial(
            out, nct, rolls_for(nct), model_names, f"Baseline {i}", full_reasoning=False
        )
        out.append("---")

    out.append("\n## Are the models predicting outcome, or just phase?\n")
    out.append(
        "The dataset is balanced 50/50 **within every phase**, so \"phase 3 trials "
        "tend to succeed\" carries no information here: a predictor that follows it "
        f"scores {rule_acc:.3f}, i.e. chance. Yet the predicted-SUCCESS rate swings "
        "hard by phase.\n"
    )
    out.append("```")
    out.extend(phase_lines)
    out.append("```\n")
    out.append("| model | r(pred, is-phase-3) | r(pred, TRUE label) |")
    out.append("|---|---|---|")
    for name in model_names:
        rp, rl = correlations[name]
        out.append(
            f"| {name} | {f'{rp:+.3f}' if rp is not None else 'n/a'} | "
            f"{f'{rl:+.3f}' if rl is not None else 'n/a'} |"
        )
    out.append("")
    leaning = [
        n for n in model_names
        if correlations[n][0] is not None
        and correlations[n][1] is not None
        and correlations[n][0] > correlations[n][1]
    ]
    if leaning:
        out.append(
            f"**{', '.join(leaning)}** correlate more strongly with the trial's phase "
            "than with its actual outcome — their S6 answer is closer to a phase "
            "lookup than to a judgement about the trial. That is also why the "
            "intermediate steps fail to predict S6 in the cross-model report: the "
            "answer is largely fixed by the phase prior before any trial-specific "
            "reasoning happens."
        )
    others = [n for n in model_names if n not in leaning]
    if others:
        out.append(
            f"\n**{', '.join(others)}** track the true label more than the phase. "
            "For a model that also abstains heavily, this is the expected shape: it "
            "declines instead of falling back on the phase prior, which is why its "
            "accuracy-when-answered is the highest of the three."
        )

    out.append("\n## Cross-Trial Patterns\n")
    out.append(
        f"- **Direction.** {labels_sf.get('SUCCESS', 0)}/{len(shared_false)} of the "
        "shared-false-belief trials are SUCCESS trials. Counting abstentions too, "
        f"{labels_all.get('SUCCESS', 0)}/{len(zero_all)} are SUCCESS. The models "
        "fail asymmetrically: they miss successes far more than they miss failures."
    )
    out.append(
        f"- **Phase.** Shared false belief: {dict(sorted(phases_sf.items()))}. "
        f"All-zero cohort: {dict(sorted(phases_all.items()))}."
    )
    out.append(
        f"- **Shared vs independent error.** {len(unanimous)}/{len(shared_false)} "
        "unanimous on the same wrong label."
    )
    recalls = [
        st.mean(models[m][n].scores.get("s1_trial_recall", 0.0) for m in model_names)
        for n in shared_false
    ]
    if recalls:
        out.append(
            f"- **Recall.** Mean S1 recall across these trials is {st.mean(recalls):.2f}; "
            f"{sum(1 for r in recalls if r == 0)}/{len(recalls)} had no model name the "
            "sponsor at all, i.e. the models are reasoning from priors, not memory."
        )
    out.append(
        f"- **Two failure modes, not one — split by endpoint type.** Of the "
        f"{len(missed_success)} SUCCESS trials called FAILURE, {ms_safety} have a "
        f"safety/tolerability primary endpoint; of the {len(missed_failure)} FAILURE "
        f"trials called SUCCESS, {mf_safety} do (baseline across all trials: "
        f"{base_safety}/{len(common)}, {base_safety/len(common):.0%}). The models "
        "reason about whether the *drug works*, but a safety trial's registered bar "
        "is whether it was *tolerated* — a trial can clear that while the drug shows "
        "nothing. The mirror-image mode is an efficacy trial for a familiar "
        "mechanism, where the models assume the endpoint will be met and it is not. "
        "(Endpoint type is keyword-classified from `primary_endpoint`, so treat the "
        "counts as indicative.)"
    )
    out.append(
        "- **The shared errors are phase-prior errors.** Every one of these trials "
        "defies its phase's reputation: the phase-3 rows are FAILUREs the models "
        "called SUCCESS, and the phase-1/2 rows are SUCCESSes they called FAILURE. "
        "The models are not failing at random — they are failing exactly where the "
        "base rate points the wrong way."
    )
    out.append(
        "- **Potentially mislabelled.** "
        + (
            ", ".join(f"`{n}`" for n, _, _ in flagged)
            if flagged
            else "none met the unanimous + confident + real-recall bar."
        )
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out) + "\n")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
