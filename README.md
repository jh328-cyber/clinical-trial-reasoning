# Clinical Trial Reasoning Environment

Understanding how LLMs reason about clinical trial outcomes through structured,
step-by-step evaluation.

## Goals

- **Decompose the prediction.** Replace free-form chain-of-thought with an explicit
  sequence of questions, the last of which is *"What is the outcome of this trial?"*
  Every intermediate step is a separately scored, separately inspectable answer.
- **Make reasoning measurable.** Score each step independently so we can see *where*
  a model's reasoning succeeds or breaks down, not just whether the final label is right.
- **Study what the model actually knows.** Separate recall (what the model already knows
  about a trial, a drug, a sponsor) from inference (what it concludes from that knowledge).
- **Build a reusable evaluation environment.** Package the task as a
  [verifiers](https://github.com/PrimeIntellect-ai/verifiers) environment so it can be
  used for evaluation today and reinforcement learning later.

## Status

Early design. See [`docs/proposal.md`](docs/proposal.md) for the proposed reasoning
process and implementation plan.

## Collaborators

- Junyi Huang — Abugoot Lab, Harvard Medical School
- Hao Zhu
- Sean Pohorence

## Acknowledgements

Built on top of [PrimeIntellect's `verifiers` library](https://github.com/PrimeIntellect-ai/verifiers).
Data and retrieval components are carried over from a prior LLM-based trial-outcome
labeling pipeline (TrialBench labels, ClinicalTrials.gov / FDA / PubMed / sponsor-press
retrieval, frozen evidence bundles).
