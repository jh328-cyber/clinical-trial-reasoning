# Fig 2D — drug-identity effect (named vs masked)

Controlled, causal counterpart of the seen/unseen memorization split: take the **same** trial
and remove the drug identity, then see if behaviour changes.

## Generate the masked inputs
```
python3 scripts/mask_specs.py          # -> data/masked_{baseline,perturbed}_specs_v0.jsonl
```
`mask_specs.py` redacts the drug name (intervention names + free-text mentions) -> "the study
drug" and `leadSponsor` -> "the sponsor" across the spec. Residual name-leak: 0/100 and 0/2090.
Pilot subsets (`masked_pilot_*`) restrict to the 20 pilot trials.

## Run (same spec-mode eval as everything else)
Run `named` (baseline_specs_v0 / perturbed_specs_v0) and `masked` (masked_*) through the
verifiers chain, e.g. for base Qwen3-8B and TP, the 100-trial baselines:
```
scripts/run_spec_mode.sh <model> data/baseline_specs_v0.jsonl         named_baseline
scripts/run_spec_mode.sh <model> data/masked_baseline_specs_v0.jsonl  masked_baseline
```

## Analysis
Graded P / PREDICTION from S6, paired by trial. Per model, McNemar on (a) baseline accuracy and
(b) **S6 parse success** (does masking break the final answer?).

## Result (n=100 baselines)
| named -> masked | base Qwen3-8B | adapted Qwen-3-8B-TP |
|---|---|---|
| accuracy | 63% -> 66% (p=0.66 n.s.) | 72% -> 64% (p=0.34 n.s.) |
| readable final answer | 100% -> 100% (robust) | 80% -> 63% (McNemar **p=0.008**) |

Base is robust to masking the name; **TP depends on it** — masking the name significantly
degrades TP's output (repetition loops / empty schema), while accuracy on the parsed subset
drops directionally (n.s.). Caveat: masking the name doesn't remove mechanism/class, so this is
a lower bound on identity dependence.
