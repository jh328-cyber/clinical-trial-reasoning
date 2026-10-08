#!/usr/bin/env python3
"""build_spec_inventory.py — inventory of what data/trial_specs.jsonl actually holds.

Counts coverage and size for every protocol field fetched, and splits them into
fields present in nearly every trial and fields that are not. The split is the
point: a perturbation that has to be insertable for ANY trial can only live in a
field the whole corpus has.

Inventory only. This describes what is there; it proposes no clinical content.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPECS = PROJECT_ROOT / "data" / "trial_specs.jsonl"
DEFAULT_OUT = PROJECT_ROOT / "docs" / "spec_field_inventory.md"

UNIVERSAL_THRESHOLD = 95  # of 100
EXAMPLE_COUNT = 2
EXAMPLE_MAX_CHARS = 180

# (key, kind, human description). kind drives how size is measured:
#   text   - a free-text blob; size is words
#   scalar - a short categorical or number; size is words (usually 1)
#   list   - a list of objects/strings; size is item count, plus words of its text
FIELDS = [
    ("briefSummary", "text", "Lay/technical summary of the study"),
    ("detailedDescription", "text", "Extended protocol narrative"),
    ("eligibilityCriteria", "text", "Inclusion/exclusion criteria block"),
    ("sex", "scalar", "Eligible sex"),
    ("minimumAge", "scalar", "Minimum eligible age"),
    ("maximumAge", "scalar", "Maximum eligible age"),
    ("enrollmentCount", "scalar", "Enrolment count"),
    ("armGroups", "list", "Arm labels, types and descriptions"),
    ("interventions", "list", "Intervention names, types and descriptions"),
    ("primaryOutcomes", "list", "Primary outcome measures + time frames"),
    ("secondaryOutcomes", "list", "Secondary outcome measures + time frames"),
    ("allocation", "scalar", "designInfo.allocation"),
    ("interventionModel", "scalar", "designInfo.interventionModel"),
    ("masking", "scalar", "designInfo.maskingInfo.masking"),
    ("phases", "list", "Registered phase(s)"),
    ("conditions", "list", "Conditions studied"),
    ("leadSponsor", "scalar", "Lead sponsor name"),
]


def flatten_text(value) -> str:
    """All human-readable text in a value, concatenated."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return " ".join(flatten_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(flatten_text(v) for v in value.values())
    return ""


def is_present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True  # a number, including 0


def short_example(value, kind: str) -> str:
    """A compact, readable rendering of one real value."""
    if kind == "list":
        if not value:
            return ""
        first = value[0]
        if isinstance(first, dict):
            for key in ("label", "name", "measure"):
                if first.get(key):
                    rendered = str(first[key])
                    break
            else:
                rendered = json.dumps(first)
        else:
            rendered = str(first)
        suffix = f" (+{len(value) - 1} more)" if len(value) > 1 else ""
        rendered = " ".join(rendered.split())
        if len(rendered) > EXAMPLE_MAX_CHARS:
            rendered = rendered[:EXAMPLE_MAX_CHARS].rstrip() + "…"
        return rendered + suffix
    rendered = " ".join(str(value).split())
    if len(rendered) > EXAMPLE_MAX_CHARS:
        rendered = rendered[:EXAMPLE_MAX_CHARS].rstrip() + "…"
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs", type=Path, default=DEFAULT_SPECS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    specs = [json.loads(l) for l in args.specs.read_text().splitlines() if l.strip()]
    total = len(specs)

    stats = []
    for key, kind, desc in FIELDS:
        values = [s.get(key) for s in specs]
        present = [v for v in values if is_present(v)]
        word_counts = [len(flatten_text(v).split()) for v in present]
        item_counts = [len(v) for v in present if isinstance(v, list)]
        # Examples: prefer genuinely short real values so the table stays readable.
        ordered = sorted(present, key=lambda v: len(flatten_text(v)))
        examples: list[str] = []
        for candidate in ordered:
            rendered = short_example(candidate, kind)
            if rendered and rendered not in examples:
                examples.append(rendered)
            if len(examples) == EXAMPLE_COUNT:
                break
        stats.append(
            {
                "key": key,
                "kind": kind,
                "desc": desc,
                "n": len(present),
                "median_words": st.median(word_counts) if word_counts else 0,
                "median_items": st.median(item_counts) if item_counts else None,
                "examples": examples,
            }
        )

    universal = [s for s in stats if s["n"] >= UNIVERSAL_THRESHOLD]
    specific = [s for s in stats if s["n"] < UNIVERSAL_THRESHOLD]

    # --- stdout ---
    print(f"FIELD INVENTORY over {total} trials ({args.specs})")
    print(f"  {'field':<22}{'n':>5}{'cov':>7}{'med words':>11}{'med items':>11}")
    for s in stats:
        items = "-" if s["median_items"] is None else f"{s['median_items']:.1f}"
        print(f"  {s['key']:<22}{s['n']:>5}{s['n']/total:>7.0%}"
              f"{s['median_words']:>11.1f}{items:>11}")
    print(f"\n  universal (>= {UNIVERSAL_THRESHOLD}/{total}): "
          f"{', '.join(s['key'] for s in universal)}")
    print(f"  trial-specific        : {', '.join(s['key'] for s in specific) or '(none)'}")

    # --- markdown ---
    out: list[str] = ["# Trial spec field inventory\n"]
    out.append(
        f"Source: `{args.specs.relative_to(PROJECT_ROOT)}` — {total} trials, the same "
        "NCT IDs and the same order as `data/trials.jsonl`.\n"
    )
    out.append(
        "Counts are of trials where the field is **non-empty** (a non-blank string, a "
        "non-empty list, or any number). \"Median words\" counts whitespace-separated "
        "tokens across all text in the field; for list fields \"median items\" is the "
        "list length. Examples are real values, shortest-first so the table stays "
        f"readable, truncated at {EXAMPLE_MAX_CHARS} characters.\n"
    )
    out.append(
        "This document is an inventory. It records what the corpus contains and "
        "proposes no clinical content.\n"
    )

    out.append("## All fields\n")
    out.append("| Field | Kind | Non-empty | Coverage | Median words | Median items |")
    out.append("|---|---|---|---|---|---|")
    for s in stats:
        items = "—" if s["median_items"] is None else f"{s['median_items']:.1f}"
        out.append(
            f"| `{s['key']}` | {s['kind']} | {s['n']}/{total} | {s['n']/total:.0%} "
            f"| {s['median_words']:.1f} | {items} |"
        )
    out.append("")

    def section(title: str, group: list[dict], blurb: str) -> None:
        out.append(f"## {title}\n")
        out.append(blurb + "\n")
        if not group:
            out.append("_None._\n")
            return
        for s in group:
            items = (
                "" if s["median_items"] is None else f", median {s['median_items']:.1f} items"
            )
            out.append(f"### `{s['key']}`\n")
            out.append(
                f"{s['desc']}. Non-empty in **{s['n']}/{total}** trials "
                f"({s['n']/total:.0%}); median {s['median_words']:.1f} words{items}.\n"
            )
            for example in s["examples"]:
                out.append(f"- `{example}`")
            if not s["examples"]:
                out.append("- _(no non-empty value)_")
            out.append("")

    section(
        f"Universal fields (present in ≥{UNIVERSAL_THRESHOLD} of {total})",
        universal,
        "Every trial in the corpus carries these, so a perturbation that must be "
        "insertable for an arbitrary trial can be placed in any of them.",
    )
    section(
        f"Trial-specific fields (present in <{UNIVERSAL_THRESHOLD} of {total})",
        specific,
        "These are missing for some trials, so anything keyed to them applies only to "
        "the subset that has them. The count next to each field is that subset's size.",
    )

    out.append("## Excluded by the leakage policy\n")
    out.append(
        "`overallStatus`, `whyStopped`, `startDate`, `completionDate`, `resultsSection` "
        "and the top-level `hasResults` flag are absent from the corpus by construction. "
        "`scripts/fetch_trial_specs.py` requests only the protocol modules it needs via "
        "the API's `fields` parameter, so these are never fetched, never cached and "
        "never written. `enrollmentInfo.type` (ACTUAL vs ESTIMATED) is also omitted, as "
        "it hints at whether enrolment completed.\n"
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(out) + "\n")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
