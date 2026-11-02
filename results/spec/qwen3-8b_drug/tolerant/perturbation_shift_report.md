# Perturbation shift report — qwen3-8b_drug / drug_perturbed

Baseline rollouts: 42 trials (0 with unparseable S6 dropped). Perturbed cases joined: 166. Skipped: none.

dP = P(SUCCESS | perturbed) − P(SUCCESS | baseline). Tolerance for 'no movement': ±0.05. 'agree' = sign of dP matches the stated direction (harmful ⇒ dP < −0.05, helpful ⇒ dP > +0.05, neutral ⇒ |dP| ≤ 0.05).

Baseline predicted-SUCCESS rate: 62%; baseline S6 accuracy: 52%.

## Per perturbation

| ID | type | expected | n | mean dP | median dP | flip | → fail | → success | agree (expected) | agree (expert) | S5 reasoning shift | S5 mentions signal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SMILES-01 | smiles_toxicophore | harmful | 39 | +0.003 | +0.000 | 18% | 33% | 28% | 33% | — | 0.68 | 4% |
| SMILES-02 | smiles_toxicophore | harmful | 39 | +0.032 | +0.000 | 23% | 23% | 28% | 23% | — | 0.68 | 0% |
| SMILES-03 | smiles_toxicophore | harmful | 39 | -0.004 | +0.000 | 13% | 41% | 31% | 41% | — | 0.68 | 5% |
| SMILES-04 | smiles_toxicophore | harmful | 39 | +0.017 | +0.000 | 21% | 23% | 28% | 23% | — | 0.68 | 0% |
| SMILES-05 | smiles_toxicophore | harmful | 10 | +0.025 | +0.025 | 20% | 30% | 30% | 30% | — | 0.69 | 0% |

## Per category

| type | n | mean dP | flip | → fail | → success | agree (expected) | S5 reasoning shift | S5 mentions signal |
|---|---|---|---|---|---|---|---|---|
| smiles_toxicophore | 166 | +0.013 | 19% | 30% | 29% | 30% | 0.68 | 2% |

## Largest movers (mean dP)

Most toward FAILURE: SMILES-03 (-0.00), SMILES-01 (+0.00), SMILES-04 (+0.02), SMILES-05 (+0.03), SMILES-02 (+0.03)

Most toward SUCCESS: SMILES-02 (+0.03), SMILES-05 (+0.03), SMILES-04 (+0.02), SMILES-01 (+0.00), SMILES-03 (-0.00)

## Reading guide

- A perturbation the model *reasons about* should show (a) dP in the stated direction, (b) a high S5 signal-mention rate, and (c) a non-trivial S5 reasoning shift.
- dP ≈ 0 with high S5 signal-mention = the model saw the signal, discussed it, and did not change its answer (reasoning–answer disconnect, as in arm A).
- dP ≈ 0 with low S5 signal-mention = the model did not pick the signal up at all.
- 'agree (expert)' fills in once expert_label is set in the catalogue; until then it is —.
