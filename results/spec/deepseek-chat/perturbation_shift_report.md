# Perturbation shift report — deepseek-chat / pilot_perturbed

Baseline rollouts: 20 trials (0 with unparseable S6 dropped). Perturbed cases joined: 414. Skipped: none.

dP = P(SUCCESS | perturbed) − P(SUCCESS | baseline). Tolerance for 'no movement': ±0.05. 'agree' = sign of dP matches the stated direction (harmful ⇒ dP < −0.05, helpful ⇒ dP > +0.05, neutral ⇒ |dP| ≤ 0.05).

Baseline predicted-SUCCESS rate: 30%; baseline S6 accuracy: 80%.

## Per perturbation

| ID | type | expected | n | mean dP | median dP | flip | → fail | → success | agree (expected) | agree (expert) | S5 reasoning shift | S5 mentions signal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A01 | ae_sae_signal | harmful | 20 | +0.005 | +0.020 | 10% | 20% | 25% | 20% | — | 0.76 | 92% |
| A02 | ae_sae_signal | harmful | 20 | +0.023 | +0.020 | 10% | 20% | 45% | 20% | — | 0.77 | 80% |
| A03 | ae_sae_signal | harmful | 19 | +0.003 | +0.020 | 11% | 32% | 26% | 32% | — | 0.77 | 81% |
| A04 | ae_sae_signal | harmful | 20 | +0.012 | +0.020 | 10% | 20% | 25% | 20% | — | 0.78 | 99% |
| A05 | ae_sae_signal | harmful | 20 | -0.023 | +0.000 | 15% | 25% | 20% | 25% | — | 0.76 | 90% |
| A06 | ae_sae_signal | harmful | 20 | -0.017 | +0.000 | 15% | 30% | 25% | 30% | — | 0.77 | 73% |
| A07 | ae_sae_signal | harmful | 20 | +0.050 | +0.020 | 15% | 5% | 35% | 5% | — | 0.76 | 94% |
| A08 | ae_sae_signal | harmful | 20 | +0.012 | +0.000 | 10% | 20% | 25% | 20% | — | 0.76 | 85% |
| A09 | ae_sae_signal | harmful | 20 | -0.002 | +0.010 | 15% | 30% | 25% | 30% | — | 0.77 | 89% |
| A10 | ae_sae_signal | harmful | 20 | +0.040 | +0.020 | 10% | 15% | 35% | 15% | — | 0.76 | 92% |
| A11 | ae_sae_signal | harmful | 15 | +0.073 | +0.050 | 7% | 7% | 47% | 7% | — | 0.76 | 42% |
| A12 | ae_sae_signal | harmful | 20 | +0.013 | +0.010 | 10% | 15% | 30% | 15% | — | 0.76 | 48% |
| B01 | protocol_design | harmful | 14 | -0.010 | -0.010 | 21% | 36% | 21% | 36% | — | 0.76 | 89% |
| B02 | protocol_design | helpful | 9 | +0.064 | +0.020 | 11% | 0% | 22% | 22% | — | 0.75 | 67% |
| B03 | protocol_design | harmful | 10 | +0.046 | +0.000 | 10% | 20% | 30% | 20% | — | 0.76 | 86% |
| B04 | protocol_design | neutral | 10 | +0.018 | +0.000 | 20% | 30% | 20% | 50% | — | 0.74 | 37% |
| B05 | protocol_design | harmful | 18 | +0.040 | +0.015 | 6% | 6% | 28% | 6% | — | 0.75 | 34% |
| B06 | protocol_design | harmful | 6 | +0.058 | +0.010 | 17% | 0% | 33% | 0% | — | 0.78 | 62% |
| B07 | protocol_design | neutral | 11 | +0.046 | +0.020 | 9% | 9% | 45% | 45% | — | 0.76 | 50% |
| C01 | positive_signal | helpful | 20 | +0.015 | +0.000 | 10% | 15% | 35% | 35% | — | 0.75 | 15% |
| C02 | positive_signal | helpful | 10 | +0.065 | +0.035 | 10% | 0% | 30% | 30% | — | 0.75 | 47% |
| C03 | positive_signal | helpful | 20 | +0.001 | +0.015 | 10% | 25% | 20% | 20% | — | 0.75 | 25% |
| C04 | positive_signal | helpful | 12 | +0.029 | +0.000 | 8% | 25% | 17% | 17% | — | 0.74 | 49% |
| D01 | external_contextual | harmful | 20 | -0.010 | +0.000 | 10% | 25% | 20% | 25% | — | 0.76 | 86% |
| D02 | external_contextual | harmful | 20 | -0.028 | +0.000 | 5% | 25% | 10% | 25% | — | 0.75 | 68% |

## Per category

| type | n | mean dP | flip | → fail | → success | agree (expected) | S5 reasoning shift | S5 mentions signal |
|---|---|---|---|---|---|---|---|---|
| ae_sae_signal | 234 | +0.015 | 12% | 20% | 30% | 20% | 0.77 | 81% |
| external_contextual | 40 | -0.019 | 8% | 25% | 15% | 25% | 0.76 | 77% |
| positive_signal | 62 | +0.021 | 10% | 18% | 26% | 26% | 0.75 | 30% |
| protocol_design | 78 | +0.034 | 13% | 15% | 28% | 26% | 0.75 | 59% |

## Largest movers (mean dP)

Most toward FAILURE: D02 (-0.03), A05 (-0.02), A06 (-0.02), D01 (-0.01), B01 (-0.01)

Most toward SUCCESS: A11 (+0.07), C02 (+0.07), B02 (+0.06), B06 (+0.06), A07 (+0.05)

## Reading guide

- A perturbation the model *reasons about* should show (a) dP in the stated direction, (b) a high S5 signal-mention rate, and (c) a non-trivial S5 reasoning shift.
- dP ≈ 0 with high S5 signal-mention = the model saw the signal, discussed it, and did not change its answer (reasoning–answer disconnect, as in arm A).
- dP ≈ 0 with low S5 signal-mention = the model did not pick the signal up at all.
- 'agree (expert)' fills in once expert_label is set in the catalogue; until then it is —.
