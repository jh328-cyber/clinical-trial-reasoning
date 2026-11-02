# Perturbation shift report — qwen3-8b-tp_drug / drug_perturbed

Baseline rollouts: 36 trials (6 with unparseable S6 dropped). Perturbed cases joined: 128. Skipped: {'no baseline rollout for trial': 22, 'S6 unparseable': 16}.

dP = P(SUCCESS | perturbed) − P(SUCCESS | baseline). Tolerance for 'no movement': ±0.05. 'agree' = sign of dP matches the stated direction (harmful ⇒ dP < −0.05, helpful ⇒ dP > +0.05, neutral ⇒ |dP| ≤ 0.05).

Baseline predicted-SUCCESS rate: 39%; baseline S6 accuracy: 67%.

## Per perturbation

| ID | type | expected | n | mean dP | median dP | flip | → fail | → success | agree (expected) | agree (expert) | S5 reasoning shift | S5 mentions signal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SMILES-01 | smiles_toxicophore | harmful | 32 | +0.020 | +0.000 | 9% | 22% | 16% | 22% | — | 0.72 | 1% |
| SMILES-02 | smiles_toxicophore | harmful | 30 | -0.020 | +0.000 | 10% | 30% | 23% | 30% | — | 0.71 | 0% |
| SMILES-03 | smiles_toxicophore | harmful | 32 | -0.017 | +0.000 | 6% | 25% | 9% | 25% | — | 0.73 | 1% |
| SMILES-04 | smiles_toxicophore | harmful | 28 | -0.025 | +0.000 | 7% | 29% | 11% | 29% | — | 0.74 | 0% |
| SMILES-05 | smiles_toxicophore | harmful | 6 | -0.033 | -0.025 | 0% | 33% | 17% | 33% | — | 0.75 | 0% |

## Per category

| type | n | mean dP | flip | → fail | → success | agree (expected) | S5 reasoning shift | S5 mentions signal |
|---|---|---|---|---|---|---|---|---|
| smiles_toxicophore | 128 | -0.011 | 8% | 27% | 15% | 27% | 0.73 | 0% |

## Largest movers (mean dP)

Most toward FAILURE: SMILES-05 (-0.03), SMILES-04 (-0.03), SMILES-02 (-0.02), SMILES-03 (-0.02), SMILES-01 (+0.02)

Most toward SUCCESS: SMILES-01 (+0.02), SMILES-03 (-0.02), SMILES-02 (-0.02), SMILES-04 (-0.03), SMILES-05 (-0.03)

## Reading guide

- A perturbation the model *reasons about* should show (a) dP in the stated direction, (b) a high S5 signal-mention rate, and (c) a non-trivial S5 reasoning shift.
- dP ≈ 0 with high S5 signal-mention = the model saw the signal, discussed it, and did not change its answer (reasoning–answer disconnect, as in arm A).
- dP ≈ 0 with low S5 signal-mention = the model did not pick the signal up at all.
- 'agree (expert)' fills in once expert_label is set in the catalogue; until then it is —.
