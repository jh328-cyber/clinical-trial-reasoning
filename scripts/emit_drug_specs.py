#!/usr/bin/env python3
"""emit_drug_specs.py — turn the drug-track PerturbedCases into spec-mode input files,
in the SAME {row_id, spec} format as generate_perturbed_cases.py --emit-model-input, so the
drug cases run through the verifiers env unchanged (same eval).

The verifiers renderer (taskset.py:177) prints each intervention as
    - [{type}] {name}: {description}
so the model only sees type / name / description. We therefore put the SMILES INSIDE the
intervention's `description` (baseline = clean SMILES, perturbed = toxic SMILES) so it is
actually rendered into the prompt. We also keep a separate `smiles` key for traceability
(ignored by the renderer).

Writes (relative to repo root):
  data/baseline_specs_drug_v0.jsonl    one row per trial; chosen drug's description carries the CLEAN SMILES
  data/perturbed_specs_drug_v0.jsonl   one row per case; chosen drug's description carries the TOXIC SMILES
  data/perturbed_specs_drug_v0.map.jsonl   row_id -> case_id

The only difference the model sees between baseline and perturbed is the toxicophore in the
SMILES string — not "a SMILES appeared" — because the baseline already shows the clean SMILES.
Leak-safe: no case_id / perturbation metadata in the spec files.

Usage (from repo root):  python3 scripts/emit_drug_specs.py
"""
import json
from pathlib import Path

from generate_perturbed_cases import MODEL_VISIBLE_FIELDS, row_id  # reuse exact conventions

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "perturbed_cases_drug_v0.jsonl"
SPECS = ROOT / "data" / "trial_specs.jsonl"
SMILES_TAG = " SMILES: "


def _strip_existing_smiles(desc: str) -> str:
    # keep descriptions idempotent if re-run
    i = desc.find(SMILES_TAG)
    return desc[:i].rstrip() if i != -1 else desc


def with_smiles_in_desc(interventions, target_idx, smiles):
    """Return a deep-ish copy of the interventions array with the SMILES appended to the
    chosen drug's description (so the renderer shows it), and also stored in a `smiles` key."""
    out = []
    for i, iv in enumerate(interventions):
        iv = dict(iv)
        if i == target_idx:
            base_desc = _strip_existing_smiles(iv.get("description") or "")
            iv["description"] = (base_desc + ("  " if base_desc else "") + f"SMILES: {smiles}").strip()
            iv["smiles"] = smiles  # traceability; not rendered
        out.append(iv)
    return out


def target_index(interventions):
    """The intervention the case edited = the one whose original_value carried a `smiles`
    key (set by generate_smiles_perturbations.py). Fall back to first DRUG arm."""
    for i, iv in enumerate(interventions):
        if iv.get("smiles"):
            return i
    for i, iv in enumerate(interventions):
        if "DRUG" in (iv.get("type") or "").upper():
            return i
    return 0


def spec_from(trial, interventions):
    s = {k: trial.get(k) for k in MODEL_VISIBLE_FIELDS}
    s["interventions"] = interventions
    return s


def main():
    trials = {json.loads(l)["nct_id"]: json.loads(l)
              for l in SPECS.read_text().splitlines() if l.strip()}
    cases = [json.loads(l) for l in CASES.read_text().splitlines() if l.strip()]

    # baseline: one row per trial, clean SMILES in the chosen drug's description
    base_by_nct = {}
    for c in cases:
        if c["nct_id"] in base_by_nct:
            continue
        iv = c["original_value"]
        idx = target_index(iv)
        base_by_nct[c["nct_id"]] = with_smiles_in_desc(iv, idx, c["smiles_original"])
    base_rows = [{"row_id": row_id(f"{nct}__drug_baseline"), "spec": spec_from(trials[nct], iv)}
                 for nct, iv in base_by_nct.items()]

    # perturbed: one row per case, toxic SMILES in the chosen drug's description
    pert_rows, map_rows = [], []
    for c in cases:
        iv = c["perturbed_value"]
        idx = target_index(iv)
        spec_iv = with_smiles_in_desc(iv, idx, c["smiles_perturbed"])
        rid = row_id(c["case_id"])
        pert_rows.append({"row_id": rid, "spec": spec_from(trials[c["nct_id"]], spec_iv)})
        map_rows.append({"row_id": rid, "case_id": c["case_id"]})

    def dump(name, rows):
        (ROOT / "data" / name).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    dump("baseline_specs_drug_v0.jsonl", base_rows)
    dump("perturbed_specs_drug_v0.jsonl", pert_rows)
    dump("perturbed_specs_drug_v0.map.jsonl", map_rows)
    print(f"baseline trials: {len(base_rows)}  perturbed cases: {len(pert_rows)}")
    print("SMILES rendered inside intervention description (taskset.py:177).")


if __name__ == "__main__":
    main()
