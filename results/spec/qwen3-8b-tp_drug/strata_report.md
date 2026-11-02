# Strata report — qwen3-8b-tp_drug / drug

Trials with a readable baseline: 39 (3 of them taken from the second baseline run). Noise pairs: 36. Perturbed cases joined: 135. Skipped: {'S6 unreadable': 25, 'no baseline': 6}.

dP = P(SUCCESS | perturbed) − P(SUCCESS | baseline). ↓ = dP < −0.05, ↑ = dP > +0.05. 'per-trial p' = Wilcoxon signed-rank test on one mean dP per trial (H0: median 0). The noise row is the second baseline run minus the first (same specs, nothing added).

## 丢失的 case（读不出最终答案，按组）

| group | cases | lost | lost % | reasons |
|---|---|---|---|---|
| SMILES 毒性基团 (Rayane) | 166 | 31 | 19% | S6 格式读不出（如 terminate/complete、只抄标签） 25; 基线读不出 6 |

## 全部 trial

| group | cases | trials | mean dP | median dP | ↓ fail | ↑ succ | per-trial p |
|---|---|---|---|---|---|---|---|
| 噪声（同题跑两遍） | 36 | 36 | +0.007 | +0.000 | 19% | 22% | nan |
| SMILES 毒性基团 (Rayane) | 135 | 37 | -0.020 | +0.000 | 31% | 15% | nan |

## TP 训练集里见过的 trial（15 个）

| group | cases | trials | mean dP | median dP | ↓ fail | ↑ succ | per-trial p |
|---|---|---|---|---|---|---|---|
| 噪声（同题跑两遍） | 15 | 15 | +0.067 | +0.000 | 20% | 33% | nan |
| SMILES 毒性基团 (Rayane) | 50 | 15 | -0.001 | +0.000 | 26% | 12% | nan |

## TP 训练集里没见过的 trial（24 个）

| group | cases | trials | mean dP | median dP | ↓ fail | ↑ succ | per-trial p |
|---|---|---|---|---|---|---|---|
| 噪声（同题跑两遍） | 21 | 21 | -0.036 | +0.000 | 19% | 14% | nan |
| SMILES 毒性基团 (Rayane) | 85 | 22 | -0.031 | +0.000 | 34% | 16% | nan |

## 基线预测准确率（P(SUCCESS) > 0.5 记为 SUCCESS）

- 全部：27/39
- TP 见过的：13/15
- TP 没见过的：14/24

