# Cross-model comparison

Run directory: `/Users/junyihuang/clinical-trial-reasoning/results`

models: deepseek-chat, gpt-4o-mini, qwen-plus

trials in dataset: 100


## 0. RUN COVERAGE

| model | complete | dropped | drop causes |
|---|---|---|---|
| deepseek-chat | 100 | 0 | - |
| gpt-4o-mini | 100 | 0 | - |
| qwen-plus | 100 | 0 | - |

Dropped episodes died mid-chain (usually a provider error) and score 0.0 on every reward; they are excluded below so throttling is not read as reasoning failure.


## 1. S6 ACCURACY (95% Wilson CI)

| model | answered | correct | acc | 95% CI | acc|answered | 95% CI | SUCC | FAIL |
|---|---|---|---|---|---|---|---|---|
| deepseek-chat | 99/100 (0.990) | 67/100 | 0.670 | [0.573, 0.754] | 67/99 (0.677) | [0.580, 0.761] | 29/50 | 38/50 |
| gpt-4o-mini | 98/100 (0.980) | 57/100 | 0.570 | [0.472, 0.663] | 57/98 (0.582) | [0.483, 0.674] | 24/50 | 33/50 |
| qwen-plus | 57/100 (0.570) | 46/100 | 0.460 | [0.366, 0.557] | 46/57 (0.807) | [0.687, 0.889] | 19/50 | 27/50 |

A 100-trial run at -r 1: the CI is wide by construction. Read gaps, not decimals.

`answered` is the share of complete chains where S6 committed to SUCCESS or FAILURE. An abstention (`PREDICTION: unknown`) scores 0.0, exactly like a wrong answer — so `acc` mixes being wrong with declining to answer, and `acc|answered` separates them. Compare models on both: `acc` is the number the reward optimises, `acc|answered` is the one that reflects discrimination.

  ABSTENTION: qwen-plus declined to predict on 43/100 trials. Its `acc` column understates its discrimination.


## 2. FAILURE BIAS — task artefact or model artefact?

The dataset is 50/50, so a model with no signal that guesses one class every time scores 0.500 overall while scoring 1.000 on that class. `pred SUCCESS` is the share of predictions that were SUCCESS: 0.50 is balanced, near 0.00 means the model answers FAILURE almost always. Every column here is computed over ANSWERED trials only — an abstention leans neither way, and scoring it against its own label would invent a bias for a model that merely declines to guess.

| model | pred SUCCESS | SUCCESS acc | FAILURE acc | FAILURE-SUCCESS | perm p |
|---|---|---|---|---|---|
| deepseek-chat | 40/99 (0.404) | 0.580 | 0.776 | +0.196 | 0.0539 |
| gpt-4o-mini | 41/98 (0.418) | 0.500 | 0.660 | +0.160 | 0.1577 |
| qwen-plus | 23/57 (0.404) | 0.731 | 0.871 | +0.140 | 0.3161 |

VERDICT: All 3 models lean FAILURE (0 significantly at p<0.05) — this looks like the task or the dataset, not one model's prior.


## 3. PER-STEP MEAN SCORE

| model | S1 | S2 | S3 | S4 | S5 | S6 |
|---|---|---|---|---|---|---|
| deepseek-chat | 0.530 | 0.483 | 0.465 | 0.843 | 0.793 | 0.670 |
| gpt-4o-mini | 0.090 | 0.823 | 0.535 | 0.569 | 0.765 | 0.570 |
| qwen-plus | 0.350 | 0.370 | 0.160 | 0.402 | 0.616 | 0.460 |

S3/S5 score calibration and structure, not trial-specific truth, so a model can top them without knowing anything about the trial.


## 4. PER-TRIAL AGREEMENT

Trials with a complete chain in every model: 100

Of those, 44 had at least one model abstain and are excluded below; 56 trials have a committed prediction from all 3 models.

Predicted-label agreement (do the models say the same thing?):

| agreement | trials | share |
|---|---|---|
| 3/3 | 43 | 0.768 |
| 2/3 | 13 | 0.232 |

Joint correctness (how many models got the trial right?):

| models correct | trials | share |
|---|---|---|
| 3/3 | 34 | 0.607 |
| 2/3 | 9 | 0.161 |
| 1/3 | 4 | 0.071 |
| 0/3 | 9 | 0.161 |

Unanimously wrong: 9 trials. These are where every model shares the same false belief — the most informative rows to read by hand.

    NCT02442674  true=FAILURE  A Trial of Tolvaptan in Children and Adolescent Subjects

    NCT02521233  true=FAILURE  Efficacy and Safety of Candesartan Associated With Chlor

    NCT02762760  true=SUCCESS  AP-011 Study to Evaluate the Safety of a Single Intra-ar

    NCT02838823  true=SUCCESS  Safety and Tolerability of Recombinant Humanized Anti-PD

    NCT02855892  true=SUCCESS  A Phase II Clinical Trial to Evaluate the Efficacy and S

    NCT02890719  true=FAILURE  Pilot Study Evaluate Efficacy of Grazoprevir + Elbasvir 

    NCT02906579  true=SUCCESS  A Phase 2 Trial of IW-1973, A Stimulator of Soluble Guan

    NCT03033524  true=SUCCESS  Trial to Evaluate the Safety of TTAC-0001(Tanibirumab) i

    NCT03101579  true=SUCCESS  Intrathecal Pemetrexed for Recurrent Leptomeningeal Meta

Models split: 13 trials. Disagreement means at least one model has trial-specific information the others lack.


## 5. INTERMEDIATE STEP SIGNAL (S1-S5 vs S6 correctness)

Point-biserial correlation between each intermediate reward and whether S6 was right, within each model, over trials. This is the question the staged chain exists to answer: if the middle steps carry no signal, the model is not reasoning through them to its answer.

Two correlations per step. `r(all)` uses every complete chain; `r(answered)` drops abstentions. They diverge when a model abstains, because an abstention scores S6=0 and also tends to carry thin intermediate answers — so over all trials an intermediate reward can correlate with S6 purely by tracking whether the model engaged at all. `r(answered)` is the one that answers the intended question, and the verdicts below are computed from it.


**deepseek-chat**


| step | n | r(all) | p | r(ans,n=99) | p |  |
|---|---|---|---|---|---|---|
| s1_trial_recall | 100 | +0.191 | 0.0866 | +0.179 | 0.0860 |  |
| s2_reference_class | 100 | +0.230 | 0.0268* | +0.217 | 0.0375* | predictive at p<0.05 |
| s3_base_rate | 100 | +0.019 | 0.8963 | +0.002 | 1.0000 |  |
| s4_success_criteria | 100 | +0.239 | 0.0176* | +0.251 | 0.0128* | predictive at p<0.05 |
| s5_risk_factors | 100 | -0.228 | 0.0254* | -0.215 | 0.0360* | predictive at p<0.05 |

    strongest (answered only): s4_success_criteria (r=+0.251, p=0.0128*)


**gpt-4o-mini**


| step | n | r(all) | p | r(ans,n=98) | p |  |
|---|---|---|---|---|---|---|
| s1_trial_recall | 100 | +0.132 | 0.2993 | +0.126 | 0.2940 |  |
| s2_reference_class | 100 | -0.179 | 0.0874 | -0.211 | 0.0463* | predictive at p<0.05 |
| s3_base_rate | 100 | +0.065 | 0.5151 | +0.039 | 0.7418 |  |
| s4_success_criteria | 100 | +0.056 | 0.6014 | +0.062 | 0.5427 |  |
| s5_risk_factors | 100 | +0.195 | 0.0589 | +0.178 | 0.0805 |  |

    strongest (answered only): s2_reference_class (r=-0.211, p=0.0463*)


**qwen-plus**


| step | n | r(all) | p | r(ans,n=57) | p |  |
|---|---|---|---|---|---|---|
| s1_trial_recall | 100 | +0.332 | 0.0015* | +0.269 | 0.0470* | predictive at p<0.05 |
| s2_reference_class | 100 | +0.287 | 0.0045* | +0.199 | 0.1663 |  |
| s3_base_rate | 100 | +0.350 | 0.0001* | +0.106 | 0.5142 | abstention-driven |
| s4_success_criteria | 100 | +0.327 | 0.0015* | +0.028 | 0.8846 | abstention-driven |
| s5_risk_factors | 100 | +0.463 | 0.0001* | -0.179 | 0.2147 | abstention-driven |

    3 step(s) lose most of their correlation once abstentions are dropped: the apparent signal was the model declining on trials it had nothing to say about, not better reasoning producing better answers.

    strongest (answered only): s1_trial_recall (r=+0.269, p=0.0470*)

MULTIPLE COMPARISONS: section 5 runs 15 correlation tests (5 steps x 3 models). At that many tests, ~0.8 results reach p<0.05 by chance alone, so an individual star here is not evidence on its own.

  Bonferroni (p < 0.0033): NO step survives in any model.

  Benjamini-Hochberg (FDR 0.05): no rejections of 15 tests.

  So: no intermediate step reliably predicts S6 correctness in any model once abstention and multiplicity are both accounted for. Read the per-model 'strongest' lines below as the largest of several noisy estimates, not as findings.

Strongest intermediate predictor per model:

| model | step | r | perm p |
|---|---|---|---|
| deepseek-chat | s4_success_criteria | +0.251 | 0.0128* |
| gpt-4o-mini | s2_reference_class | -0.211 | 0.0463* |
| qwen-plus | s1_trial_recall | +0.269 | 0.0470* |

Models disagree on which step predicts best (s1_trial_recall, s2_reference_class, s4_success_criteria); with n=3 models and one rollout each, that is consistent with none of them carrying much signal.


## 6. DO BETTER INTERMEDIATE SCORES MEAN BETTER PREDICTIONS?

| model | S2 | S3 | S5 | S6 acc |
|---|---|---|---|---|
| deepseek-chat | 0.483 | 0.465 | 0.793 | 0.670 |
| gpt-4o-mini | 0.823 | 0.535 | 0.765 | 0.570 |
| qwen-plus | 0.370 | 0.160 | 0.616 | 0.460 |

This is a between-model comparison with n=3 models. A correlation across that many points is not estimable, and none is reported here on purpose — the table is for eyeballing whether the ordering is even suggestive. The within-model correlations in section 5 are the statistically meaningful version of this question.

