#!/usr/bin/env bash
# run_spec_mode.sh — run the six-step chain in SPEC MODE (arm B): the model is
# shown the registered trial specification, baseline or perturbed.
#
# Same chain, same scorers, same model flags as run_multi_model.sh; the only
# difference is `--env.taskset.data-path`, which points at a {row_id, spec}
# file produced by scripts/generate_perturbed_cases.py --emit-model-input
# (or scripts/make_pilot.py). Nothing in those files identifies the perturbation.
#
# Usage:
#   scripts/run_spec_mode.sh <model-name> <data-file> <run-dir-name>
#
#   scripts/run_spec_mode.sh deepseek-chat data/pilot_baseline_specs_v0.jsonl  pilot_baseline
#   scripts/run_spec_mode.sh deepseek-chat data/pilot_perturbed_specs_v0.jsonl pilot_perturbed
#   DRY_RUN=1 scripts/run_spec_mode.sh deepseek-chat data/pilot_baseline_specs_v0.jsonl pilot_baseline
#
# Results land in results/spec/<model-name>/<run-dir-name>/traces.jsonl.
# NUM_TASKS defaults to every row in the data file.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$REPO_ROOT"

name="${1:?model name (deepseek-chat | gpt-4o-mini | qwen-plus)}"
data="${2:?data file, e.g. data/pilot_baseline_specs_v0.jsonl}"
run_dir="${3:?run dir name, e.g. pilot_baseline}"
[[ -f "$data" ]] || { echo "error: $data not found" >&2; exit 1; }

NUM_TASKS="${NUM_TASKS:-$(grep -c . "$data")}"
NUM_ROLLOUTS="${NUM_ROLLOUTS:-1}"
CONCURRENCY="${CONCURRENCY:-4}"
OUTPUT_DIR="${OUTPUT_DIR:-results/spec/$name}"

case "$name" in
  deepseek-chat) model="deepseek-chat"; base_url="https://api.deepseek.com";                       key_var="DEEPSEEK_API_KEY" ;;
  gpt-4o-mini)   model="gpt-4o-mini";   base_url="https://api.openai.com/v1";                      key_var="OPENAI_API_KEY" ;;
  qwen-plus)     model="qwen-plus";     base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"; key_var="DASHSCOPE_API_KEY" ;;
  *) echo "error: unknown model '$name'" >&2; exit 1 ;;
esac

# Keys come from .env by variable NAME; never on the command line.
if [[ -f .env ]]; then set -a; . ./.env; set +a; else echo "error: no .env at $REPO_ROOT/.env" >&2; exit 1; fi
key="${!key_var:-}"
[[ -n "$key" ]] || { echo "error: \$$key_var is not set in .env" >&2; exit 1; }
if [[ "$key" == sk-ant-* && "$base_url" != *anthropic.com* ]]; then
  echo "error: \$$key_var looks like an Anthropic key; refusing to send it to $base_url" >&2; exit 1; fi
probe=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 -H "Authorization: Bearer $key" "${base_url%/}/models" 2>/dev/null || echo "000")
if [[ "$probe" == "401" || "$probe" == "403" ]]; then echo "error: \$$key_var rejected by $base_url (HTTP $probe)" >&2; exit 1; fi

echo "=== $name  spec-mode  $data  ($NUM_TASKS tasks x $NUM_ROLLOUTS rollouts, c=$CONCURRENCY) -> $OUTPUT_DIR/$run_dir"
uv run --project environments/clinical_trial_reasoning eval clinical-trial-reasoning \
  --env.agent.harness.id null \
  --env.agent.runtime.type subprocess \
  --env.taskset.data-path "$data" \
  --model "$model" \
  --client.base-url "$base_url" \
  --client.api-key-var "$key_var" \
  -n "$NUM_TASKS" -r "$NUM_ROLLOUTS" -c "$CONCURRENCY" \
  -o "$OUTPUT_DIR" --run.dir "$run_dir" \
  --no-push \
  ${DRY_RUN:+--dry-run}
