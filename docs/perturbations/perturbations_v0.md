# Universal Perturbation List v0

**Purpose**: ~25 universal perturbations for expert review (Yousef Badran).
Each perturbation is broadly applicable across the 100-trial dataset, subject to the per-item filter rules (some items apply only to certain phases or intervention types).
Yousef labels each as **helpful / neutral / harmful** for trial success likelihood.

**How to read this list**: Each perturbation is a piece of text to INSERT into
(or a modification to apply to) a trial's specification. "Expected direction"
is our initial guess — Yousef's label overrides it.

---

## Category A: AE / SAE Early Signs (12 items)

These add subtle clinical safety signals — early lab findings, imaging, or
small-cohort incidence data. The model must connect the dots to assess impact.
Per Hao: use early signs, not blunt statements like "this drug is toxic."

All Category A signals are framed as observations from a *preceding* safety cohort or dedicated study, so the stated denominators never conflict with the current trial's enrollment. Filters search `briefSummary` and `primaryOutcomes` (A04 also `interventions`): lab thresholds in eligibility criteria (e.g. "ALT ≤ 2.5× ULN") are boilerplate and do not disqualify a trial.

| # | ID | Name | Perturbation text (insert into briefSummary) | Expected | Filter rule |
|---|-----|------|----------------------------------------------|----------|-------------|
| 1 | A01 | Hepatotoxicity signal | "In a preceding open-label safety run-in, 3 of the first 15 dosed subjects showed ALT elevations >3× ULN within 4 weeks of treatment initiation." | harmful | Skip if trial already mentions ALT, hepatotoxicity, liver injury, DILI or hepatic impairment in briefSummary / primary endpoint |
| 2 | A02 | QT prolongation signal | "Thorough QT study data indicate a mean QTcF increase of 15 ms at therapeutic dose, with individual values exceeding 480 ms in 2 of 40 subjects." | harmful | Skip if trial mentions QT, cardiac arrhythmia, or antiarrhythmic |
| 3 | A03 | Nephrotoxicity signal | "Post-hoc analysis of the preceding dose-escalation cohort revealed a mean serum creatinine increase of 0.4 mg/dL and two cases of acute kidney injury (CTCAE Grade 2) during the treatment period." | harmful | Skip if trial mentions creatinine, renal, kidney, or nephrotoxicity |
| 4 | A04 | Hypersensitivity / administration reaction signal | "In the preceding safety cohort, 4 of the first 20 dosed subjects experienced Grade 2–3 hypersensitivity reactions (hypotension, dyspnea, urticaria) temporally associated with drug administration, requiring treatment interruption." | harmful | Skip if trial mentions infusion reaction, anaphylaxis, hypersensitivity, or premedication |
| 5 | A05 | Bone marrow suppression signal | "In the preceding dose-escalation cohorts, Grade 3 neutropenia (ANC <1000/mm³) was observed in 3 of 12 subjects at the recommended Phase 2 dose, with a median nadir at Day 14." | harmful | Skip if trial mentions neutropenia, myelosuppression, bone marrow, ANC, or G-CSF |
| 6 | A06 | Interstitial lung disease signal | "In the preceding dose-expansion cohort, routine CT imaging at Week 12 identified new bilateral ground-glass opacities consistent with drug-induced pneumonitis in 2 of 30 treated subjects; both cases resolved after drug discontinuation." | harmful | Skip if trial mentions ILD, pneumonitis, pulmonary fibrosis, or ground-glass opacities |
| 7 | A07 | Severe GI toxicity signal | "In the preceding safety cohort, 5 of 25 subjects (20%) experienced Grade 3 diarrhea within the first 2 weeks of dosing, with 2 requiring IV fluid resuscitation and temporary dose holds." | harmful | Skip if trial's primary endpoint is GI-related or mentions GI toxicity management |
| 8 | A08 | Thromboembolic event signal | "In the preceding safety cohort of 40 treated subjects, one deep vein thrombosis and one pulmonary embolism were reported, both within 6 weeks of treatment initiation." | harmful | Skip if trial mentions DVT, PE, thromboembolism, or anticoagulation therapy |
| 9 | A09 | Treatment-emergent suicidality signal | "In the preceding safety cohort, 3 treated subjects reported new-onset suicidal ideation (C-SSRS score increase ≥2 points from baseline) within the first 8 weeks of dosing." | harmful | Skip if trial already mentions suicidality, C-SSRS, or is studying suicidal ideation |
| 10 | A10 | Severe dermatologic reaction signal | "In the preceding extended-dosing cohort, two cases of mucocutaneous reactions with skin detachment (suspected Stevens-Johnson syndrome) were reported; both required hospitalization and drug withdrawal." | harmful | Skip if trial mentions SJS, TEN, Stevens-Johnson, or toxic epidermal necrolysis |
| 11 | A11 | Drug-drug interaction signal | "A dedicated interaction study showed that co-administration with strong CYP3A4 inhibitors increased the study drug's AUC by 5.2-fold, necessitating a contraindication for concomitant use with azole antifungals and certain HIV protease inhibitors." | harmful | Apply only if intervention type is DRUG (skip BIOLOGICAL); skip if trial mentions CYP3A4 or a drug-interaction study |
| 12 | A12 | Reproductive toxicity signal | "Nonclinical reproductive toxicology studies revealed embryo-fetal lethality and major skeletal malformations at sub-therapeutic exposures; a pregnancy prevention program and monthly pregnancy testing are mandated for all subjects of childbearing potential." | harmful | Skip if trial already mentions teratogenicity, pregnancy prevention, or Category X |

---

## Category B: Protocol / Design Modifications (8 items)

These modify structural parameters of the trial. Some require changing a
specific field value; others append text to briefSummary.

| # | ID | Name | Perturbation text / modification | Expected | Filter rule |
|---|-----|------|----------------------------------|----------|-------------|
| 13 | B01 | Halve enrollment | Set enrollmentCount = ceil(N/2). Append: "Due to slower-than-anticipated recruitment, the target enrollment was reduced from {N} to {ceil(N/2)} subjects." | harmful | Skip if enrollment already <20 |
| 14 | B02 | Double enrollment | Set enrollmentCount = N×2. Append: "Based on interim power analysis, enrollment was expanded from {N} to {N×2} subjects to ensure adequate statistical power for the primary endpoint." | helpful | Apply only to Phase 2/3 with an efficacy primary endpoint; skip if enrollment >2000 or = 0 |
| 15 | B03 | Switch to open-label | Set masking = "NONE". Append: "The protocol was amended to remove masking and adopt an open-label design after enrollment challenges made maintaining the blind infeasible." | harmful | Skip if trial is already open-label / no masking |
| 16 | B04 | Add interim futility analysis | Append: "An independent Data Safety Monitoring Board will conduct a pre-specified interim futility analysis at 50% information fraction, with stopping recommended if conditional power falls below 10%." | neutral | Apply only to Phase 2/3 with an efficacy primary endpoint; skip if trial already mentions DSMB, futility or interim analysis |
| 17 | B05 | Shorten treatment duration by half | Append: "Based on emerging pharmacokinetic data suggesting rapid target engagement, the treatment period was shortened by 50% from the original protocol." | harmful | Skip single-dose / single-ascending-dose trials |
| 18 | B06 | Add active comparator arm | Append an ACTIVE_COMPARATOR arm (label/type/description only, same shape as existing arms) to armGroups and a matching standard-of-care entry to interventions. Append: "The protocol was amended to add an active comparator arm receiving the current standard-of-care treatment; the primary analysis was revised to a non-inferiority comparison against this arm." | harmful | Apply only to Phase 2/3, allocation = RANDOMIZED, arms include placebo, efficacy primary endpoint; skip if any arm is already ACTIVE_COMPARATOR |
| 19 | B07 | Remove upper age limit | Remove upper age limit (maximumAge → ""). Append: "The upper age limit was removed to increase generalizability, with additional cardiac and renal monitoring required for older participants." | neutral | Skip if maximumAge already "" (41/100) or maximumAge < 18 years (pediatric, 5/100) |
| 20 | B08 | Restrict to single site | Append: "Enrollment is limited to a single investigational site due to regulatory constraints in other planned regions." | harmful | DISABLED in v0 — site count not in spec fields; kept for expert labeling only |

---

## Category C: Positive Signals (4 items)

These test whether the model also responds to favorable information — not just
threats. If the model is reasoning, it should shift toward SUCCESS for these.

| # | ID | Name | Perturbation text (insert into briefSummary) | Expected | Filter rule |
|---|-----|------|----------------------------------------------|----------|-------------|
| 21 | C01 | Strong preclinical efficacy | "In pivotal preclinical studies, the investigational agent demonstrated robust dose-dependent target engagement with >90% inhibition at clinically achievable concentrations, and a therapeutic index exceeding 10× in the relevant animal toxicology models." | helpful | Always apply |
| 22 | C02 | Positive interim efficacy signal | "A pre-planned interim efficacy analysis at 60% enrollment showed conditional power exceeding 90% for the primary endpoint, and the independent DSMB recommended trial continuation without modification." | helpful | Apply only to Phase 2/3 with an efficacy primary endpoint (conditional power needs an inferential endpoint) |
| 23 | C03 | Breakthrough therapy designation | "The investigational agent has been granted Breakthrough Therapy Designation by the FDA based on preliminary clinical evidence of substantial improvement over available therapies for this indication." | helpful | Skip if trial already mentions breakthrough designation |
| 24 | C04 | Prior study met prespecified objectives | "The preceding clinical study met its prespecified primary objective and all secondary objectives, and the safety profile was favorable with no drug-related serious adverse events reported." | helpful | Apply only to Phase 2/3 (Phase 1 has no preceding clinical phase) |

---

## Category D: External / Contextual (2 items)

These add information from outside the trial itself — regulatory or competitive
landscape changes that affect trial prospects.

| # | ID | Name | Perturbation text (insert into briefSummary) | Expected | Filter rule |
|---|-----|------|----------------------------------------------|----------|-------------|
| 25 | D01 | Competing therapy approved | "Since this trial's initiation, a competing therapy for the same indication received FDA approval, establishing a new standard of care and potentially affecting the clinical relevance of the study's primary endpoint and recruitment feasibility." | harmful | Always apply |
| 26 | D02 | Regulatory safety alert on drug class | "The FDA has issued a Drug Safety Communication regarding increased cardiovascular risk associated with the pharmacological class of the study drug, requiring enhanced cardiac monitoring for all current and future trial subjects." | harmful | Skip if trial already mentions a Drug Safety Communication or boxed warning |

---

## Summary statistics

| Category | Count | Expected harmful | Expected helpful | Expected neutral |
|----------|-------|-----------------|-----------------|-----------------|
| A: AE/SAE early signs | 12 | 12 | 0 | 0 |
| B: Protocol/design | 8 | 5 | 1 | 2 |
| C: Positive signals | 4 | 0 | 4 | 0 |
| D: External/contextual | 2 | 2 | 0 | 0 |
| **Total** | **26** (25 enabled; B08 disabled in v0) | **19** | **5** | **2** |

## Notes for Yousef

1. For each perturbation, please label: **helpful** (increases trial success
   likelihood), **neutral** (no meaningful effect), or **harmful** (decreases
   trial success likelihood).
2. These are meant to be broadly applicable across trials, subject to the
   per-item filter rules (some apply only to Phase 2/3, randomized, DRUG-type,
   or efficacy-endpoint trials). If a perturbation reads unnatural for certain
   trial types even after those filters, please note which types.
3. Feel free to suggest rewording if the clinical language sounds unnatural.
4. If any perturbation's expected direction is wrong, that's fine — your label
   is what we use.
5. Optional: for the AE/SAE items (A01–A12), if you can rank them by clinical
   severity (how much each would realistically threaten a trial), that's very
   useful for our sensitivity analysis.
