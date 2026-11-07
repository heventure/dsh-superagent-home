#!/usr/bin/env node
// Redact local identifiers from collected run evidence before it is committed to a
// public repository. Reads run-evidence JSON on stdin, writes redacted JSON.
//
// Redacted: DSH home (env DSH_HOME), eval scratch roots, account home, user name, host
// name, and the machine's CPU/GPU model. Nothing else is altered.
import { homedir, hostname, userInfo } from 'node:os'

const replacements = [
  [process.env.DSH_HOME, '<DSH_HOME>'],
  ['/tmp/mr-eval', '<SCRATCH>'],
  [process.env.EVAL_SCRATCH || '/tmp/wk', '<SCRATCH>'],
  [homedir(), '<ACCOUNT_HOME>'],
  [userInfo().username, '<ACCOUNT>'],
  [hostname(), '<HOST>'],
  ['Intel N150', '<HOST_CPU>'],
  ['Alder Lake-N', '<HOST_GPU>'],
].filter(([from]) => from && from.length > 2)

let input = ''
process.stdin.on('data', (d) => (input += d))
process.stdin.on('end', () => {
  let text = input
  for (const [from, to] of replacements) text = text.split(from).join(to)
  const leaks = text.match(/\/vol1\/[^\s"')]+/g)
  if (leaks) console.error(`redaction warning: ${[...new Set(leaks)].join(', ')}`)
  process.stdout.write(text)
})
