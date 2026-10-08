#!/usr/bin/env python3
"""generate_perturbed_cases.py — apply the universal perturbation catalogue
(docs/perturbations/perturbations_v0.json) to every trial in data/trial_specs.jsonl,
validate every generated case against docs/perturbations/perturbed_case.schema.json,
and check that the Markdown catalogue (perturbations_v0.md) says the same thing as
the JSON catalogue.

If this script exits 0, the following are mechanically true:
  * every filter key in the JSON is implemented here (unknown keys raise);
  * every filter term matches as a whole word (or with an explicit trailing `*`
    prefix wildcard) — a term that only ever occurs as a longer word in the corpus
    is reported as a stem bug and fails the run;
  * every field_modification op is implemented here;
  * every generated case passes the schema, has no unfilled placeholder, is not a
    no-op (original == perturbed), and has a unique case_id;
  * perturbations_v0.md and perturbations_v0.json agree on id, order, name,
    expected_direction, perturbation text and enabled flag.

What this script does NOT check: whether the clinical wording is natural or the
expected direction is right. That is the expert's job (Yousef).

LABEL LEAKAGE WARNING
---------------------
A PerturbedCase carries perturbation_id, perturbation_type, expected_direction and
expert_label. Those are the answer. Never serialise a whole case into a model
prompt. Use --emit-model-input, which writes only the perturbed trial
specification (MODEL_VISIBLE_FIELDS) keyed by an opaque row_id (case_id itself
embeds the perturbation id, e.g. …__A01, so it is NOT in that file); the harness
joins metadata back through perturbed_specs_v0.map.jsonl after scoring.

Usage (from repo root):
    python3 scripts/generate_perturbed_cases.py --dry-run
    python3 scripts/generate_perturbed_cases.py                     # data/perturbed_cases_v0.jsonl
    python3 scripts/generate_perturbed_cases.py --emit-model-input  # + data/perturbed_specs_v0.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import jsonschema
except ImportError:  # pragma: no cover
    sys.exit("pip install jsonschema")

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "data" / "trial_specs.jsonl"
CATALOGUE = ROOT / "docs" / "perturbations" / "perturbations_v0.json"
CATALOGUE_MD = ROOT / "docs" / "perturbations" / "perturbations_v0.md"
SCHEMA = ROOT / "docs" / "perturbations" / "perturbed_case.schema.json"
OUT = ROOT / "data" / "perturbed_cases_v0.jsonl"
OUT_MODEL = ROOT / "data" / "perturbed_specs_v0.jsonl"
OUT_MAP = ROOT / "data" / "perturbed_specs_v0.map.jsonl"
OUT_BASE = ROOT / "data" / "baseline_specs_v0.jsonl"

# The only fields a model may ever see: the trial_specs.jsonl record, nothing else.
MODEL_VISIBLE_FIELDS = [
    "nct_id", "briefSummary", "detailedDescription", "eligibilityCriteria", "sex",
    "minimumAge", "maximumAge", "enrollmentCount", "armGroups", "interventions",
    "primaryOutcomes", "secondaryOutcomes", "allocation", "interventionModel",
    "masking", "phases", "conditions", "leadSponsor",
]

BASIC_KEYS = {
    "skip_if_endpoint_contains", "skip_if_enrollment_below", "skip_if_enrollment_above",
    "skip_if_masking_is", "skip_if_maximum_age_is", "skip_if_maximum_age_below_years",
    "skip_if_primary_endpoint_safety_only",
    "apply_only_if_phase", "apply_only_if_intervention_type", "apply_only_if_allocation",
    "apply_only_if_text_contains", "apply_only_if_search_fields", "skip_if_arm_type_contains",
}
ADVANCED_KEYS = {"skip_if_text_contains", "search_fields"}
FILTER_META = {"note"}

# A primary outcome is "safety/PK" if its measure matches this. A trial whose primary
# outcomes are ALL safety/PK has no inferential efficacy endpoint, so perturbations that
# talk about statistical power, conditional power or non-inferiority do not apply.
SAFETY_PK = re.compile(
    r"adverse event|\bAEs?\b|\bSAEs?\b|\bTEAEs?\b|safety|tolerab|toxicit|dose[- ]limiting|"
    r"\bDLTs?\b|maximum tolerated|\bMTD\b|pharmacokinetic|\bPK\b|\bCmax\b|\bAUC\b|"
    r"half-life|plasma concentration|immunogenicity|recommended phase 2 dose|\bRP2D\b|"
    r"maximal tolerated|maximum tolerable|excretion|laborator|vital sign|\bECG\b|electrocardiogra|"
    r"urinalys|C-SSRS|suicid|clinically significant (change|abnormal)|physical examination|bioavailab|"
    r"\bt1/2\b|\bTmax\b|concentration-time|dose[- ]proportional",
    re.I,
)

# ----------------------------------------------------------------------------- matching

def term_regex(term: str) -> re.Pattern:
    """Whole-word, case-insensitive. A trailing `*` makes it a prefix match
    (`anticoagul*` hits anticoagulant / anticoagulation). Boundaries are letters only,
    so `QTcF>480` still matches `QTcF`."""
    prefix = term.endswith("*")
    core = re.escape(term.rstrip("*").lower())
    tail = r"[a-z]*" if prefix else ""
    return re.compile(r"(?<![a-z])" + core + tail + r"(?![a-z])")


def has_term(hay: str, term: str) -> bool:
    return term_regex(term).search(hay) is not None


def blob(trial: dict, fields: list[str]) -> str:
    parts = []
    for f in fields:
        v = trial.get(f)
        parts.append(v if isinstance(v, str) else json.dumps(v))
    return " ".join(parts).lower()


def age_years(s: str | None) -> float | None:
    m = re.match(r"(\d+)\s*(Year|Month|Week|Day)", s or "")
    if not m:
        return None
    v, u = int(m.group(1)), m.group(2)
    return {"Year": v, "Month": v / 12, "Week": v / 52, "Day": v / 365}[u]


def safety_only_primary(t: dict) -> bool:
    ms = [o.get("measure", "") for o in (t.get("primaryOutcomes") or [])]
    return bool(ms) and all(SAFETY_PK.search(m) for m in ms)

# ----------------------------------------------------------------------------- filters

def passes_filter(p: dict, t: dict) -> tuple[bool, str]:
    """(passed, note). Unknown filter keys raise so the vocabulary stays closed."""
    f = p.get("filter", {})
    b, a = f.get("basic", {}), f.get("advanced", {})
    unknown = (set(b) - BASIC_KEYS) | (set(a) - ADVANCED_KEYS) | (set(f) - {"basic", "advanced"} - FILTER_META)
    if unknown:
        raise ValueError(f"{p['id']}: unknown filter keys {sorted(unknown)}")

    ec = t.get("enrollmentCount")
    if "skip_if_enrollment_below" in b and (ec is None or ec < b["skip_if_enrollment_below"]):
        return False, f"enrollment {ec} < {b['skip_if_enrollment_below']}"
    if "skip_if_enrollment_above" in b and ec is not None and ec > b["skip_if_enrollment_above"]:
        return False, f"enrollment {ec} > {b['skip_if_enrollment_above']}"
    if "skip_if_masking_is" in b and t.get("masking") in b["skip_if_masking_is"]:
        return False, f"masking is {t.get('masking')}"
    if "skip_if_maximum_age_is" in b and t.get("maximumAge") == b["skip_if_maximum_age_is"]:
        return False, "no upper age limit already"
    if "skip_if_maximum_age_below_years" in b:
        y = age_years(t.get("maximumAge"))
        if y is not None and y < b["skip_if_maximum_age_below_years"]:
            return False, f"maximumAge {t.get('maximumAge')} < {b['skip_if_maximum_age_below_years']}y"
    if b.get("skip_if_primary_endpoint_safety_only") and safety_only_primary(t):
        return False, "primary endpoint(s) are safety/PK only"
    if "apply_only_if_phase" in b and not set(t.get("phases") or []) & set(b["apply_only_if_phase"]):
        return False, f"phase {t.get('phases')} not in {b['apply_only_if_phase']}"
    if "apply_only_if_intervention_type" in b:
        types = {(i.get("type") or "").upper() for i in (t.get("interventions") or [])}
        if not types & set(b["apply_only_if_intervention_type"]):
            return False, f"intervention types {sorted(types)} not in {b['apply_only_if_intervention_type']}"
    if "apply_only_if_allocation" in b and t.get("allocation") != b["apply_only_if_allocation"]:
        return False, f"allocation {t.get('allocation')} != {b['apply_only_if_allocation']}"
    if "apply_only_if_text_contains" in b:
        hay = blob(t, b.get("apply_only_if_search_fields", ["briefSummary"]))
        if not any(has_term(hay, w) for w in b["apply_only_if_text_contains"]):
            return False, f"none of {b['apply_only_if_text_contains']} in {b.get('apply_only_if_search_fields')}"
    if "skip_if_arm_type_contains" in b:
        arm_types = {(g.get("type") or "") for g in (t.get("armGroups") or [])}
        hit = arm_types & set(b["skip_if_arm_type_contains"])
        if hit:
            return False, f"arm type {sorted(hit)} present"
    if "skip_if_endpoint_contains" in b:
        hay = blob(t, ["primaryOutcomes"])
        hit = [w for w in b["skip_if_endpoint_contains"] if has_term(hay, w)]
        if hit:
            return False, f"primary endpoint mentions {hit}"
    if "skip_if_text_contains" in a:
        hay = blob(t, a.get("search_fields", ["briefSummary"]))
        hit = [w for w in a["skip_if_text_contains"] if has_term(hay, w)]
        if hit:
            return False, f"{hit} found in {a.get('search_fields')}"
    return True, "all filter rules passed"


def lint_filter_terms(cat: list[dict], trials: list[dict]) -> list[str]:
    """A single-word term without `*` that never matches as a whole word, while some
    corpus word begins with it, is almost certainly a truncated stem (`anticoagul`).
    Hard error."""
    corpus = " ".join(blob(t, MODEL_VISIBLE_FIELDS[1:]) for t in trials)
    words = set(re.findall(r"[a-z][a-z\-]+", corpus))
    problems = []
    for p in cat:
        for lvl in ("basic", "advanced"):
            for k, v in p["filter"].get(lvl, {}).items():
                if not (isinstance(v, list) and "contains" in k) or k == "skip_if_arm_type_contains":
                    continue
                for term in v:
                    core = term.rstrip("*").lower()
                    if term.endswith("*") or " " in core or "-" in core or has_term(corpus, term):
                        continue
                    if term.isupper():
                        continue  # acronym (ALT, TEN, SJS), not a truncated stem
                    longer = sorted({w for w in words if w.startswith(core) and w != core})[:4]
                    if longer:
                        problems.append(f"{p['id']} term '{term}' never matches whole-word but corpus has {longer} — stem? add `*`")
    return problems

# ----------------------------------------------------------------------------- building

def fill(text: str, t: dict) -> str:
    n = t.get("enrollmentCount") or 0
    return (text.replace("{N}", str(n))
                .replace("{ceil(N/2)}", str(math.ceil(n / 2)))
                .replace("{N×2}", str(n * 2)))


def apply_modification(mod: dict, t: dict):
    field, op = mod["field"], mod["op"]
    orig = t.get(field)
    if op == "ceil_half":
        return orig, math.ceil(orig / 2)
    if op == "double":
        return orig, orig * 2
    if op == "set":
        return orig, mod["value"]
    if op == "append_item":
        return orig, list(orig or []) + [mod["value"]]
    raise ValueError(f"unknown field_modification op {op}")


def build_case(p: dict, t: dict, note: str) -> dict:
    text = fill(p["perturbation_text"], t)
    summary = t.get("briefSummary") or ""
    appended = (summary + " " + text).strip()
    base = {
        "case_id": f"{t['nct_id']}__{p['id']}",
        "nct_id": t["nct_id"],
        "perturbation_id": p["id"],
        "track": "clinical",
        "perturbation_type": p["type"],
        "expected_direction": p["expected_direction"],
        "expert_label": p.get("yousef_label"),
        "filter_passed": True,
        "filter_note": note,
        "smiles_original": None, "smiles_perturbed": None, "toxicophore": None,
        "notes": None,
    }
    if p["insertion_method"] == "append":
        return {**base, "target_field": "briefSummary", "edit_method": "append",
                "original_value": summary, "perturbed_value": appended,
                "inserted_text": text, "secondary_edits": []}
    if p["insertion_method"] == "modify_and_append":
        mods = p["field_modification"]
        mods = mods if isinstance(mods, list) else [mods]
        orig, new = apply_modification(mods[0], t)
        secondary = []
        for m in mods[1:]:
            o2, n2 = apply_modification(m, t)
            secondary.append({"target_field": m["field"], "original_value": o2, "perturbed_value": n2})
        secondary.append({"target_field": "briefSummary", "original_value": summary, "perturbed_value": appended})
        return {**base, "target_field": mods[0]["field"], "edit_method": "replace",
                "original_value": orig, "perturbed_value": new, "inserted_text": None,
                "secondary_edits": secondary}
    raise ValueError(f"{p['id']}: unknown insertion_method {p['insertion_method']}")


def row_id(case_id: str) -> str:
    """Opaque id for model-input rows. case_id embeds the perturbation id (…__A01), which
    is the answer, so the model-facing file carries only a hash; the .map file joins back."""
    return hashlib.sha1(case_id.encode()).hexdigest()[:12]


def model_input(case: dict, t: dict) -> dict:
    """The perturbed spec with ONLY model-visible fields, keyed by an opaque row_id.
    Nothing in this record identifies the perturbation."""
    spec = {k: t.get(k) for k in MODEL_VISIBLE_FIELDS}
    spec[case["target_field"]] = case["perturbed_value"]
    for e in case["secondary_edits"]:
        spec[e["target_field"]] = e["perturbed_value"]
    return {"row_id": row_id(case["case_id"]), "spec": spec}

# ----------------------------------------------------------------------------- md check

def check_md(cat: list[dict], md: str) -> list[str]:
    errs = []
    ids = re.findall(r"^\| \d+ \| ([A-D]\d\d) \|", md, re.M)
    if [p["id"] for p in cat] != ids:
        errs.append(f"id/order mismatch: json {[p['id'] for p in cat]} vs md {ids}")
    for p in cat:
        m = re.search(r"^\| \d+ \| " + p["id"] + r" \| (.*?) \| (.*?) \| (harmful|helpful|neutral) \| (.*?) \|$", md, re.M)
        if not m:
            errs.append(f"{p['id']}: row not parseable in md"); continue
        name, text, direction, filt = m.groups()
        if name != p["name"]:
            errs.append(f"{p['id']}: name md='{name}' json='{p['name']}'")
        if direction != p["expected_direction"]:
            errs.append(f"{p['id']}: direction md={direction} json={p['expected_direction']}")
        if p["perturbation_text"] not in text:
            errs.append(f"{p['id']}: perturbation_text not found verbatim in md row")
        if not p.get("enabled", True) and "disabled" not in (text + filt).lower():
            errs.append(f"{p['id']}: disabled in json but md row does not say so")
    return errs

# ----------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--emit-model-input", action="store_true")
    ap.add_argument("--specs", type=Path, default=SPECS)
    ap.add_argument("--catalogue", type=Path, default=CATALOGUE)
    ap.add_argument("--catalogue-md", type=Path, default=CATALOGUE_MD)
    ap.add_argument("--schema", type=Path, default=SCHEMA)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--out-model", type=Path, default=OUT_MODEL)
    args = ap.parse_args()

    trials = [json.loads(l) for l in args.specs.read_text().splitlines() if l.strip()]
    cat = json.loads(args.catalogue.read_text())
    schema = json.loads(args.schema.read_text())
    jsonschema.Draft7Validator.check_schema(schema)
    V = jsonschema.Draft7Validator(schema)

    fatal = []
    if args.catalogue_md.exists():
        fatal += check_md(cat, args.catalogue_md.read_text())
    fatal += lint_filter_terms(cat, trials)
    if fatal:
        print("CATALOGUE ERRORS:")
        for e in fatal:
            print("  -", e)
        return 1

    cases, skipped, errors, seen = [], Counter(), [], set()
    skip_reasons = defaultdict(Counter)
    for p in cat:
        if not p.get("enabled", True):
            continue
        for t in trials:
            ok, note = passes_filter(p, t)
            if not ok:
                skipped[p["id"]] += 1
                skip_reasons[p["id"]][note[:50]] += 1
                continue
            c = build_case(p, t, note)
            errs = [e.message for e in V.iter_errors(c)]
            s = json.dumps(c)
            if any(ph in s for ph in ("{N", "{ceil", "{original")):
                errs.append("unfilled placeholder")
            if c["original_value"] == c["perturbed_value"]:
                errs.append("no-op: original == perturbed")
            if c["case_id"] in seen:
                errs.append("duplicate case_id")
            if c["case_id"] != f"{c['nct_id']}__{c['perturbation_id']}":
                errs.append("case_id does not match nct_id/perturbation_id")
            sec_fields = [e["target_field"] for e in c["secondary_edits"]]
            if len(sec_fields) != len(set(sec_fields)) or c["target_field"] in sec_fields:
                errs.append("a field is edited more than once")
            seen.add(c["case_id"])
            if errs:
                errors.append((c["case_id"], errs))
            cases.append(c)

    applied = Counter(c["perturbation_id"] for c in cases)
    print(f"trials: {len(trials)}  enabled perturbations: {sum(1 for p in cat if p.get('enabled', True))}")
    print(f"cases generated: {len(cases)}   errors: {len(errors)}")
    print("\nper perturbation  applied / skipped   (top skip reason)")
    for p in cat:
        flag = "   (disabled)" if not p.get("enabled", True) else ""
        top = skip_reasons[p["id"]].most_common(1)
        print(f"  {p['id']}  {applied[p['id']]:3d} / {skipped[p['id']]:3d}{flag}   {top[0][0] if top else ''}")
    if errors:
        print("\nERRORS:")
        for cid, e in errors[:20]:
            print(" ", cid, e)
        return 1
    if not args.dry_run:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as fh:
            for c in cases:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"\nwrote {args.out}")
        if args.emit_model_input:
            tmap = {t["nct_id"]: t for t in trials}
            with args.out_model.open("w") as fh, OUT_MAP.open("w") as mp, OUT_BASE.open("w") as bf:
                for c in cases:
                    fh.write(json.dumps(model_input(c, tmap[c["nct_id"]]), ensure_ascii=False) + "\n")
                    mp.write(json.dumps({"row_id": row_id(c["case_id"]), "case_id": c["case_id"]}) + "\n")
                # Unperturbed baseline, same shape and same opaque-id scheme, so the
                # same env config runs both and the shift analysis joins by nct_id.
                for t in trials:
                    cid = f"{t['nct_id']}__BASELINE"
                    bf.write(json.dumps({"row_id": row_id(cid), "spec": {k: t.get(k) for k in MODEL_VISIBLE_FIELDS}}, ensure_ascii=False) + "\n")
                    mp.write(json.dumps({"row_id": row_id(cid), "case_id": cid}) + "\n")
            print(f"wrote {args.out_model}  (row_id + spec only; no case_id, no perturbation metadata)")
            print(f"wrote {OUT_BASE}  (unperturbed baseline, same shape)")
            print(f"wrote {OUT_MAP}  (row_id -> case_id for both files; keep OUT of any prompt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
