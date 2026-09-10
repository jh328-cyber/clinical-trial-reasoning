#!/usr/bin/env bash
# run_multi_model.sh — the same 100 trials against several model families.
#
# The environment carries no model configuration: `taskset.py` defines the chain
# and the scorers, and the endpoint is chosen entirely at the CLI. So a
# cross-model comparison is this file — one invocation per provider, every flag
# except `--model`/`--client.*` held fixed, so a difference in the numbers is a
# difference between models rather than between run configurations.
#
# Usage:
#   scripts/run_multi_model.sh                  # every model marked default below
#   scripts/run_multi_model.sh qwen-plus        # just these
#   DRY_RUN=1 scripts/run_multi_model.sh        # resolve configs, run nothing

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

NUM_TASKS="${NUM_TASKS:-100}"
NUM_ROLLOUTS="${NUM_ROLLOUTS:-1}"
# Held at 4 deliberately: DashScope's free tier throttles well below the
# library's default of 128, and a 429 mid-chain kills the episode rather than
# retrying it, which would show up as model failure in the analysis.
CONCURRENCY="${CONCURRENCY:-4}"
OUTPUT_DIR="${OUTPUT_DIR:-results}"

# name | model id | base_url | api key env var
# The name is the results subdirectory and the label the analysis reports under.
MODELS=(
  "qwen-plus|qwen-plus|https://dashscope.aliyuncs.com/compatible-mode/v1|DASHSCOPE_API_KEY"
  "gpt-4o-mini|gpt-4o-mini|https://api.openai.com/v1|OPENAI_API_KEY"
  "deepseek-chat|deepseek-chat|https://api.deepseek.com|DEEPSEEK_API_KEY"
)
# Run when no model is named on the command line. deepseek-chat is excluded
# until DEEPSEEK_API_KEY holds an actual DeepSeek key — see the guard below.
DEFAULT_MODELS=("qwen-plus" "gpt-4o-mini")

# --- environment ----------------------------------------------------------
# The verifiers CLI reads keys from the environment by variable NAME
# (`--client.api-key-var`); nothing is ever passed on the command line, where it
# would land in the shell history and in `ps`.
if [[ -f .env ]]; then
  set -a; . ./.env; set +a
else
  echo "error: no .env at $REPO_ROOT/.env" >&2
  echo "Create one with DASHSCOPE_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY." >&2
  exit 1
fi

run_one() {
  local name="$1" model="$2" base_url="$3" key_var="$4"
  local key="${!key_var:-}"

  if [[ -z "$key" ]]; then
    echo "SKIP $name — \$$key_var is not set in .env" >&2
    return 0
  fi
  # An Anthropic key posted to DashScope/OpenAI/DeepSeek is a credential
  # disclosed to a third party, and the request fails anyway. Refuse rather
  # than let a copy-paste slip in .env leak it.
  if [[ "$key" == sk-ant-* && "$base_url" != *anthropic.com* ]]; then
    echo "SKIP $name — \$$key_var looks like an Anthropic key (sk-ant-…);" >&2
    echo "     refusing to send it to $base_url." >&2
    return 0
  fi

  echo
  echo "=== $name  ($model @ $base_url) ==============================="
  uv run --project environments/clinical_trial_reasoning eval clinical-trial-reasoning \
    --env.agent.harness.id null \
    --env.agent.runtime.type subprocess \
    --model "$model" \
    --client.base-url "$base_url" \
    --client.api-key-var "$key_var" \
    -n "$NUM_TASKS" -r "$NUM_ROLLOUTS" -c "$CONCURRENCY" \
    -o "$OUTPUT_DIR" --run.dir "$name" \
    --no-push \
    ${DRY_RUN:+--dry-run}
}

selected=("$@")
if [[ ${#selected[@]} -eq 0 ]]; then selected=("${DEFAULT_MODELS[@]}"); fi

for want in "${selected[@]}"; do
  found=""
  for entry in "${MODELS[@]}"; do
    IFS='|' read -r name model base_url key_var <<<"$entry"
    if [[ "$name" == "$want" ]]; then
      run_one "$name" "$model" "$base_url" "$key_var"
      found=1
      break
    fi
  done
  if [[ -z "$found" ]]; then
    echo "error: unknown model '$want'. Known:" >&2
    printf '  %s\n' "${MODELS[@]%%|*}" >&2
    exit 1
  fi
done

echo
echo "Done. Analyse with:  uv run --project environments/clinical_trial_reasoning \\"
echo "                       python scripts/analyze_cross_model.py $OUTPUT_DIR"
