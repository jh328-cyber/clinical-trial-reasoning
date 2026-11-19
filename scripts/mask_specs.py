#!/usr/bin/env python3
"""Mask drug identity in the clinical spec files, for the named-vs-masked test (Fig 2D).

Redacts, across every text field of each {row_id, spec}:
  - each intervention name + free-text drug-name mentions -> "the study drug"
  - leadSponsor                                           -> "the sponsor"
Then reports how many masked specs still leak an original drug name (should be 0).

Place at scripts/mask_specs.py in the repo; run from the repo root:
    python3 scripts/mask_specs.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRUG, SPON = "the study drug", "the sponsor"
trials = {json.loads(l)["nct_id"]: json.loads(l)
          for l in (ROOT / "data/trials.jsonl").read_text().splitlines() if l.strip()}


def names_for(spec):
    nm = set()
    for iv in spec.get("interventions") or []:
        n = (iv.get("name") or "").strip()
        if n:
            nm.add(n)
    t = trials.get(spec.get("nct_id"), {})
    if t.get("drug_name"):
        nm.add(t["drug_name"].strip())
    return sorted({n for n in nm if len(n) >= 3}, key=len, reverse=True)


def redact(o, pats):
    if isinstance(o, str):
        for p in pats:
            o = p.sub(DRUG, o)
        return o
    if isinstance(o, list):
        return [redact(x, pats) for x in o]
    if isinstance(o, dict):
        return {k: redact(v, pats) for k, v in o.items()}
    return o


def mask_spec(spec):
    names = names_for(spec)
    pats = [re.compile(re.escape(n), re.I) for n in names]
    s = redact(spec, pats)
    if s.get("leadSponsor"):
        s["leadSponsor"] = SPON
    for iv in s.get("interventions") or []:
        iv["name"] = DRUG
    return s, names


def run(inf, outf):
    rows = [json.loads(l) for l in (ROOT / inf).read_text().splitlines() if l.strip()]
    out, leaks = [], 0
    for r in rows:
        m, names = mask_spec(r["spec"])
        blob = json.dumps(m, ensure_ascii=False)
        if any(re.search(re.escape(n), blob, re.I) for n in names):
            leaks += 1
        out.append({"row_id": r["row_id"], "spec": m})
    (ROOT / outf).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    print(f"{outf}: {len(out)} specs, residual leak {leaks}/{len(out)}")


if __name__ == "__main__":
    run("data/baseline_specs_v0.jsonl", "data/masked_baseline_specs_v0.jsonl")
    run("data/perturbed_specs_v0.jsonl", "data/masked_perturbed_specs_v0.jsonl")
