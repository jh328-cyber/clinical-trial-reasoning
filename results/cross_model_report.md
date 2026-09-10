# Cross-model comparison

Run directory: `/Users/junyihuang/clinical-trial-reasoning/results`

models: gpt-4o-mini, qwen-plus

trials in dataset: 100

NOTE: 2 model(s) present. Sections keyed to three-way agreement degrade to what the available runs support.


## 0. RUN COVERAGE

| model | complete | dropped | drop causes |
|---|---|---|---|
| gpt-4o-mini | 100 | 0 | - |
| qwen-plus | 100 | 0 | - |

Dropped episodes died mid-chain (usually a provider error) and score 0.0 on every reward; they are excluded below so throttling is not read as reasoning failure.


## 1. S6 ACCURACY (95% Wilson CI)

| model | answered | correct | acc | 95% CI | acc|answered | 95% CI | SUCC | FAIL |
|---|---|---|---|---|---|---|---|---|
| gpt-4o-mini | 98/100 (0.980) | 57/100 | 0.570 | [0.472, 0.663] | 57/98 (0.582) | [0.483, 0.674] | 24/50 | 33/50 |
| qwen-plus | 57/100 (0.570) | 46/100 | 0.460 | [0.366, 0.557] | 46/57 (0.807) | [0.687, 0.889] | 19/50 | 27/50 |

A 100-trial run at -r 1: the CI is wide by construction. Read gaps, not decimals.

`answered` is the share of complete chains where S6 committed to SUCCESS or FAILURE. An abstention (`PREDICTION: unknown`) scores 0.0, exactly like a wrong answer — so `acc` mixes being wrong with declining to answer, and `acc|answered` separates them. Compare models on both: `acc` is the number the reward optimises, `acc|answered` is the one that reflects discrimination.

  ABSTENTION: qwen-plus declined to predict on 43/100 trials. Its `acc` column understates its discrimination.


## 2. FAILURE BIAS — task artefact or model artefact?

The dataset is 50/50, so a model with no signal that guesses one class every time scores 0.500 overall while scoring 1.000 on that class. `pred SUCCESS` is the share of predictions that were SUCCESS: 0.50 is balanced, near 0.00 means the model answers FAILURE almost always. Every column here is computed over ANSWERED trials only — an abstention leans neither way, and scoring it against its own label would invent a bias for a model that merely declines to guess.

| model | pred SUCCESS | SUCCESS acc | FAILURE acc | FAILURE-SUCCESS | perm p |
|---|---|---|---|---|---|
| gpt-4o-mini | 41/98 (0.418) | 0.500 | 0.660 | +0.160 | 0.1436 |
| qwen-plus | 23/57 (0.404) | 0.731 | 0.871 | +0.140 | 0.3156 |

VERDICT: All 2 models lean FAILURE (0 significantly at p<0.05) — this looks like the task or the dataset, not one model's prior.


## 3. PER-STEP MEAN SCORE

| model | S1 | S2 | S3 | S4 | S5 | S6 |
|---|---|---|---|---|---|---|
| gpt-4o-mini | 0.090 | 0.823 | 0.535 | 0.569 | 0.765 | 0.570 |
| qwen-plus | 0.350 | 0.370 | 0.160 | 0.402 | 0.616 | 0.460 |

S3/S5 score calibration and structure, not trial-specific truth, so a model can top them without knowing anything about the trial.


## 4. PER-TRIAL AGREEMENT

Trials with a complete chain in every model: 100

Of those, 43 had at least one model abstain and are excluded below; 57 trials have a committed prediction from all 2 models.

Predicted-label agreement (do the models say the same thing?):

| agreement | trials | share |
|---|---|---|
| 2/2 | 45 | 0.789 |
| 1/2 | 12 | 0.211 |

Joint correctness (how many models got the trial right?):

| models correct | trials | share |
|---|---|---|
| 2/2 | 35 | 0.614 |
| 1/2 | 12 | 0.211 |
| 0/2 | 10 | 0.175 |

Unanimously wrong: 10 trials. These are where every model shares the same false belief — the most informative rows to read by hand.

    NCT02442674  true=FAILURE  A Trial of Tolvaptan in Children and Adolescent Subjects

    NCT02521233  true=FAILURE  Efficacy and Safety of Candesartan Associated With Chlor

    NCT02762760  true=SUCCESS  AP-011 Study to Evaluate the Safety of a Single Intra-ar

    NCT02838823  true=SUCCESS  Safety and Tolerability of Recombinant Humanized Anti-PD

    NCT02855892  true=SUCCESS  A Phase II Clinical Trial to Evaluate the Efficacy and S

    NCT02888106  true=SUCCESS  Myrcludex B in Combination With Peginterferon Alfa-2a Ve

    NCT02890719  true=FAILURE  Pilot Study Evaluate Efficacy of Grazoprevir + Elbasvir 

    NCT02906579  true=SUCCESS  A Phase 2 Trial of IW-1973, A Stimulator of Soluble Guan

    NCT03033524  true=SUCCESS  Trial to Evaluate the Safety of TTAC-0001(Tanibirumab) i

    NCT03101579  true=SUCCESS  Intrathecal Pemetrexed for Recurrent Leptomeningeal Meta

Models split: 12 trials. Disagreement means at least one model has trial-specific information the others lack.


## 5. INTERMEDIATE STEP SIGNAL (S1-S5 vs S6 correctness)

Point-biserial correlation between each intermediate reward and whether S6 was right, within each model, over trials. This is the question the staged chain exists to answer: if the middle steps carry no signal, the model is not reasoning through them to its answer.

Two correlations per step. `r(all)` uses every complete chain; `r(answered)` drops abstentions. They diverge when a model abstains, because an abstention scores S6=0 and also tends to carry thin intermediate answers — so over all trials an intermediate reward can correlate with S6 purely by tracking whether the model engaged at all. `r(answered)` is the one that answers the intended question, and the verdicts below are computed from it.


**gpt-4o-mini**


| step | n | r(all) | p | r(ans,n=98) | p |  |
|---|---|---|---|---|---|---|
| s1_trial_recall | 100 | +0.132 | 0.2883 | +0.126 | 0.3013 |  |
| s2_reference_class | 100 | -0.179 | 0.0819 | -0.211 | 0.0463* | predictive at p<0.05 |
| s3_base_rate | 100 | +0.065 | 0.5153 | +0.039 | 0.7455 |  |
| s4_success_criteria | 100 | +0.056 | 0.5875 | +0.062 | 0.5506 |  |
| s5_risk_factors | 100 | +0.195 | 0.0582 | +0.178 | 0.0771 |  |

    strongest (answered only): s2_reference_class (r=-0.211, p=0.0463*)


**qwen-plus**


| step | n | r(all) | p | r(ans,n=57) | p |  |
|---|---|---|---|---|---|---|
| s1_trial_recall | 100 | +0.332 | 0.0025* | +0.269 | 0.0498* | predictive at p<0.05 |
| s2_reference_class | 100 | +0.287 | 0.0040* | +0.199 | 0.1676 |  |
| s3_base_rate | 100 | +0.350 | 0.0006* | +0.106 | 0.5236 | abstention-driven |
| s4_success_criteria | 100 | +0.327 | 0.0013* | +0.028 | 0.8812 | abstention-driven |
| s5_risk_factors | 100 | +0.463 | 0.0001* | -0.179 | 0.2103 | abstention-driven |

    3 step(s) lose most of their correlation once abstentions are dropped: the apparent signal was the model declining on trials it had nothing to say about, not better reasoning producing better answers.

    strongest (answered only): s1_trial_recall (r=+0.269, p=0.0498*)

Strongest intermediate predictor per model:

| model | step | r | perm p |
|---|---|---|---|
| gpt-4o-mini | s2_reference_class | -0.211 | 0.0463* |
| qwen-plus | s1_trial_recall | +0.269 | 0.0498* |

Models disagree on which step predicts best (s1_trial_recall, s2_reference_class); with n=2 models and one rollout each, that is consistent with none of them carrying much signal.


## 6. DO BETTER INTERMEDIATE SCORES MEAN BETTER PREDICTIONS?

| model | S2 | S3 | S5 | S6 acc |
|---|---|---|---|---|
| gpt-4o-mini | 0.823 | 0.535 | 0.765 | 0.570 |
| qwen-plus | 0.370 | 0.160 | 0.616 | 0.460 |

This is a between-model comparison with n=2 models. A correlation across that many points is not estimable, and none is reported here on purpose — the table is for eyeballing whether the ordering is even suggestive. The within-model correlations in section 5 are the statistically meaningful version of this question.

