# Strata report — qwen3-8b_drug / drug

Trials with a readable baseline: 42 (0 of them taken from the second baseline run). Noise pairs: 42. Perturbed cases joined: 166. Skipped: none.

dP = P(SUCCESS | perturbed) − P(SUCCESS | baseline). ↓ = dP < −0.05, ↑ = dP > +0.05. 'per-trial p' = Wilcoxon signed-rank test on one mean dP per trial (H0: median 0). The noise row is the second baseline run minus the first (same specs, nothing added).

## 丢失的 case（读不出最终答案，按组）

| group | cases | lost | lost % | reasons |
|---|---|---|---|---|
| SMILES 毒性基团 (Rayane) | 166 | 0 | 0% | — |

## 全部 trial

| group | cases | trials | mean dP | median dP | ↓ fail | ↑ succ | per-trial p |
|---|---|---|---|---|---|---|---|
| 噪声（同题跑两遍） | 42 | 42 | +0.007 | +0.000 | 26% | 36% | nan |
| SMILES 毒性基团 (Rayane) | 166 | 42 | +0.013 | +0.000 | 37% | 34% | nan |

## TP 训练集里见过的 trial（18 个）

| group | cases | trials | mean dP | median dP | ↓ fail | ↑ succ | per-trial p |
|---|---|---|---|---|---|---|---|
| 噪声（同题跑两遍） | 18 | 18 | +0.075 | +0.050 | 17% | 50% | nan |
| SMILES 毒性基团 (Rayane) | 66 | 18 | +0.066 | +0.025 | 23% | 42% | nan |

## TP 训练集里没见过的 trial（24 个）

| group | cases | trials | mean dP | median dP | ↓ fail | ↑ succ | per-trial p |
|---|---|---|---|---|---|---|---|
| 噪声（同题跑两遍） | 24 | 24 | -0.044 | +0.000 | 33% | 25% | nan |
| SMILES 毒性基团 (Rayane) | 100 | 24 | -0.023 | +0.000 | 46% | 29% | nan |

## 基线预测准确率（P(SUCCESS) > 0.5 记为 SUCCESS）

- 全部：21/42
- TP 见过的：9/18
- TP 没见过的：12/24

