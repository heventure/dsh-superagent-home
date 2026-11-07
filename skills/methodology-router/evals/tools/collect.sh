#!/bin/sh
# Collect harness evidence + sanitized output for the runs listed in a TSV map.
# usage: collect.sh <runs.tsv> <session-root> <results-dir>
# TSV columns: run-id, arm (enabled|control), scenario, subagent-id
set -eu
map="$1"; root="$2"; out="$3"
mkdir -p "$out/runs"
here=$(cd "$(dirname "$0")" && pwd)
while IFS="$(printf '\t')" read -r run arm scen id; do
  [ -n "${run:-}" ] || continue
  src="$root/$id/session.v4.jsonl.zstd"
  [ -f "$src" ] || { echo "$run MISSING"; continue; }
  node "$here/run_evidence.mjs" "$src" | node "$here/redact.mjs" > "$out/runs/$run.json"
  node -e '
const j=require(process.argv[1]);
console.log([process.argv[2],process.argv[3],process.argv[4],j.model,j.started_at,
  "catalog="+j.catalog_lists_skill,"loads="+j.skill_loaded_calls,
  "output_chars="+(j.sent_messages.join("\n\n")||j.final_text).length].join("\t"))
' "$out/runs/$run.json" "$run" "$arm" "$scen"
done < "$map"
