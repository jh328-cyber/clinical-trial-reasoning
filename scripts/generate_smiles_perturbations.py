#!/usr/bin/env python3
"""Drug-track perturbations (Rayane): SMILES + toxicophore.

For each trial in data/trials.jsonl, resolve the drug to a canonical SMILES (PubChem),
then insert a well-known structural alert (toxicophore) to make the molecule plausibly
toxic WITHOUT changing the trial text — the counterfactual "Add Relevant Risk" at the
molecular level. A model that reasons about the drug should lower its success/safety
estimate; a model that just reads the trial text should not move. Emits PerturbedCase
rows in the shared schema (perturbed_case.schema.json), track="drug".

Toxicophore (v1): aromatic nitro — a classic structural alert (mutagenicity/hepatotox),
inserted on one aromatic C-H via RDKit. Molecules with no aromatic C-H fall back to an
aromatic-amine (aniline) alert on an aromatic ring; if neither applies the drug is skipped
(reported). Biologics/antibodies/vaccines don't resolve to a SMILES and self-filter out.

Resolution uses PubChem's current property name `SMILES` (the old `CanonicalSMILES` now
returns under a different key). Resumable via a cache.

Usage:
    python3 generate_smiles_perturbations.py                 # -> smiles_perturbed_cases.jsonl
    python3 generate_smiles_perturbations.py --n 20          # pilot
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import requests
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit import RDLogger

RDLogger.DisableLog("rdApp.*")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TRIALS = DATA / "trial_specs.jsonl"
OUT = DATA / "perturbed_cases_drug_v0.jsonl"
CACHE = DATA / "pubchem_smiles_cache.json"
PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{}/property/SMILES/JSON"

# Known structural alerts (toxicophores), each inserted on a compatible site via RDKit.
# One perturbed case is emitted per alert that transforms the molecule, so a drug can
# yield several cases (SMILES-01, -02, ...). Aromatic alerts need an aromatic C-H; the
# epoxide needs an aliphatic C=C.
TOXICOPHORES = [
    ("aromatic nitro",   AllChem.ReactionFromSmarts("[cH:1]>>[c:1][N+](=O)[O-]")),
    ("aromatic amine (aniline)", AllChem.ReactionFromSmarts("[cH:1]>>[c:1]N")),
    ("aromatic nitroso", AllChem.ReactionFromSmarts("[cH:1]>>[c:1]N=O")),
    ("aryl bromide",     AllChem.ReactionFromSmarts("[cH:1]>>[c:1]Br")),
    ("epoxide",          AllChem.ReactionFromSmarts("[C:1]=[C:2]>>[C:1]1O[C:2]1")),
]

# drug names that are clearly not single small molecules (skip the PubChem lookup)
NON_SMALL = re.compile(r"(?i)(placebo|plasma|vaccine|antibod|mab\b|cells?|therapy|"
                       r"immunoglob|interferon|insulin|albumin|/|\+)")


def resolve_smiles(name: str, cache: dict) -> str | None:
    if name in cache:
        return cache[name]
    val = None
    if not NON_SMALL.search(name):
        try:
            r = requests.get(PUG.format(requests.utils.quote(name)), timeout=25)
            if r.status_code == 200:
                props = r.json()["PropertyTable"]["Properties"][0]
                val = props.get("SMILES") or props.get("IsomericSMILES")
        except Exception:  # noqa: BLE001
            val = None
    cache[name] = val
    return val


def add_toxicophores(smiles: str):
    """Return a list of (perturbed_smiles, toxicophore_name) — one per alert that applies
    and yields a distinct, valid structure."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []
    base = Chem.MolToSmiles(mol)
    out, seen = [], set()
    for tox, rxn in TOXICOPHORES:
        try:
            prods = rxn.RunReactants((mol,))
        except Exception:  # noqa: BLE001
            prods = ()
        for (p,) in prods:
            try:
                Chem.SanitizeMol(p)
                s = Chem.MolToSmiles(p)
            except Exception:  # noqa: BLE001
                continue
            if s and s != base and s not in seen:
                seen.add(s)
                out.append((s, tox))
                break  # one site per alert type is enough
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0)
    args = ap.parse_args()
    trials = [json.loads(l) for l in TRIALS.read_text().splitlines() if l.strip()]
    if args.n:
        trials = trials[:args.n]
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    import copy
    cases, n_resolved, n_tox, n_biologic, n_nodrug = [], 0, 0, 0, 0
    for i, t in enumerate(trials, 1):
        nct = t["nct_id"]
        ivs = t.get("interventions") or []
        # pick the first DRUG-type intervention that PubChem resolves to a SMILES
        target_idx, smi, name = None, None, None
        for idx, iv in enumerate(ivs):
            if "DRUG" not in (iv.get("type") or "").upper():
                continue
            nm = (iv.get("name") or "").strip()
            s = resolve_smiles(nm, cache)
            # require a single-component small molecule: multi-component SMILES (salts /
            # co-crystals / combination products, with '.') aren't clean toxicophore test
            # cases — the edit would also perturb the co-components.
            if s and "." not in s:
                target_idx, smi, name = idx, s, nm
                break
        if target_idx is None:
            if any("DRUG" in (iv.get("type") or "").upper() for iv in ivs):
                n_biologic += 1       # had a DRUG-typed arm but no resolvable small molecule
            else:
                n_nodrug += 1         # no DRUG intervention at all (biologic/device/...)
            continue
        n_resolved += 1
        variants = add_toxicophores(smi)
        if not variants:
            continue
        n_tox += 1
        # baseline shows the CLEAN SMILES, perturbed shows the TOXIC SMILES, so the only
        # thing that differs between the two model inputs is the toxicophore (not "a SMILES
        # appeared"). Both are the real interventions array with a `smiles` field added.
        # fixed toxicophore -> id so a drug catalogue can map id -> type/direction
        # (nitro=01, aniline=02, nitroso=03, aryl bromide=04, epoxide=05).
        tox_id = {t[0]: i for i, t in enumerate(TOXICOPHORES, 1)}
        for pert, tox in variants:
            pid = f"SMILES-{tox_id[tox]:02d}"
            orig_iv = copy.deepcopy(ivs); orig_iv[target_idx]["smiles"] = smi
            pert_iv = copy.deepcopy(ivs); pert_iv[target_idx]["smiles"] = pert
            cases.append({
                "case_id": f"{nct}__{pid}", "nct_id": nct, "perturbation_id": pid,
                "track": "drug", "perturbation_type": "smiles_toxicophore",
                "target_field": "interventions", "edit_method": "replace",
                "original_value": orig_iv, "perturbed_value": pert_iv,
                "inserted_text": None, "expected_direction": "harmful", "expert_label": None,
                "filter_passed": True,
                "filter_note": f"DRUG '{name}' (intervention #{target_idx}) resolved to SMILES; "
                               f"{tox} alert added. Baseline carries the clean SMILES so the "
                               f"contrast isolates the toxicophore.",
                "smiles_original": smi, "smiles_perturbed": pert, "toxicophore": tox,
                "notes": None, "secondary_edits": [],
            })
        if i % 20 == 0:
            CACHE.write_text(json.dumps(cache)); print(f"  {i}/{len(trials)}", flush=True)
        time.sleep(0.2)

    CACHE.write_text(json.dumps(cache))
    OUT.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n")
    print(f"\n=== DRUG-TRACK SMILES PERTURBATIONS ===")
    print(f"trials                        : {len(trials)}")
    print(f"DRUG arm resolved to SMILES   : {n_resolved}  (small molecules)")
    print(f"DRUG arm but no small-mol SMILES: {n_biologic}  (biologic/fusion/combo)")
    print(f"no DRUG intervention          : {n_nodrug}")
    print(f"toxicophore added             : {n_tox}  -> perturbed cases written")
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
