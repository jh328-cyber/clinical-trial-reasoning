# Drug track — SMILES / toxicophore perturbations

Same schema and same spec-mode eval as the clinical track; only the perturbation differs:
we take the trial's small-molecule drug, resolve its SMILES (PubChem), insert a known
structural-alert toxicophore (RDKit), and keep the trial text unchanged. The SMILES is
written into the intervention's `description` so the verifiers renderer (taskset.py) shows
it to the model. Baseline carries the clean SMILES, perturbed the toxic one, so the only
change the model sees is the toxicophore.

## Files
- `scripts/generate_smiles_perturbations.py` -> `data/perturbed_cases_drug_v0.jsonl` (166 cases, 42 drugs).
- `scripts/emit_drug_specs.py` -> spec-mode inputs (same {row_id, spec} as `--emit-model-input`):
  `data/baseline_specs_drug_v0.jsonl` (clean SMILES in description),
  `data/perturbed_specs_drug_v0.jsonl` (toxic SMILES), `.map` (row_id -> case_id).
- `docs/perturbations/perturbations_drug_v0.json` — catalogue (SMILES-01..05 toxicophore types, all `harmful`).
- `docs/tox_validation.md` — structural-alert tox validation (100% of toxified molecules carry a recognized genotoxic alert).

## Run (same eval as clinical)
```
python3 scripts/generate_smiles_perturbations.py
python3 scripts/emit_drug_specs.py
scripts/run_spec_mode.sh deepseek-chat data/baseline_specs_drug_v0.jsonl  drug_baseline
scripts/run_spec_mode.sh deepseek-chat data/perturbed_specs_drug_v0.jsonl drug_perturbed
python3 scripts/analyze_perturbation_shift.py \
    --baseline results/spec/deepseek-chat/drug_baseline/traces.jsonl \
    --perturbed results/spec/deepseek-chat/drug_perturbed/traces.jsonl \
    --map data/perturbed_specs_drug_v0.map.jsonl \
    --catalogue docs/perturbations/perturbations_drug_v0.json
```
Requires `rdkit` + `requests` for generation (not for the eval).
