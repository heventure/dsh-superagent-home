#!/usr/bin/env node
// Build the trigger/behavior summary table for one run set from collected evidence.
//
// usage: node summarize.mjs <runs.tsv> <results-dir>
//   runs.tsv columns: run-id, arm (enabled|control), scenario, subagent-id
// Prints TSV: run, arm, scenario, expected_trigger, catalog, skill_loaded, output_chars, verdict
// `expected_trigger` comes from the scenario id: S1/S2/S3/S6 and T* expect a load,
// S4 and N* expect none, S5 is behaviour-only (n/a).
import { readFileSync } from 'node:fs'

const [mapFile, resultsDir] = process.argv.slice(2)
const rows = readFileSync(mapFile, 'utf8')
  .split('\n')
  .filter((line) => line.trim())
  .map((line) => {
    const [run, arm, scenario] = line.split('\t')
    let evidence = {}
    try {
      evidence = JSON.parse(readFileSync(`${resultsDir}/runs/${run}.json`, 'utf8'))
    } catch {
      return [run, arm, scenario, '-', '-', '-', '-', 'no-evidence']
    }
    const expected = /^T\d+$/.test(scenario) || ['S1', 'S2', 'S3', 'S6'].includes(scenario)
      ? 'trigger'
      : /^N\d+$/.test(scenario) || scenario === 'S4'
        ? 'no_trigger'
        : 'n/a'
    const loaded = evidence.skill_loaded_calls > 0
    const verdict =
      expected === 'n/a'
        ? 'behaviour-only'
        : expected === 'trigger'
          ? loaded ? 'hit' : 'miss'
          : loaded ? 'false-trigger' : 'correct-skip'
    return [
      run,
      arm,
      scenario,
      expected,
      evidence.catalog_lists_skill,
      evidence.skill_loaded_calls,
      (evidence.sent_messages.join('\n\n') || evidence.final_text).length,
      verdict,
    ]
  })

console.log(['run', 'arm', 'scenario', 'expected', 'catalog', 'loads', 'output_chars', 'verdict'].join('\t'))
for (const row of rows) console.log(row.join('\t'))

const count = (pred) => rows.filter(pred).length
const enabled = rows.filter((r) => r[1] === 'enabled')
const hits = enabled.filter((r) => r[7] === 'hit').length
const misses = enabled.filter((r) => r[7] === 'miss').length
const falseTriggers = enabled.filter((r) => r[7] === 'false-trigger').length
const correctSkips = enabled.filter((r) => r[7] === 'correct-skip').length

console.error(`\nrows=${rows.length}`)
console.error(`should-trigger: ${hits}/${hits + misses}`)
console.error(`should-skip:    ${correctSkips}/${correctSkips + falseTriggers}`)
console.error(`misses=${misses} false_triggers=${falseTriggers} no_evidence=${count((r) => r[7] === 'no-evidence')}`)
