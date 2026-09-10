#!/usr/bin/env python3
"""analyze_cross_model.py — the same 100 trials, several model families side by side.

`analyze_rollouts.py` answers "is this number stable across repeated rollouts of
one model". This answers a different question: run at `-r 1`, is a result a fact
about clinical-trial reasoning or a fact about DeepSeek? Three things separate
those:

  * the FAILURE bias — high accuracy on FAILURE rows bought with low accuracy on
    SUCCESS rows is a prior, not reasoning. If every model shows it, it is the
    task; if one does, it is that model.
  * per-trial agreement — trials all models get right are the ones whose outcome
    is effectively memorised; trials they split on are where the signal is.
  * intermediate-step signal — whether S1-S5 predict S6 *within* a model. A chain
    whose middle steps carry no signal is a chain that is not being used.

Single-rollout runs are noisy (see `analyze_rollouts.py`: unchanged code moved
56.7% -> 70.0% on n=60), so every point estimate here carries an interval and
every claim of a difference carries a permutation p-value.

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
INTERMEDIATE = REWARDS[:-1]
OUTCOME = "s6_outcome"

EXPECTED_STEPS = 6
PERMUTATIONS = 10000
SEED = 2026


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_run(run_dir: Path) -> tuple[list[dict], list[dict]]:
    """(complete, incomplete) traces for one model's run directory.

    An episode killed mid-chain by a provider error still carries rewards, all
    scored 0.0 because the replies are missing. Averaging those in would report a
    rate limit as a reasoning failure — and the whole point of this script is
    comparing providers, whose rate limits differ. They are separated here and
    only complete chains are analysed; the count of dropped ones is reported so a
    model that was mostly throttled cannot masquerade as a model that was mostly
    wrong.
    """
    path = run_dir / "traces.jsonl"
    if not path.exists():
        return [], []
    traces: list[dict] = []
    for line in path.read_text().splitlines():
        if line.strip():
            traces.extend(json.loads(line).get("traces", []))
    complete, incomplete = [], []
    for trace in traces:
        sampled = sum(1 for n in trace.get("nodes", []) if n.get("sampled"))
        (complete if sampled == EXPECTED_STEPS else incomplete).append(trace)
    return complete, incomplete


def prediction(trace: dict) -> str | None:
    """The label the model predicted at S6, or None if nothing parsed.

    Read off the recorded metrics rather than re-parsing the reply, so this
    script and the reward function can never disagree about what was predicted.
    """
    metrics = trace.get("metrics") or {}
    if not metrics.get("s6_parsed"):
        return None
    return "SUCCESS" if metrics.get("s6_predicted_success") else "FAILURE"


class ModelRun:
    """One model's complete episodes, keyed by trial."""

    def __init__(self, name: str, run_dir: Path, meta: dict[str, dict]):
        self.name = name
        self.dir = run_dir
        traces, dropped = load_run(run_dir)
        self.dropped = len(dropped)
        self.drop_causes: dict[str, int] = defaultdict(int)
        for trace in dropped:
            for err in trace.get("errors") or []:
                self.drop_causes[str(err.get("type"))] += 1

        # nct -> {reward name: score}, plus the prediction and the true label.
        self.rows: dict[str, dict] = {}
        for trace in traces:
            nct = (trace.get("task") or {}).get("data", {}).get("nct_id")
            if nct is None:
                continue
            rewards = trace.get("rewards") or {}
            self.rows[nct] = {
                "scores": {
                    name: rewards[name]["score"]
                    for name in REWARDS
                    if name in rewards
                },
                "predicted": prediction(trace),
                "label": (meta.get(nct) or {}).get("label"),
            }

    # -- accessors ---------------------------------------------------------

    def scores(self, reward: str) -> list[float]:
        return [
            row["scores"][reward] for row in self.rows.values() if reward in row["scores"]
        ]

    def paired(
        self, reward: str, answered_only: bool = False
    ) -> tuple[list[float], list[float]]:
        """(intermediate score, S6 correctness) over trials that have both.

        `answered_only` is the confound-free version. An abstention scores S6=0
        AND tends to come with thin intermediate answers, so over all trials any
        intermediate reward correlates with S6 simply by tracking "did the model
        engage with this trial at all". Restricting to trials where the model
        committed to a label removes that channel and leaves the question the
        chain is actually asking: given that it answered, did reasoning better
        through the middle steps make the answer righter?
        """
        xs, ys = [], []
        for row in self.rows.values():
            scores = row["scores"]
            if answered_only and row["predicted"] is None:
                continue
            if reward in scores and OUTCOME in scores:
                xs.append(scores[reward])
                ys.append(scores[OUTCOME])
        return xs, ys

    def accuracy_by_label(self, answered_only: bool = False) -> dict[str, tuple[int, int]]:
        """label -> (correct, total).

        `answered_only` drops abstentions. Section 2 asks which way the model
        leans, and an abstention leans neither way — counting it as a miss on its
        own label would manufacture a bias out of a model that simply declines.
        """
        out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for row in self.rows.values():
            label = row["label"]
            if label is None or OUTCOME not in row["scores"]:
                continue
            if answered_only and row["predicted"] is None:
                continue
            out[label][0] += int(row["scores"][OUTCOME])
            out[label][1] += 1
        return {k: (v[0], v[1]) for k, v in out.items()}

    def answered(self) -> tuple[int, int]:
        """(trials with a parsed SUCCESS/FAILURE, complete trials).

        A model that writes `PREDICTION: unknown` scores 0.0 on S6 — the same as
        a confident wrong answer. Across models that is not comparable: one that
        abstains half the time looks equally wrong as one that guesses badly, so
        the abstention rate has to be reported next to the accuracy.
        """
        n = sum(1 for row in self.rows.values() if OUTCOME in row["scores"])
        answered = sum(
            1
            for row in self.rows.values()
            if OUTCOME in row["scores"] and row["predicted"] is not None
        )
        return answered, n

    def accuracy_among_answered(self) -> tuple[int, int]:
        """(correct, answered) — accuracy conditional on committing to a label."""
        correct = total = 0
        for row in self.rows.values():
            if OUTCOME in row["scores"] and row["predicted"] is not None:
                total += 1
                correct += int(row["scores"][OUTCOME])
        return correct, total

    def predicted_success_rate(self) -> tuple[int, int]:
        """(predicted SUCCESS, parsed predictions)."""
        parsed = [row["predicted"] for row in self.rows.values() if row["predicted"]]
        return sum(1 for p in parsed if p == "SUCCESS"), len(parsed)


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------


def wilson(successes: float, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — behaves near 0 and 1 where the normal one does not."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r; None when either side is constant (r undefined, not 0).

    With `ys` binary this is the point-biserial correlation — the natural effect
    size for "does this intermediate score predict getting S6 right".
    """
    n = len(xs)
    if n < 3:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    sx = math.sqrt(sum(d * d for d in dx))
    sy = math.sqrt(sum(d * d for d in dy))
    if sx == 0 or sy == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / (sx * sy)


def pearson_permutation_p(xs: list[float], ys: list[float], rng: random.Random) -> float:
    """Two-sided permutation p for Pearson r.

    Under permutation the means and standard deviations are fixed, so only the
    centred cross-product changes — shuffling and re-dotting is enough, no need
    to recompute r itself.
    """
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = st.mean(xs), st.mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    if not any(dx) or not any(dy):
        return float("nan")
    observed = abs(sum(a * b for a, b in zip(dx, dy)))
    hits = 0
    shuffled = list(dy)
    for _ in range(PERMUTATIONS):
        rng.shuffle(shuffled)
        if abs(sum(a * b for a, b in zip(dx, shuffled))) >= observed - 1e-12:
            hits += 1
    return (hits + 1) / (PERMUTATIONS + 1)


def two_proportion_permutation_p(
    a: list[float], b: list[float], rng: random.Random
) -> float:
    """Two-sided permutation test on a difference of means."""
    if not a or not b:
        return float("nan")
    observed = abs(st.mean(a) - st.mean(b))
    pool = list(a) + list(b)
    cut = len(a)
    hits = 0
    for _ in range(PERMUTATIONS):
        rng.shuffle(pool)
        if abs(st.mean(pool[:cut]) - st.mean(pool[cut:])) >= observed - 1e-12:
            hits += 1
    return (hits + 1) / (PERMUTATIONS + 1)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


class Report:
    """Collects lines for stdout and the markdown file at once."""

    def __init__(self) -> None:
        self.md: list[str] = []

    def h(self, level: int, text: str) -> None:
        print(f"\n{text}" if level <= 2 else f"\n{text}")
        self.md.append(f"\n{'#' * level} {text}\n")

    def p(self, text: str = "") -> None:
        print(text)
        self.md.append(text + "\n")

    def raw_md(self, text: str) -> None:
        """Markdown-only (a table the console prints in its own format)."""
        self.md.append(text + "\n")

    def console(self, text: str) -> None:
        print(text)

    def table(self, headers: list[str], rows: list[list[str]], widths: list[int]) -> None:
        """Fixed-width to the console, pipe-delimited to markdown."""
        line = "".join(h.ljust(w) for h, w in zip(headers, widths))
        print("  " + line)
        print("  " + "-" * len(line.rstrip()))
        for row in rows:
            print("  " + "".join(str(c).ljust(w) for c, w in zip(row, widths)))
        self.md.append("| " + " | ".join(headers) + " |")
        self.md.append("|" + "|".join("---" for _ in headers) + "|")
        for row in rows:
            self.md.append("| " + " | ".join(str(c) for c in row) + " |")
        self.md.append("")


def fmt_p(p: float) -> str:
    if p != p:  # NaN
        return "n/a"
    return f"{p:.4f}" + ("*" if p < 0.05 else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "results_dir",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "results",
        help="directory holding one subdirectory per model run (default: results/)",
    )
    parser.add_argument(
        "--rows",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "trials.jsonl",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="markdown report path (default: <results_dir>/cross_model_report.md)",
    )
    args = parser.parse_args()
    rng = random.Random(SEED)

    out_path = args.out or (args.results_dir / "cross_model_report.md")

    meta: dict[str, dict] = {}
    for line in args.rows.read_text().splitlines():
        if line.strip():
            record = json.loads(line)
            meta[record["nct_id"]] = record

    if not args.results_dir.exists():
        raise SystemExit(f"no results directory at {args.results_dir}")
    run_dirs = sorted(
        d for d in args.results_dir.iterdir() if d.is_dir() and (d / "traces.jsonl").exists()
    )
    if not run_dirs:
        raise SystemExit(
            f"no run directories with traces.jsonl under {args.results_dir}. "
            "Run scripts/run_multi_model.sh first."
        )

    models = [ModelRun(d.name, d, meta) for d in run_dirs]
    models = [m for m in models if m.rows]
    if not models:
        raise SystemExit("every run directory was empty of complete episodes")

    r = Report()
    r.md.append("# Cross-model comparison\n")
    r.console(f"CROSS-MODEL COMPARISON  ({args.results_dir})")
    r.md.append(f"Run directory: `{args.results_dir}`\n")
    r.p(f"models: {', '.join(m.name for m in models)}")
    r.p(f"trials in dataset: {len(meta)}")
    if len(models) < 3:
        r.p(
            f"NOTE: {len(models)} model(s) present. Sections keyed to three-way "
            "agreement degrade to what the available runs support."
        )

    # --- 0. coverage ------------------------------------------------------
    r.h(2, "0. RUN COVERAGE")
    rows = []
    for m in models:
        causes = ", ".join(f"{k}={v}" for k, v in sorted(m.drop_causes.items())) or "-"
        rows.append([m.name, len(m.rows), m.dropped, causes])
    r.table(
        ["model", "complete", "dropped", "drop causes"],
        rows,
        [16, 11, 10, 40],
    )
    r.p(
        "Dropped episodes died mid-chain (usually a provider error) and score 0.0 "
        "on every reward; they are excluded below so throttling is not read as "
        "reasoning failure."
    )

    # --- 1. S6 accuracy ---------------------------------------------------
    r.h(2, "1. S6 ACCURACY (95% Wilson CI)")
    rows = []
    abstainers = []
    for m in models:
        s6 = m.scores(OUTCOME)
        correct = int(sum(s6))
        lo, hi = wilson(correct, len(s6))
        ans, ans_n = m.answered()
        acorr, atot = m.accuracy_among_answered()
        alo, ahi = wilson(acorr, atot)
        by_label = m.accuracy_by_label()
        succ_c, succ_n = by_label.get("SUCCESS", (0, 0))
        fail_c, fail_n = by_label.get("FAILURE", (0, 0))
        rows.append(
            [
                m.name,
                f"{ans}/{ans_n}" + (f" ({ans/ans_n:.3f})" if ans_n else ""),
                f"{correct}/{len(s6)}",
                f"{st.mean(s6):.3f}" if s6 else "-",
                f"[{lo:.3f}, {hi:.3f}]",
                f"{acorr}/{atot}" + (f" ({acorr/atot:.3f})" if atot else ""),
                f"[{alo:.3f}, {ahi:.3f}]" if atot else "-",
                f"{succ_c}/{succ_n}",
                f"{fail_c}/{fail_n}",
            ]
        )
        if ans_n and ans / ans_n < 0.95:
            abstainers.append((m.name, ans_n - ans, ans_n))
    r.table(
        [
            "model",
            "answered",
            "correct",
            "acc",
            "95% CI",
            "acc|answered",
            "95% CI",
            "SUCC",
            "FAIL",
        ],
        rows,
        [16, 17, 10, 8, 18, 16, 18, 8, 8],
    )
    r.p("A 100-trial run at -r 1: the CI is wide by construction. Read gaps, not decimals.")
    r.p(
        "`answered` is the share of complete chains where S6 committed to "
        "SUCCESS or FAILURE. An abstention (`PREDICTION: unknown`) scores 0.0, "
        "exactly like a wrong answer — so `acc` mixes being wrong with declining "
        "to answer, and `acc|answered` separates them. Compare models on both: "
        "`acc` is the number the reward optimises, `acc|answered` is the one that "
        "reflects discrimination."
    )
    if abstainers:
        for name, missed, total in abstainers:
            r.p(
                f"  ABSTENTION: {name} declined to predict on {missed}/{total} "
                "trials. Its `acc` column understates its discrimination."
            )
    else:
        r.p("  Every model committed to a label on essentially every trial.")

    # --- 2. the FAILURE bias ----------------------------------------------
    r.h(2, "2. FAILURE BIAS — task artefact or model artefact?")
    r.p(
        "The dataset is 50/50, so a model with no signal that guesses one class "
        "every time scores 0.500 overall while scoring 1.000 on that class. "
        "`pred SUCCESS` is the share of predictions that were SUCCESS: 0.50 is "
        "balanced, near 0.00 means the model answers FAILURE almost always. "
        "Every column here is computed over ANSWERED trials only — an abstention "
        "leans neither way, and scoring it against its own label would invent a "
        "bias for a model that merely declines to guess."
    )
    rows = []
    biased = []
    for m in models:
        by_label = m.accuracy_by_label(answered_only=True)
        succ_c, succ_n = by_label.get("SUCCESS", (0, 0))
        fail_c, fail_n = by_label.get("FAILURE", (0, 0))
        succ_acc = succ_c / succ_n if succ_n else float("nan")
        fail_acc = fail_c / fail_n if fail_n else float("nan")
        gap = fail_acc - succ_acc
        pred_s, pred_n = m.predicted_success_rate()
        succ_scores = [
            row["scores"][OUTCOME]
            for row in m.rows.values()
            if row["label"] == "SUCCESS"
            and OUTCOME in row["scores"]
            and row["predicted"] is not None
        ]
        fail_scores = [
            row["scores"][OUTCOME]
            for row in m.rows.values()
            if row["label"] == "FAILURE"
            and OUTCOME in row["scores"]
            and row["predicted"] is not None
        ]
        p = two_proportion_permutation_p(fail_scores, succ_scores, rng)
        rows.append(
            [
                m.name,
                f"{pred_s}/{pred_n}" + (f" ({pred_s/pred_n:.3f})" if pred_n else ""),
                f"{succ_acc:.3f}",
                f"{fail_acc:.3f}",
                f"{gap:+.3f}",
                fmt_p(p),
            ]
        )
        if gap == gap:
            biased.append((m.name, gap, p))
    r.table(
        ["model", "pred SUCCESS", "SUCCESS acc", "FAILURE acc", "FAILURE-SUCCESS", "perm p"],
        rows,
        [16, 18, 13, 13, 17, 10],
    )
    positive = [b for b in biased if b[1] > 0]
    significant = [b for b in biased if b[1] > 0 and b[2] == b[2] and b[2] < 0.05]
    if len(biased) < 2:
        # "every model does it, so it is the task" needs more than one model.
        # Stating it from a single run is precisely the inference this section
        # exists to prevent.
        only = biased[0] if biased else None
        verdict = (
            f"Only one model has results ({only[0]}, gap {only[1]:+.3f}, "
            f"p={fmt_p(only[2])}). Whether this is the task or the model is "
            "exactly what a second model would settle — not answerable yet."
            if only
            else "No model produced a gradable SUCCESS/FAILURE split."
        )
    elif len(positive) == len(biased):
        verdict = (
            f"All {len(biased)} models lean FAILURE "
            f"({len(significant)} significantly at p<0.05) — this looks like the "
            "task or the dataset, not one model's prior."
        )
    elif positive:
        verdict = (
            f"{len(positive)}/{len(biased)} model(s) lean FAILURE "
            f"({', '.join(b[0] for b in positive)}) — the bias is NOT universal, "
            "so it is a property of those models rather than of the task."
        )
    else:
        verdict = "No model leans FAILURE; the bias seen earlier did not reproduce."
    r.p(f"VERDICT: {verdict}")

    # --- 3. per-step means ------------------------------------------------
    r.h(2, "3. PER-STEP MEAN SCORE")
    rows = []
    for m in models:
        row = [m.name]
        for name in REWARDS:
            values = m.scores(name)
            row.append(f"{st.mean(values):.3f}" if values else "-")
        rows.append(row)
    r.table(
        ["model"] + [n.split("_")[0].upper() for n in REWARDS],
        rows,
        [16] + [9] * len(REWARDS),
    )
    r.p(
        "S3/S5 score calibration and structure, not trial-specific truth, so a "
        "model can top them without knowing anything about the trial."
    )

    # --- 4. per-trial agreement -------------------------------------------
    r.h(2, "4. PER-TRIAL AGREEMENT")
    shared = set(models[0].rows)
    for m in models[1:]:
        shared &= set(m.rows)
    r.p(f"Trials with a complete chain in every model: {len(shared)}")
    if len(models) < 2:
        r.p(
            "Skipped: agreement needs at least two models. Re-run this script once "
            "a second run directory exists."
        )
    elif not shared:
        r.p("Skipped: no trial completed its chain in every model.")
    if len(models) >= 2 and shared:
        agree_buckets: dict[str, int] = defaultdict(int)
        correct_buckets: dict[int, int] = defaultdict(int)
        unanimous_wrong = []
        split_trials = []
        n_models = len(models)
        abstained = 0
        for nct in shared:
            preds = [m.rows[nct]["predicted"] for m in models]
            if any(p is None for p in preds):
                # At least one model declined. "Do they agree?" has no answer
                # here, so these are counted apart rather than folded in as a
                # disagreement — and they are excluded from both denominators.
                abstained += 1
                continue
            top = max(preds.count("SUCCESS"), preds.count("FAILURE"))
            agree_buckets[f"{top}/{n_models}"] += 1
            n_correct = sum(
                int(m.rows[nct]["scores"].get(OUTCOME, 0.0)) for m in models
            )
            correct_buckets[n_correct] += 1
            label = meta.get(nct, {}).get("label", "?")
            if n_correct == 0:
                unanimous_wrong.append((nct, label))
            if top < n_models:
                split_trials.append((nct, label, preds))

        comparable = len(shared) - abstained
        r.p(
            f"Of those, {abstained} had at least one model abstain and are excluded "
            f"below; {comparable} trials have a committed prediction from all "
            f"{n_models} models."
        )
        if comparable == 0:
            r.p("No trial drew a committed prediction from every model.")
        else:
            r.console("")
            r.p("Predicted-label agreement (do the models say the same thing?):")
            r.table(
                ["agreement", "trials", "share"],
                [
                    [k, v, f"{v/comparable:.3f}"]
                    for k, v in sorted(agree_buckets.items(), reverse=True)
                ],
                [14, 10, 10],
            )
            r.p("Joint correctness (how many models got the trial right?):")
            r.table(
                ["models correct", "trials", "share"],
                [
                    [f"{k}/{n_models}", v, f"{v/comparable:.3f}"]
                    for k, v in sorted(correct_buckets.items(), reverse=True)
                ],
                [16, 10, 10],
            )
        r.p(
            f"Unanimously wrong: {len(unanimous_wrong)} trials. These are where every "
            "model shares the same false belief — the most informative rows to read by hand."
        )
        for nct, label in sorted(unanimous_wrong)[:10]:
            title = (meta.get(nct, {}).get("trial_title") or "")[:56]
            r.p(f"    {nct}  true={label:<8} {title}")
        if len(unanimous_wrong) > 10:
            r.p(f"    ... and {len(unanimous_wrong) - 10} more")
        r.p(
            f"Models split: {len(split_trials)} trials. Disagreement means at least one "
            "model has trial-specific information the others lack."
        )

    # --- 5. intermediate step signal --------------------------------------
    r.h(2, "5. INTERMEDIATE STEP SIGNAL (S1-S5 vs S6 correctness)")
    r.p(
        "Point-biserial correlation between each intermediate reward and whether "
        "S6 was right, within each model, over trials. This is the question the "
        "staged chain exists to answer: if the middle steps carry no signal, the "
        "model is not reasoning through them to its answer."
    )
    r.p(
        "Two correlations per step. `r(all)` uses every complete chain; "
        "`r(answered)` drops abstentions. They diverge when a model abstains, "
        "because an abstention scores S6=0 and also tends to carry thin "
        "intermediate answers — so over all trials an intermediate reward can "
        "correlate with S6 purely by tracking whether the model engaged at all. "
        "`r(answered)` is the one that answers the intended question, and the "
        "verdicts below are computed from it."
    )
    best_per_model: dict[str, tuple[str, float, float]] = {}
    all_pvalues: list[tuple[str, str, float]] = []
    for m in models:
        ans_n = m.answered()[0]
        r.console("")
        r.raw_md(f"\n**{m.name}**\n")
        r.console(f"  {m.name}")
        rows = []
        ranked = []
        for name in INTERMEDIATE:
            xs, ys = m.paired(name)
            axs, ays = m.paired(name, answered_only=True)
            corr = pearson(xs, ys)
            acorr = pearson(axs, ays)
            if corr is None and acorr is None:
                rows.append([name, len(xs), "undefined", "n/a", "-", "n/a", "constant"])
                continue
            p = pearson_permutation_p(xs, ys, rng) if corr is not None else float("nan")
            ap = (
                pearson_permutation_p(axs, ays, rng)
                if acorr is not None
                else float("nan")
            )
            note = ""
            if acorr is not None and ap == ap and ap < 0.05:
                note = "predictive at p<0.05"
            if corr is not None and acorr is not None and abs(corr - acorr) >= 0.15:
                note = "abstention-driven"
            rows.append(
                [
                    name,
                    len(xs),
                    f"{corr:+.3f}" if corr is not None else "-",
                    fmt_p(p),
                    f"{acorr:+.3f}" if acorr is not None else "-",
                    fmt_p(ap),
                    note,
                ]
            )
            if acorr is not None:
                ranked.append((abs(acorr), name, acorr, ap))
                if ap == ap:
                    all_pvalues.append((m.name, name, ap))
        r.table(
            ["step", "n", "r(all)", "p", f"r(ans,n={ans_n})", "p", ""],
            rows,
            [22, 6, 9, 9, 16, 9, 20],
        )
        inflated = [row for row in rows if row[-1] == "abstention-driven"]
        if inflated:
            r.p(
                f"    {len(inflated)} step(s) lose most of their correlation once "
                "abstentions are dropped: the apparent signal was the model "
                "declining on trials it had nothing to say about, not better "
                "reasoning producing better answers."
            )
        if ranked:
            ranked.sort(reverse=True)
            _, name, corr, p = ranked[0]
            best_per_model[m.name] = (name, corr, p)
            r.p(
                f"    strongest (answered only): {name} (r={corr:+.3f}, p={fmt_p(p)})"
                + (
                    ""
                    if p == p and p < 0.05
                    else "  <- not significant; treat as no signal"
                )
            )

    if all_pvalues:
        n_tests = len(all_pvalues)
        bonferroni = 0.05 / n_tests
        survivors = [t for t in all_pvalues if t[2] < bonferroni]
        # Benjamini-Hochberg at FDR 0.05.
        ordered = sorted(all_pvalues, key=lambda t: t[2])
        bh = 0
        for i, (_, _, pv) in enumerate(ordered, 1):
            if pv <= 0.05 * i / n_tests:
                bh = i
        r.console("")
        r.p(
            f"MULTIPLE COMPARISONS: section 5 runs {n_tests} correlation tests "
            f"({len(INTERMEDIATE)} steps x {len(models)} models). At that many "
            f"tests, ~{0.05 * n_tests:.1f} results reach p<0.05 by chance alone, "
            "so an individual star here is not evidence on its own."
        )
        r.p(
            f"  Bonferroni (p < {bonferroni:.4f}): "
            + (
                ", ".join(f"{mn}/{sn}" for mn, sn, _ in survivors)
                if survivors
                else "NO step survives in any model."
            )
        )
        r.p(
            f"  Benjamini-Hochberg (FDR 0.05): {bh} of {n_tests} rejections."
            if bh
            else f"  Benjamini-Hochberg (FDR 0.05): no rejections of {n_tests} tests."
        )
        if not survivors and not bh:
            r.p(
                "  So: no intermediate step reliably predicts S6 correctness in "
                "any model once abstention and multiplicity are both accounted "
                "for. Read the per-model 'strongest' lines below as the largest "
                "of several noisy estimates, not as findings."
            )

    if best_per_model:
        r.console("")
        r.p("Strongest intermediate predictor per model:")
        r.table(
            ["model", "step", "r", "perm p"],
            [
                [name, step, f"{corr:+.3f}", fmt_p(p)]
                for name, (step, corr, p) in best_per_model.items()
            ],
            [16, 22, 10, 10],
        )
        agreed = {step for step, _, _ in best_per_model.values()}
        sig = [n for n, (_, _, pv) in best_per_model.items() if pv == pv and pv < 0.05]
        if not sig:
            r.p(
                "No model has a significant intermediate predictor once "
                "abstentions are excluded. On this evidence the S1-S5 scores do "
                "not predict whether S6 is right — the chain's middle steps are "
                "not carrying the final answer. That is a finding about these "
                "scorers as much as about the models: S3 and S5 grade "
                "calibration and structure, which a model can satisfy without "
                "knowing anything about the trial."
            )
        elif len(agreed) == 1 and len(best_per_model) > 1:
            r.p(
                f"All models agree the strongest predictor is {agreed.pop()} "
                f"(significant for: {', '.join(sig)}) — evidence that step "
                "carries real signal rather than noise."
            )
        elif len(best_per_model) > 1:
            r.p(
                "Models disagree on which step predicts best "
                f"({', '.join(sorted(agreed))}); with n={len(models)} models and "
                "one rollout each, that is consistent with none of them carrying "
                "much signal."
            )

    # --- 6. does a better chain mean a better answer? ---------------------
    r.h(2, "6. DO BETTER INTERMEDIATE SCORES MEAN BETTER PREDICTIONS?")
    rows = []
    for m in models:
        s6 = m.scores(OUTCOME)
        row = [m.name]
        for name in ("s2_reference_class", "s3_base_rate", "s5_risk_factors"):
            values = m.scores(name)
            row.append(f"{st.mean(values):.3f}" if values else "-")
        row.append(f"{st.mean(s6):.3f}" if s6 else "-")
        rows.append(row)
    r.table(["model", "S2", "S3", "S5", "S6 acc"], rows, [16, 9, 9, 9, 10])
    r.p(
        f"This is a between-model comparison with n={len(models)} models. A "
        "correlation across that many points is not estimable, and none is "
        "reported here on purpose — the table is for eyeballing whether the "
        "ordering is even suggestive. The within-model correlations in section 5 "
        "are the statistically meaningful version of this question."
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(r.md) + "\n")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
