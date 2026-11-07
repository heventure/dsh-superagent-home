#!/usr/bin/env node
// Build the trigger table and confusion matrix for one run set from collected evidence.
//
// usage: node summarize.mjs <runs.tsv> <results-dir>
//   runs.tsv columns: run-id, arm (enabled|control), scenario, session-id, status
// stdout: TSV per run. stderr: headline counts, split by scenario set and language.
// Expected trigger comes from the scenario id: S1/S2/S3/S6/T*/H1/H2 expect a load, S4/N*
// expect none, S5/D*/H3/P* are behaviour-only. A control run has no verdict. An interrupted
// run with no load is inconclusive and counts on neither side; one that loaded is a load.
// prompt_ok compares the recorded prompt with evals/prompts.jsonl and trigger_set.jsonl.
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const [mapFile, resultsDir] = process.argv.slice(2)
const evals = join(dirname(fileURLToPath(import.meta.url)), '..')
const jsonl = (f) => readFileSync(join(evals, f), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l))
const expectedPrompt = new Map([...jsonl('prompts.jsonl'), ...jsonl('trigger_set.jsonl')].map((r) => [r.id, r.prompt]))
const lang = new Map(jsonl('trigger_set.jsonl').map((r) => [r.id, r.lang]))

const expectation = (s) =>
  /^T\d+$/.test(s) || ['S1', 'S2', 'S3', 'S6', 'H1', 'H2'].includes(s)
    ? 'trigger'
    : /^N\d+$/.test(s) || s === 'S4'
      ? 'no_trigger'
      : 'n/a'

const rows = readFileSync(mapFile, 'utf8').split('\n').filter((l) => l.trim()).map((line) => {
  const [run, arm, scenario, , status = 'complete'] = line.split('\t')
  const ev = JSON.parse(readFileSync(`${resultsDir}/runs/${run}.json`, 'utf8'))
  const expected = expectation(scenario)
  const loaded = ev.skill_loaded_calls > 0
  let verdict = 'behaviour-only'
  if (arm === 'control') verdict = 'control'
  else if (expected !== 'n/a') {
    if (status === 'interrupted' && !loaded) verdict = 'inconclusive'
    else if (expected === 'trigger') verdict = loaded ? 'hit' : 'miss'
    else verdict = loaded ? 'false-trigger' : 'correct-skip'
  }
  return {
    run, arm, scenario, status, expected, verdict,
    catalog: ev.catalog_lists_skill,
    loads: ev.skill_loaded_calls,
    prompt_ok: ev.prompt === expectedPrompt.get(scenario),
    read_eval: (ev.read_eval_materials ?? []).length,
    chars: `${(ev.sent_messages ?? []).join('').length}+${(ev.final_text ?? '').length}`,
  }
})

const cols = ['run', 'arm', 'scenario', 'status', 'expected', 'catalog', 'loads', 'prompt_ok', 'read_eval', 'chars', 'verdict']
console.log(cols.join('\t'))
for (const r of rows) console.log(cols.map((c) => r[c]).join('\t'))

const n = (pred) => rows.filter(pred).length
const report = (label, pred) => {
  const hit = n((r) => pred(r) && r.verdict === 'hit')
  const miss = n((r) => pred(r) && r.verdict === 'miss')
  const skip = n((r) => pred(r) && r.verdict === 'correct-skip')
  const fp = n((r) => pred(r) && r.verdict === 'false-trigger')
  console.error(`${label}: should-trigger ${hit}/${hit + miss}; should-skip ${skip}/${skip + fp}; inconclusive ${n((r) => pred(r) && r.verdict === 'inconclusive')}`)
}
report('all', () => true)
report('excluding runs that read eval materials', (r) => r.read_eval === 0)
report('zh', (r) => (lang.get(r.scenario) ?? 'zh') === 'zh')
report('en', (r) => lang.get(r.scenario) === 'en')
console.error(`prompt_mismatch: ${rows.filter((r) => !r.prompt_ok && r.scenario[0] !== 'P').map((r) => r.run).join(', ') || 'none'}`)
console.error(`read_eval_materials: ${rows.filter((r) => r.read_eval > 0).map((r) => r.run).join(', ') || 'none'}`)
