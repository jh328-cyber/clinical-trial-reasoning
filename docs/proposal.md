# Reasoning Process Proposal

**Clinical Trial Reasoning Environment**
Junyi Huang · Abugoot Lab, Harvard Medical School
Draft for review by Sean Pohorence and Hao Zhu

---

## 1. Motivation

The question this project asks is not *"can an LLM predict clinical trial outcomes?"* but
**"what is the model actually doing when it predicts one?"** That reframing changes what
we need to build.

**Why not free-form chain-of-thought.** Free-form CoT produces one undifferentiated blob
of text per trial. It is not comparable across trials (every rollout reasons in a different
order, at different depth), not attributable (when the final label is wrong we cannot say
*which* inference was wrong), and not intervenable (we cannot correct step 3 and re-run
steps 4–6 to measure the downstream effect). Worse, CoT text is only weakly coupled to the
answer — a model can produce plausible prose and then emit a label reached by other means,
so the trace is not reliable evidence about the computation.

**Why structured steps.** If instead the episode is a fixed sequence of questions, each
answered in its own turn and in its own schema, then every step becomes a measurable
variable. We get per-step accuracy, per-step failure rates, and a step-by-step profile of
where reasoning degrades. Sean's framing:

> a sequence of predictions or questions, the last question being: *What's the outcome?*

and concretely:

> first recall X, Y, Z about this trial. then make a list of similar trials you know of.

This mirrors the structure of `drug-perturbation-rl`, which decomposed phenotype
prediction into target → mechanism of action → pathway → phenotype, and reported that the
chain made it possible to "track and reward the model's reasoning for each step, leading
to more signal and better final results." We adopt the same shape for trial outcomes.

**A second motivation specific to this domain: contamination.** Almost every trial with a
known outcome completed before the model's training cutoff. A model may not be reasoning
at all — it may be recalling. A structured process lets us *measure* that instead of
worrying about it, by making recall its own scored step (§2, S1–S2) and by running the
same trials under a closed-book and an open-book condition (§4).

---

## 2. Proposed Reasoning Steps

Six steps. Each is issued as a separate turn; the model must answer before it sees the
next question, and cannot revise an earlier answer. Steps 1–3 are deliberately
**trial-agnostic priors** (what does the model bring to this trial?); steps 4–6 are
**trial-specific judgment**.

### S1 — Trial Recall

**Question.** "Here is an NCT ID and the trial's registered title. Without any tools, state
what you know about this trial: intervention and its molecular target / mechanism,
indication, phase, lead sponsor, planned enrollment, the pre-specified primary endpoint,
and the registration and primary-completion dates. Mark any field you do not know as
`unknown` — do not guess."

**Output.** JSON object with those fields plus a per-field `known: true|false`.

**Why it is useful.** This is the contamination probe and the foundation of everything
after it. Scored against the ClinicalTrials.gov record, it gives a per-field recall F1 and,
separately, a **fabrication rate** (fields asserted confidently and wrong vs. correctly
marked `unknown`). A model that recalls the primary endpoint of a 2015 phase 3 trial
verbatim is in a different epistemic regime than one that knows only the drug class, and
every downstream step must be read conditional on which regime we are in.

### S2 — Reference Class Construction

**Question.** "List up to 8 other trials you know of that you would put in the same
reference class as this one — same target or mechanism, same indication, comparable phase.
For each, give NCT ID if you know it, drug, sponsor, phase, and its outcome
(success / failure / unknown)."

**Output.** JSON array of reference trials.

**Why it is useful.** This is Sean's "make a list of similar trials you know of," and it is
the single most diagnostic step in the chain. It exposes three things at once:
(a) **hallucination rate** — do the NCT IDs resolve, and do the resolved records match the
claimed drug/indication? (b) **retrieval quality** — how relevant is the class the model
constructs, judged against a programmatically built reference class from
ClinicalTrials.gov? (c) **prior correctness** — are the outcomes it attributes to those
trials actually right? A model reasoning from a reference class of half-invented trials
can still land the right final label, and we would never know without this step.

### S3 — Base Rate Estimate

**Question.** "Given the reference class you just constructed, what fraction of trials like
this one succeed? Give a probability and one sentence of justification."

**Output.** `{"base_rate": float, "justification": str}`.

**Why it is useful.** Calibration anchor. It is scored against the empirical success rate
of the matching (phase × indication-area) cell computed from the labeled corpus — not
against the individual trial's outcome. Separating the base rate from the final prediction
lets us decompose the final error into *"wrong prior"* vs. *"wrong update on the prior"*,
which is exactly the decomposition free-form CoT destroys.

### S4 — Success Criterion

**Question.** "From the registered design alone, state what would have to be true for this
trial to be a success: the pre-specified primary endpoint, the analysis population, the
alpha, and any design feature that changes the bar — non-inferiority margin, co-primary
endpoints, single-arm ORR threshold, group-sequential interim boundary."

**Output.** JSON: `primary_endpoint`, `population`, `alpha`, `design_features[]`,
`success_condition` (one sentence).

**Why it is useful.** This is a **methodological-competence** check, independent of the
outcome, and it is scorable against the registered record. It carries over the
phase-and-design applicability logic and the design-specific qualifications
(non-inferiority requires a pre-specified justified margin plus a conservative population;
one-of-two co-primaries is mixed, not success; futility stop is an efficacy failure, not an
operational one) that the prior pipeline's adjudicator prompt already encodes. If a model
cannot state the bar, any verdict it later gives about clearing the bar is unearned.

### S5 — Risk-Factor Enumeration

**Question.** "Enumerate the specific ways this trial could fail, one dimension at a time:
efficacy, safety, regulatory, operational. For each, give a concrete hypothesis, a
direction, and how much weight you place on it. Say `not applicable` where the dimension
does not apply at this phase and design."

**Output.** JSON keyed by the four dimensions; each entry
`{applicable, hypothesis, weight}`.

**Why it is useful.** This reuses the five-dimensional decomposition from the prior
pipeline (efficacy / safety / regulatory / operational / post-decision), but repurposes it:
there it was the *output schema*, here it is a *reasoning step*. It forces the model to
commit to a mechanism before it commits to a label, so we can ask the question that matters
most for scientific credit — **does the model get trials right for the right reason?** A
prediction of FAILURE justified by a safety hypothesis on a trial that actually failed for
enrollment futility is a right answer with wrong reasoning, and this step is what makes
that visible.

### S6 — Outcome Prediction

**Question.** "What is the outcome of this trial? Give SUCCESS or FAILURE, a probability,
and the single most decisive factor from your earlier steps."

**Output.** `{"outcome": "SUCCESS"|"FAILURE", "probability": float, "decisive_factor": str,
"decisive_step": "S1".."S5"}`.

**Why it is useful.** The terminal question, plus a self-report of which earlier step
drove it. The self-report is itself data: we can check whether the claimed decisive step
is the one that actually moves the prediction, by re-running the episode with that step's
answer perturbed (§3).

### Reward shape

Following the `drug-perturbation-rl` pattern of a weighted composite over intermediate
metrics, with a proposed starting allocation (to be tuned, and deliberately weighted so
that intermediate reasoning is worth roughly as much as the final label):

```
R = 0.10 · recall_F1(S1)
  + 0.15 · refclass_score(S2)        # validity × relevance × outcome-correctness
  + 0.10 · calibration(S3)           # 1 - |estimate - empirical base rate|
  + 0.10 · criterion_match(S4)
  + 0.15 · risk_factor_score(S5)     # judge-scored against the true failure mode
  + 0.40 · outcome_score(S6)         # label correctness, Brier-penalized
```

An explicit non-goal: we do **not** want the model to maximize final-label accuracy by
abstaining or by pattern-matching sponsor names. Weighting the intermediate steps at 0.60
is the mechanism for that.

---

## 3. How This Helps Us Understand Model Reasoning

**Per-step accuracy profiles.** For every trial we get six scored outputs instead of one.
Aggregated, this answers questions we currently cannot: does the model fail because it
does not know the trial (S1), because it invents a reference class (S2), because its prior
is miscalibrated (S3), because it misreads the design (S4), or because it updates
incorrectly on evidence it correctly identified (S5→S6)?

**Recall/reason separation.** The correlation between S1 recall quality and S6 accuracy is
a direct measure of how much of the model's apparent predictive skill is memorization. If
accuracy collapses on trials the model cannot recall, we are measuring contamination, not
reasoning — and that is a publishable negative result, not a failure of the project.

**Causal intervention, not just observation.** Because the environment — not the prompt —
controls the turn sequence, we can intervene between steps: inject a *corrected* S2
reference class and measure how much S6 improves; delete S3 and see whether calibration
degrades; permute step order; run S4 before S1. This yields causal claims about which
reasoning steps carry the prediction. Free-form CoT admits none of these interventions.

**Right answer / wrong reason detection.** S5 plus the labeled failure mode gives a
2×2: correct label with correct mechanism, correct label with wrong mechanism, and the two
error cells. The off-diagonal "correct label, wrong mechanism" cell is, in our view, the
most interesting thing this environment can measure.

**Relation to Rayane's masking approach.** *(This section needs Rayane's input — the
description below is my current understanding and should be corrected.)* As I understand
it, the masking work perturbs the **input**: hide or ablate parts of the trial record and
observe how the prediction shifts, which tells us which *fields* the model depends on.
The step decomposition here perturbs the **process**: it opens up the intermediate
computation and lets us intervene on inferences rather than inputs. The two are
complementary and compose directly — masking a field in S1's input and watching the effect
propagate through S2–S6 tells us not just *that* a field mattered but *through which
reasoning step* it mattered. If the two efforts converge, input-masking sensitivity should
be predictable from step-level dependencies, and a disagreement would itself be a finding.

---

## 4. Implementation Plan

### Environment

Built on `verifiers` v1 (`import verifiers.v1 as vf`), scaffolded with
`uv run init clinical-trial-reasoning`.

- **`TrialData(vf.TaskData)`** — `nct_id`, registration-time CTG fields, the TrialBench
  label, and the pre-computed ground truth for each step (reference class, empirical base
  rate, registered success criterion, labeled failure mode).
- **`StagedReasoningEnv(vf.Env)`** — the core piece. `verifiers` exposes
  `agent.interaction(task)` with `await interaction.turn(message)`, which sends one user
  turn and runs one harness segment. The environment issues S1…S6 as six successive
  `turn()` calls, so **step order is enforced by the environment rather than requested in
  the prompt** — the model cannot skip ahead, and each step's answer lands as its own
  assistant message in the `Trace`. The ablation and intervention experiments in §3 are
  then just variations on this `run()` method.
- **Scoring** — each step is a `@vf.metric` (recorded per-step, so the per-step profile is
  in the trace by construction) and the weighted composite is the `@vf.reward`. S1, S3, S4
  are deterministic scorers against the CTG record and the corpus; S2 mixes deterministic
  NCT-ID validation with a relevance judge; S5 uses a `vf.Judge`.
- **`TrialToolset(vf.Toolset)`** — for the open-book arm only. The prior pipeline's
  retrieval modules (ClinicalTrials.gov v2, FDA, PubMed, sponsor press, sponsor-site /
  Wayback, news) port over as `@vf.tool` methods; `verifiers` installs them into the
  harness as an MCP server. This is exactly the `wiki_search` environment's pattern.

### Experimental arms

| Arm | Tools | Purpose |
|---|---|---|
| **A — closed-book** | none | Measures priors and memorization. The primary arm for the reasoning question. |
| **B — open-book, time-gated** | retrieval tools restricted to sources dated before primary completion | Measures evidence integration under realistic prediction conditions. |
| **C — open-book, unrestricted** | full retrieval | Upper bound; also the leakage control — the gap B→C quantifies how much of the signal is post-hoc. |

Leakage control is not optional here. The registered fields shown to the model must exclude
`overallStatus`, `whyStopped`, and `resultsSection`, all of which encode the answer. A
prior GEPA optimization run on the old pipeline had to be quarantined for exactly this
class of leakage, and that lesson carries forward.

### Data

Reused from the prior pipeline, which is a real head start:

- **TrialBench labels** (~17.6k labeled trials) as the outcome ground truth.
- **A frozen 100-trial phase/label-balanced manifest** already split 30 train / 30 val /
  40 test, seed 42, SHA256-pinned — usable immediately as the development set.
- **Frozen evidence bundles** (one per trial, cached) so the open-book arms are
  reproducible and do not re-hit live APIs on every rollout.
- **Two hand-adjudicated gold trials** (Anthera NCT02514967, Intarcia NCT03060980) with
  full five-dimensional verdicts — the anchors for validating S4 and S5 scorers.

New data work required: build the programmatic reference class per trial (for S2), compute
per-(phase × indication) empirical base rates (for S3), and extract the registered success
criterion (for S4). All three are derivable from ClinicalTrials.gov plus the label set.

### Stack

`uv` (the repo mandates `uv run` over bare `python`) · `verifiers` v1 · `subprocess`
runtime for development, `docker` for scaled evaluation · MCP toolset for the open-book
arms · results reported as per-step metric tables, not a single accuracy number.

### Sequencing

1. Port the frozen 100-trial dev set into `TrialData`; build the S2/S3/S4 ground truth.
2. Implement `StagedReasoningEnv` with S1, S2, S6 only — the minimum chain that tests the
   contamination hypothesis — and run arm A.
3. Add S3–S5 and their scorers; validate S4/S5 against the two gold trials.
4. Add the toolset and run arms B and C; report the B→C gap.
5. Ablation and intervention studies (§3), which are edits to `Env.run` rather than new
   infrastructure.
6. Only then consider RL. Everything above is evaluation; the environment is
   training-ready by construction, but the scientific question is answerable without
   training a model.

---

## Open questions for Sean and Hao

1. **Step count and granularity.** Six steps versus `drug-perturbation-rl`'s four — is
   this the right resolution, or should S3 fold into S2 and S4 into S5?
2. **Is the closed-book arm the primary one?** It is the cleanest probe of reasoning, but
   it is also the least like the real prediction task.
3. **Reward weights.** The 0.60 / 0.40 intermediate-to-final split is a guess. For
   evaluation it does not matter much; for RL it determines what gets learned.
4. **Rayane's masking approach** — §3 needs correcting by someone who knows the actual
   design, and we should decide whether to unify the two under one environment.
5. **Scope of the outcome label.** The prior pipeline emitted five orthogonal verdicts plus
   an overall. Here S6 predicts a single binary. Should the terminal step instead predict
   the full five-dimensional verdict?
