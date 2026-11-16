# Perturbation shift report — qwen3-8b-tp_drug / drug_perturbed

Baseline rollouts: 3 trials (39 with unparseable S6 dropped). Perturbed cases joined: 6. Skipped: {'no baseline rollout for trial': 154, 'S6 unparseable': 6}.

dP = P(SUCCESS | perturbed) − P(SUCCESS | baseline). Tolerance for 'no movement': ±0.05. 'agree' = sign of dP matches the stated direction (harmful ⇒ dP < −0.05, helpful ⇒ dP > +0.05, neutral ⇒ |dP| ≤ 0.05).

Baseline predicted-SUCCESS rate: 100%; baseline S6 accuracy: 67%.

## Per perturbation

| ID | type | expected | n | mean dP | median dP | flip | → fail | → success | agree (expected) | agree (expert) | S5 reasoning shift | S5 mentions signal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SMILES-01 | smiles_toxicophore | harmful | 1 | +0.000 | +0.000 | 0% | 0% | 0% | 0% | — | 0.64 | 0% |
| SMILES-02 | smiles_toxicophore | harmful | 2 | -0.075 | -0.075 | 0% | 50% | 0% | 50% | — | 0.70 | 0% |
| SMILES-03 | smiles_toxicophore | harmful | 2 | +0.000 | +0.000 | 0% | 0% | 0% | 0% | — | 0.72 | 0% |
| SMILES-04 | smiles_toxicophore | harmful | 1 | -0.050 | -0.050 | 0% | 0% | 0% | 0% | — | 0.75 | 0% |

## Per category

| type | n | mean dP | flip | → fail | → success | agree (expected) | S5 reasoning shift | S5 mentions signal |
|---|---|---|---|---|---|---|---|---|
| smiles_toxicophore | 6 | -0.033 | 0% | 17% | 0% | 17% | 0.71 | 0% |

## Largest movers (mean dP)

Most toward FAILURE: SMILES-02 (-0.08), SMILES-04 (-0.05), SMILES-01 (+0.00), SMILES-03 (+0.00)

Most toward SUCCESS: SMILES-03 (+0.00), SMILES-01 (+0.00), SMILES-04 (-0.05), SMILES-02 (-0.08)

## Reading guide

- A perturbation the model *reasons about* should show (a) dP in the stated direction, (b) a high S5 signal-mention rate, and (c) a non-trivial S5 reasoning shift.
- dP ≈ 0 with high S5 signal-mention = the model saw the signal, discussed it, and did not change its answer (reasoning–answer disconnect, as in arm A).
- dP ≈ 0 with low S5 signal-mention = the model did not pick the signal up at all.
- 'agree (expert)' fills in once expert_label is set in the catalogue; until then it is —.
