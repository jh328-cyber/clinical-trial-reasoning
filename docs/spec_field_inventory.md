# Trial spec field inventory

Source: `data/trial_specs.jsonl` — 100 trials, the same NCT IDs and the same order as `data/trials.jsonl`.

Counts are of trials where the field is **non-empty** (a non-blank string, a non-empty list, or any number). "Median words" counts whitespace-separated tokens across all text in the field; for list fields "median items" is the list length. Examples are real values, shortest-first so the table stays readable, truncated at 180 characters.

This document is an inventory. It records what the corpus contains and proposes no clinical content.

## All fields

| Field | Kind | Non-empty | Coverage | Median words | Median items |
|---|---|---|---|---|---|
| `briefSummary` | text | 100/100 | 100% | 41.0 | — |
| `detailedDescription` | text | 55/100 | 55% | 138.0 | — |
| `eligibilityCriteria` | text | 100/100 | 100% | 315.0 | — |
| `sex` | scalar | 100/100 | 100% | 1.0 | — |
| `minimumAge` | scalar | 98/100 | 98% | 2.0 | — |
| `maximumAge` | scalar | 59/100 | 59% | 2.0 | — |
| `enrollmentCount` | scalar | 100/100 | 100% | 1.0 | — |
| `armGroups` | list | 100/100 | 100% | 38.0 | 2.0 |
| `interventions` | list | 100/100 | 100% | 18.0 | 2.0 |
| `primaryOutcomes` | list | 100/100 | 100% | 22.0 | 1.0 |
| `secondaryOutcomes` | list | 91/100 | 91% | 85.0 | 6.0 |
| `allocation` | scalar | 100/100 | 100% | 1.0 | — |
| `interventionModel` | scalar | 100/100 | 100% | 1.0 | — |
| `masking` | scalar | 100/100 | 100% | 1.0 | — |
| `phases` | list | 100/100 | 100% | 1.0 | 1.0 |
| `conditions` | list | 100/100 | 100% | 3.0 | 1.0 |
| `leadSponsor` | scalar | 100/100 | 100% | 3.0 | — |

## Universal fields (present in ≥95 of 100)

Every trial in the corpus carries these, so a perturbation that must be insertable for an arbitrary trial can be placed in any of them.

### `briefSummary`

Lay/technical summary of the study. Non-empty in **100/100** trials (100%); median 41.0 words.

- `Phase II study of TAS-102 plus bevacizumab switch maintenance therapy in patients with mCRC`
- `An extension study of safety and tolerability of SEP-363856 in adult subjects with schizophrenia`

### `eligibilityCriteria`

Inclusion/exclusion criteria block. Non-empty in **100/100** trials (100%); median 315.0 words.

- `Inclusion Criteria: * adult patients with clinical diagnosis of cyclic vomiting in the ED Exclusion Criteria: * pregnancy, allergy to any of the study medicines`
- `Inclusion Criteria: * Body mass index (BMI) of 30-43 kg/m2 * Waist circumference \> 40 inches in males or \> 30 inches in females * Normal ECG readings Exclusion Criteria: * Signif…`

### `sex`

Eligible sex. Non-empty in **100/100** trials (100%); median 1.0 words.

- `ALL`
- `MALE`

### `minimumAge`

Minimum eligible age. Non-empty in **98/100** trials (98%); median 2.0 words.

- `1 Year`
- `4 Years`

### `enrollmentCount`

Enrolment count. Non-empty in **100/100** trials (100%); median 1.0 words.

- `1`
- `6`

### `armGroups`

Arm labels, types and descriptions. Non-empty in **100/100** trials (100%); median 38.0 words, median 2.0 items.

- `DBPR112`
- `Lu AF11167`

### `interventions`

Intervention names, types and descriptions. Non-empty in **100/100** trials (100%); median 18.0 words, median 2.0 items.

- `FOLFIRINOX`
- `idarucizumab`

### `primaryOutcomes`

Primary outcome measures + time frames. Non-empty in **100/100** trials (100%); median 22.0 words, median 1.0 items.

- `VAS`
- `Adverse Events`

### `allocation`

designInfo.allocation. Non-empty in **100/100** trials (100%); median 1.0 words.

- `NA`
- `RANDOMIZED`

### `interventionModel`

designInfo.interventionModel. Non-empty in **100/100** trials (100%); median 1.0 words.

- `PARALLEL`
- `CROSSOVER`

### `masking`

designInfo.maskingInfo.masking. Non-empty in **100/100** trials (100%); median 1.0 words.

- `NONE`
- `SINGLE`

### `phases`

Registered phase(s). Non-empty in **100/100** trials (100%); median 1.0 words, median 1.0 items.

- `PHASE2`
- `PHASE3`

### `conditions`

Conditions studied. Non-empty in **100/100** trials (100%); median 3.0 words, median 1.0 items.

- `ICC`
- `AML`

### `leadSponsor`

Lead sponsor name. Non-empty in **100/100** trials (100%); median 3.0 words.

- `EMS`
- `argenx`

## Trial-specific fields (present in <95 of 100)

These are missing for some trials, so anything keyed to them applies only to the subset that has them. The count next to each field is that subset's size.

### `detailedDescription`

Extended protocol narrative. Non-empty in **55/100** trials (55%); median 138.0 words.

- `The total study duration per participant was up to 68 weeks that consisted of a 4-weeks run-in period, 52-weeks treatment period, and a 12-weeks post treatment period.`
- `This will be a 12-week, randomized, double blind, placebo-controlled safety and efficacy study in men and women ≥18 years of age with fasting triglycerides ≥500 mg/dL and \<2000 mg…`

### `maximumAge`

Maximum eligible age. Non-empty in **59/100** trials (59%); median 2.0 words.

- `7 Years`
- `9 Years`

### `secondaryOutcomes`

Secondary outcome measures + time frames. Non-empty in **91/100** trials (91%); median 85.0 words, median 6.0 items.

- `Efficacy: Dynamometry Score`
- `Time to Viral Rebound`

## Excluded by the leakage policy

`overallStatus`, `whyStopped`, `startDate`, `completionDate`, `resultsSection` and the top-level `hasResults` flag are absent from the corpus by construction. `scripts/fetch_trial_specs.py` requests only the protocol modules it needs via the API's `fields` parameter, so these are never fetched, never cached and never written. `enrollmentInfo.type` (ACTUAL vs ESTIMATED) is also omitted, as it hints at whether enrolment completed.

