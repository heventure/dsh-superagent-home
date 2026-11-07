#!/bin/sh
# Collect harness evidence + redacted output for the runs listed in a TSV map.
# usage: collect.sh <runs.tsv> <session-root> <results-dir>
# TSV columns: run-id, arm (enabled|control), scenario, session-id, status (complete|interrupted)
set -eu
map="$1"; root="$2"; out="$3"
mkdir -p "$out/runs"
here=$(cd "$(dirname "$0")" && pwd)
while IFS="$(printf '\t')" read -r run arm scen id status; do
  [ -n "${run:-}" ] || continue
  src="$root/$id/session.v4.jsonl.zstd"
  [ -f "$src" ] || { echo "$run MISSING" >&2; continue; }
  node "$here/run_evidence.mjs" "$src" | node "$here/redact.mjs" > "$out/runs/$run.json"
done < "$map"
