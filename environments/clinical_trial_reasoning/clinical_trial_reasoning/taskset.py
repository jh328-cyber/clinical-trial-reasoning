"""clinical-trial-reasoning: staged, closed-book reasoning about trial outcomes.

Arm A of the proposal: the model gets an NCT ID and the registered brief title and
nothing else — no tools, no retrieval. The episode is a fixed sequence of questions
issued by the environment rather than a single prompt, so each reasoning step lands
as its own assistant message and is scored separately.

The full chain: S1 (recall) -> S2 (reference class) -> S3 (base rate) ->
S4 (success criteria) -> S5 (risk factors) -> S6 (outcome). Reordering or dropping
a step for an ablation is an edit to STEPS and STEP_NAMES alone.

S3-S5 are scored on calibration and structure, not against trial-specific ground
truth — the row data carries no registered endpoint or labelled failure mode to
check them against. They are placeholders for real scorers, not measurements of
reasoning quality.

Why the task's prompt is None: `Interaction.turn()` has an asymmetric first-turn
rule — a prompted task must take its opening reply with a bare `turn()`, while a
prompt-less task is opened by `turn(message)`. Seeding S1 through `TaskData.prompt`
would therefore make S1 structurally different from S2/S6 and unswappable. Nulling
the prompt keeps all steps symmetric.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import verifiers.v1 as vf

# --------------------------------------------------------------------------
# Step prompts
# --------------------------------------------------------------------------

S1_PROMPT = (
    'Here is a clinical trial: {nct_id} — "{trial_title}"\n\n'
    "Without looking up any information, tell me everything you know about this trial. "
    "Include: drug name and mechanism, sponsor, phase, indication, "
    "primary endpoint, planned enrollment, key dates.\n\n"
    "For any field you are not sure about, write 'unknown'. Do not fabricate."
)

S2_PROMPT = (
    "Now list 3-5 clinical trials that you believe are most similar to this one. "
    "For each, provide:\n"
    "- NCT ID (if you know it)\n"
    "- Drug name and indication\n"
    "- Phase\n"
    "- Outcome (SUCCESS / FAILURE / unknown)\n"
    "- Why it is similar to the trial in question\n\n"
    "If you are unsure about any detail, say 'unknown'. Do not fabricate."
)

S6_PROMPT = (
    "Based on your recall of this trial and the similar trials you listed, "
    "make your final prediction:\n\n"
    "Format your answer EXACTLY as:\n"
    "PREDICTION: SUCCESS or FAILURE\n"
    "CONFIDENCE: a number between 0.0 and 1.0\n"
    "KEY_REASON: one sentence explaining the most important factor"
)

S3_PROMPT = (
    "Based on your knowledge of clinical trials, what is the historical "
    "base rate of success for trials like this one?\n\n"
    "Consider:\n"
    "- Phase: {phase}\n"
    "- Indication: {indication}\n"
    "- Drug class and mechanism (from what you recalled earlier)\n\n"
    "Provide your answer EXACTLY as:\n"
    "BASE_RATE: [a number between 0.0 and 1.0]\n"
    "REASONING: [one paragraph explaining how you arrived at this estimate]"
)

S4_PROMPT = (
    "Based on the trial design of {nct_id}, describe what would constitute "
    "a successful outcome.\n\n"
    "Include:\n"
    "1. The likely primary endpoint(s) and how they would be measured\n"
    "2. The statistical threshold that would need to be met (e.g., p<0.05, "
    "hazard ratio, non-inferiority margin)\n"
    "3. Whether this is likely a superiority, non-inferiority, or equivalence trial\n"
    "4. Key design features (randomization, blinding, control arm)\n\n"
    "If you are unsure about any detail, say 'unknown'. Do not fabricate."
)

S5_PROMPT = (
    "What are the key risk factors that could cause this trial to fail?\n\n"
    "List 3-5 specific risks, ordered from most to least concerning. "
    "For each risk, provide:\n"
    "- RISK: [name of the risk]\n"
    "- APPLIES_BECAUSE: [why this risk is relevant to THIS specific trial]\n"
    "- LIKELIHOOD: HIGH, MEDIUM, or LOW\n\n"
    "Consider: safety signals from earlier phases, efficacy concerns, "
    "enrollment challenges, regulatory issues, competitive landscape, "
    "and trial design limitations."
)

STEPS = [S1_PROMPT, S2_PROMPT, S3_PROMPT, S4_PROMPT, S5_PROMPT, S6_PROMPT]
STEP_NAMES = [
    "s1_recall",
    "s2_reference",
    "s3_base_rate",
    "s4_criteria",
    "s5_risks",
    "s6_outcome",
]

# Scorers address steps by name, never by a bare integer: adding S3-S5 silently
# moved S6 from index 2 to index 5, and an ablation that reorders STEPS would do
# the same again. Keep STEPS and STEP_NAMES in the same order and these follow.
STEP_INDEX = {name: i for i, name in enumerate(STEP_NAMES)}

# Industry phase-transition success rates (BIO/QLS/Citeline). Used only as the
# calibration target for S3; they are not trial-specific ground truth.
PHASE_BASE_RATES = {"1": 0.52, "2": 0.29, "3": 0.58}
PHASE_BASE_RATE_FALLBACK = 0.40
BASE_RATE_RE = re.compile(r"BASE_RATE:\s*([\d.]+)")
# The label arrives dressed up: markdown emphasis around it and, most often, an
# ordinal between the word and the colon (`**RISK 1: ...**`). A literal `RISK:`
# pattern scored 50/60 rows as format non-compliance when the model had in fact
# complied, so emphasis and an optional number are both tolerated. What is measured
# is whether the model enumerated labelled risks, not how it styled them.
RISK_TAG_RE = re.compile(r"\*{0,2}RISK\*{0,2}\s*\d*\s*\*{0,2}\s*:", re.IGNORECASE)
RISK_ITEM_RE = re.compile(r"(?:^|\n)\s*(?:\d+[.)]\s*|-\s*\*?\*?)")
LIKELIHOOD_RE = re.compile(
    r"\*{0,2}LIKELIHOOD\*{0,2}\s*:\s*\*{0,2}(HIGH|MEDIUM|LOW)", re.IGNORECASE
)

# S4 is scored on how much of the REGISTERED primary endpoint the model names.
# These words carry no identifying signal — they appear in almost every endpoint
# description and in almost every S4 reply, so leaving them in would rebuild the
# saturated keyword scorer this replaced.
ENDPOINT_STOPWORDS = frozenset(
    """the of in at to and or a an from by for with on as is was between after
    before during through number rate change time week weeks month months day days
    year years baseline study treatment group subjects patients participants
    measured defined percentage proportion mean median""".split()
)
ENDPOINT_WORD_RE = re.compile(r"[a-z]{3,}")
S4_RECALL_BANDS = ((0.6, 1.0), (0.4, 0.7), (0.2, 0.3))

NCT_RE = re.compile(r"NCT\d{8}")
S2_FULL_CREDIT_IDS = 3.0

# Sponsor-name noise stripped before matching: legal-entity suffixes and the
# generic institutional words that carry no identifying information. Both lists
# exist so a match means the model named the DISTINCTIVE part of the sponsor
# ("tennessee", "servier") rather than scoring on "of" or "university", which
# appear in almost any reply.
SPONSOR_CORPORATE_NOISE = re.compile(
    r"\b(inc|ltd|co|corp|llc|plc|sa|ag|gmbh|nv|as|a/s|pharmaceuticals?|pharma"
    r"|biopharmaceuticals?|therapeutics?|biosciences?|biotech|laboratories?|labs?"
    r"|medical|medicine|healthcare|sciences?|research)\b"
)
SPONSOR_GENERIC_NOISE = re.compile(
    r"\b(the|of|for|and|at|in|de|du|la|le|el|group|holdings?|company|center|centre"
    r"|hospital|university|universitaire|school|college|institute|instituto|nacional"
    r"|national|foundation|health|system|clinic|trust|general|cancer|oncology"
    r"|first|second)\b"
)
SPONSOR_RECALL_THRESHOLD = 0.5


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------


class TrialData(vf.TaskData):
    """One trial, closed-book.

    `prompt` stays None — the environment issues every step through `turn()`.
    None of the outcome-bearing CTG fields (overall_status, why_stopped,
    has_results) reach this row; `scripts/prepare_data.py` drops them at the
    source.
    """

    nct_id: str
    label: str
    phase: str
    indication: str
    sponsor: str
    drug_name: str
    trial_title: str
    primary_endpoint: str = ""
    """The registered primary outcome measure(s). Scoring-side only: no step prompt
    interpolates it, so S4 is asked to produce what this field already knows."""
    split: str = "unknown"


# --------------------------------------------------------------------------
# Task
# --------------------------------------------------------------------------


def _step_reply(trace: vf.Trace, index: int) -> str | None:
    """The model's reply to STEPS[index], or None if that step never ran.

    Assumes one sampled assistant message per step, which holds in arm A: the
    agent has no tools, so a segment cannot loop. `n_assistant_messages` is
    recorded as a metric so a violation of that assumption is visible in the
    output instead of silently misaligning every reward by one.
    """
    messages = trace.assistant_messages
    if index >= len(messages):
        return None
    return messages[index].content or ""


def _endpoint_keyword_recall(endpoint: str, reply: str | None) -> float:
    """Share of the registered endpoint's content words that appear in the reply.

    Returns -1.0 when it cannot be computed — no reply, no registered endpoint, or
    an endpoint made entirely of stopwords. -1.0 is distinct from 0.0 (computed,
    nothing matched) so an ungradable row is never counted as a failure.
    """
    if reply is None:
        return -1.0
    text = (endpoint or "").strip().lower()
    if not text:
        return -1.0
    keywords = {w for w in ENDPOINT_WORD_RE.findall(text) if w not in ENDPOINT_STOPWORDS}
    if not keywords:
        return -1.0
    lowered = reply.lower()
    return sum(1 for kw in keywords if kw in lowered) / len(keywords)


def _phase_base_rate(phase: str) -> float:
    """The industry success rate for this phase, or the fallback if unrecognised."""
    text = (phase or "").upper()
    for digit, rate in PHASE_BASE_RATES.items():
        if digit in text:
            return rate
    return PHASE_BASE_RATE_FALLBACK


def _sponsor_keywords(sponsor: str) -> list[str]:
    """The sponsor's distinctive tokens, legal and generic institutional noise removed.

    "University of Tennessee" -> ["tennessee"], "Gilead Sciences" -> ["gilead"].
    Returns [] for an unknown sponsor or one that is entirely generic.
    """
    name = (sponsor or "").strip().lower()
    if not name or name == "unknown":
        return []
    cleaned = SPONSOR_CORPORATE_NOISE.sub(" ", name)
    cleaned = SPONSOR_GENERIC_NOISE.sub(" ", cleaned)
    cleaned = re.sub(r"[.,\-/()]", " ", cleaned)
    return [token for token in cleaned.split() if len(token) >= 2]


class TrialTask(vf.Task[TrialData]):
    # ---------------- metrics (recorded, unweighted) ----------------

    @vf.metric
    async def n_assistant_messages(self, trace: vf.Trace) -> float:
        """Should equal len(STEPS). Anything else means step<->reply misalignment."""
        return float(len(trace.assistant_messages))

    @vf.metric
    async def drug_name_in_title(self, trace: vf.Trace) -> float:
        """1.0 when the drug name is already visible in the title shown at S1.

        `s1_trial_recall` cannot distinguish recall from copying on these rows, so
        the S1 score is only interpretable stratified by this metric.
        """
        drug = (self.data.drug_name or "").strip().lower()
        if not drug or drug == "unknown":
            return 0.0
        return float(drug in (self.data.trial_title or "").lower())

    @vf.metric
    async def sponsor_in_title(self, trace: vf.Trace) -> float:
        """1.0 when a sponsor keyword is already visible in the title shown at S1.

        The control for `s1_trial_recall`, mirroring `drug_name_in_title`. This
        should stay near 0; if it rises, the S1 score is measuring copying again
        and the recall field has to move to something else.
        """
        title = (self.data.trial_title or "").lower()
        keywords = _sponsor_keywords(self.data.sponsor)
        if not keywords:
            return 0.0
        return float(
            any(re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", title) for kw in keywords)
        )

    @vf.metric
    async def s6_parsed(self, trace: vf.Trace) -> float:
        """1.0 when a SUCCESS/FAILURE prediction could be parsed out of S6."""
        return float(self._prediction(trace) is not None)

    @vf.metric
    async def s6_predicted_success(self, trace: vf.Trace) -> float:
        """1.0 when the model predicted SUCCESS — exposes a degenerate all-one-class run."""
        return float(self._prediction(trace) == "SUCCESS")

    @vf.metric
    async def s3_stated_base_rate(self, trace: vf.Trace) -> float:
        """The base rate the model actually stated, or -1.0 if it stated none.

        The reward collapses this to a 0/0.5/1 band; the raw number is what shows
        whether the model anchors on one habitual value across every trial.
        """
        reply = _step_reply(trace, STEP_INDEX["s3_base_rate"])
        match = BASE_RATE_RE.search(reply or "")
        if not match:
            return -1.0
        try:
            return float(match.group(1))
        except ValueError:
            return -1.0

    @vf.metric
    async def s5_risk_items(self, trace: vf.Trace) -> float:
        """How many risks S5 enumerated (RISK: tags, else list items)."""
        reply = _step_reply(trace, STEP_INDEX["s5_risks"])
        if reply is None:
            return 0.0
        tagged = len(RISK_TAG_RE.findall(reply))
        return float(tagged or len(RISK_ITEM_RE.findall(reply)))

    @vf.metric
    async def s5_likelihood_tags(self, trace: vf.Trace) -> float:
        """How many risks carried a LIKELIHOOD: HIGH/MEDIUM/LOW tag."""
        reply = _step_reply(trace, STEP_INDEX["s5_risks"])
        return float(len(LIKELIHOOD_RE.findall(reply or "")))

    @vf.metric
    async def s4_endpoint_keyword_recall(self, trace: vf.Trace) -> float:
        """Raw endpoint keyword recall behind the S4 bands; -1.0 if ungradable."""
        return _endpoint_keyword_recall(
            self.data.primary_endpoint, _step_reply(trace, STEP_INDEX["s4_criteria"])
        )

    @vf.metric
    async def s5_risk_tag_count(self, trace: vf.Trace) -> float:
        """RISK: tags in S5 — the count the reward now uses, without the bullet fallback."""
        reply = _step_reply(trace, STEP_INDEX["s5_risks"])
        return float(len(RISK_TAG_RE.findall(reply or "")))

    @vf.metric
    async def s3_reply_length(self, trace: vf.Trace) -> float:
        return float(len(_step_reply(trace, STEP_INDEX["s3_base_rate"]) or ""))

    @vf.metric
    async def s4_reply_length(self, trace: vf.Trace) -> float:
        return float(len(_step_reply(trace, STEP_INDEX["s4_criteria"]) or ""))

    @vf.metric
    async def s5_reply_length(self, trace: vf.Trace) -> float:
        return float(len(_step_reply(trace, STEP_INDEX["s5_risks"]) or ""))

    @vf.metric
    async def s2_nct_ids(self, trace: vf.Trace) -> float:
        """Count of well-formed NCT IDs offered at S2 (format only, not existence)."""
        reply = _step_reply(trace, STEP_INDEX["s2_reference"])
        return float(len(set(NCT_RE.findall(reply or ""))))

    # ---------------- rewards (weighted) ----------------

    @vf.reward(weight=0.10)
    async def s1_trial_recall(self, trace: vf.Trace) -> float:
        """Did the model name the trial's SPONSOR — information the prompt withholds?

        The prompt shows the NCT ID and the brief title. The drug name is in that
        title 72% of the time, so scoring recall on the drug measures copying; the
        sponsor's distinctive token appears in only ~12% of titles, so naming it is
        evidence the model has actually seen the trial. Credit requires at least
        half the sponsor's distinctive keywords, matched on word boundaries.
        """
        reply = _step_reply(trace, STEP_INDEX["s1_recall"])
        if reply is None:
            return 0.0
        keywords = _sponsor_keywords(self.data.sponsor)
        if not keywords:
            return 0.0
        text = reply.lower()
        matched = sum(
            1 for kw in keywords if re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", text)
        )
        return float(matched / len(keywords) >= SPONSOR_RECALL_THRESHOLD)

    @vf.reward(weight=0.15)
    async def s2_reference_class(self, trace: vf.Trace) -> float:
        """Format-valid NCT IDs offered at S2, saturating at S2_FULL_CREDIT_IDS.

        First-pass proxy only: it checks shape, not that the IDs exist or that the
        trials are actually similar. Resolving them against the registry is the
        next iteration.
        """
        reply = _step_reply(trace, STEP_INDEX["s2_reference"])
        if reply is None:
            return 0.0
        found = set(NCT_RE.findall(reply))
        if not found:
            return 0.0
        return min(len(found) / S2_FULL_CREDIT_IDS, 1.0)

    @vf.reward(weight=0.10)
    async def s3_base_rate(self, trace: vf.Trace) -> float:
        """Is the stated base rate near the industry phase-transition rate?

        Full credit within 0.10 of the phase rate, half credit within 0.20. The
        target is a population statistic, not this trial's outcome, so a model
        that simply knows phase 2 is the hard one scores well here by design.
        """
        reply = _step_reply(trace, STEP_INDEX["s3_base_rate"])
        if reply is None:
            return 0.0
        match = BASE_RATE_RE.search(reply)
        if not match:
            return 0.0
        try:
            rate = float(match.group(1))
        except ValueError:
            return 0.0
        if not 0.0 <= rate <= 1.0:
            return 0.0
        expected = _phase_base_rate(self.data.phase)
        error = abs(rate - expected)
        if error <= 0.10:
            return 1.0
        return 0.5 if error <= 0.20 else 0.0

    @vf.reward(weight=0.10)
    async def s4_success_criteria(self, trace: vf.Trace) -> float:
        """Did the model name the trial's REGISTERED primary endpoint?

        Banded keyword recall against `primary_endpoint`, which the prompt never
        shows. Replaces a keyword-presence scorer that returned 1.0 on all 60 rows.
        Still lexical: a model that says "objective response rate" scores the same
        whether or not it understood the threshold.
        """
        recall = _endpoint_keyword_recall(
            self.data.primary_endpoint, _step_reply(trace, STEP_INDEX["s4_criteria"])
        )
        if recall < 0:
            return 0.0
        for threshold, score in S4_RECALL_BANDS:
            if recall >= threshold:
                return score
        return 0.0

    @vf.reward(weight=0.15)
    async def s5_risk_factors(self, trace: vf.Trace) -> float:
        """Structure of the risk enumeration: item count, LIKELIHOOD tags, specificity.

        Like S4 this scores form, not whether the risks named are the ones that
        actually threatened the trial. Scoring against the labelled failure mode is
        the next iteration.
        """
        reply = _step_reply(trace, STEP_INDEX["s5_risks"])
        if reply is None:
            return 0.0

        # RISK: tags only. The markdown-bullet fallback this replaces counted every
        # list item in a ~4600-character reply (mean 16.5), so the 3-5 band never
        # fired and the score tracked verbosity instead of risk enumeration.
        risk_count = len(RISK_TAG_RE.findall(reply))

        score = 0.0
        if 3 <= risk_count <= 5:
            score += 0.5
        elif risk_count >= 1:
            score += 0.25

        likelihoods = len(LIKELIHOOD_RE.findall(reply))
        if likelihoods >= 3:
            score += 0.3
        elif likelihoods >= 1:
            score += 0.15

        indication = (self.data.indication or "").strip().lower()
        if indication and indication != "unknown" and indication in reply.lower():
            score += 0.2

        return min(score, 1.0)

    @vf.reward(weight=0.40)
    async def s6_outcome(self, trace: vf.Trace) -> float:
        """Is the final SUCCESS/FAILURE prediction correct?"""
        predicted = self._prediction(trace)
        if predicted is None:
            return 0.0
        return float(predicted == self.data.label.strip().upper())

    # ---------------- helpers ----------------

    def _prediction(self, trace: vf.Trace) -> str | None:
        """SUCCESS / FAILURE parsed out of the S6 reply, or None.

        Reads only the PREDICTION line when the model followed the format; falling
        back to the whole reply would let a KEY_REASON mentioning "failure" flip a
        SUCCESS prediction, so the fallback is limited to a reply that names exactly
        one of the two labels.
        """
        reply = _step_reply(trace, STEP_INDEX["s6_outcome"])
        if reply is None:
            return None
        text = reply.upper()
        if "PREDICTION:" in text:
            text = text.split("PREDICTION:", 1)[1].split("\n", 1)[0]
        has_success = "SUCCESS" in text
        has_failure = "FAILURE" in text
        if has_success == has_failure:  # neither, or ambiguous
            return None
        return "SUCCESS" if has_success else "FAILURE"


# --------------------------------------------------------------------------
# Environment: the staged control flow
# --------------------------------------------------------------------------


class TrialReasoningEnvConfig(vf.EnvConfig):
    agent: vf.AgentConfig = vf.AgentConfig()
    """The one seat under evaluation. Closed-book: give it no tools."""


class TrialReasoningEnv(vf.Env[TrialReasoningEnvConfig]):
    """Issues STEPS as successive user turns against one held-open rollout.

    Step order is enforced here rather than requested in a prompt: the model
    answers each question before it sees the next and cannot revise an earlier
    answer. Ablations (drop a step, reorder, inject a corrected answer) are edits
    to this loop.
    """

    async def run(self, task, agents) -> None:
        staged = type(task)(
            task.data.model_copy(update={"prompt": None}),
            task.config,
        )
        fields = task.data.model_dump()
        async with agents.agent.interaction(staged) as interaction:
            for step_prompt in STEPS:
                segment = await interaction.turn(step_prompt.format(**fields))
                if segment.terminated:
                    # The run ended instead of answering; a further turn() would
                    # raise. Remaining steps stay unanswered and their rewards
                    # score 0 — `n_assistant_messages` records how far it got.
                    break


# --------------------------------------------------------------------------
# Taskset
# --------------------------------------------------------------------------


class TrialReasoningConfig(vf.TasksetConfig):
    data_path: str = "data/trials.jsonl"
    """Row source, relative to the repo root (or absolute)."""

    split: str = ""
    """Keep only rows from this split ("train" / "val"); empty keeps all."""


class TrialReasoningTaskset(vf.Taskset[TrialTask, TrialReasoningConfig]):
    def load(self) -> list[TrialTask]:
        path = Path(self.config.data_path)
        if not path.is_absolute():
            # environments/clinical_trial_reasoning/clinical_trial_reasoning/taskset.py
            path = Path(__file__).resolve().parents[3] / path
        if not path.exists():
            raise FileNotFoundError(
                f"task rows not found at {path}. Run scripts/prepare_data.py first."
            )

        tasks: list[TrialTask] = []
        for idx, line in enumerate(path.read_text().splitlines()):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if self.config.split and record.get("split") != self.config.split:
                continue
            tasks.append(
                TrialTask(
                    TrialData(
                        idx=idx,
                        prompt=None,
                        nct_id=record["nct_id"],
                        label=record["label"],
                        phase=record.get("phase", "unknown"),
                        indication=record.get("indication", "unknown"),
                        sponsor=record.get("sponsor", "unknown"),
                        drug_name=record.get("drug_name", "unknown"),
                        trial_title=record.get("trial_title", record["nct_id"]),
                        primary_endpoint=record.get("primary_endpoint", ""),
                        split=record.get("split", "unknown"),
                    ),
                    self.config.task,
                )
            )
        if not tasks:
            raise ValueError(f"no rows loaded from {path} (split={self.config.split!r})")
        return tasks
