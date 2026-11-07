#!/usr/bin/env node
// Redact local identifiers from collected run evidence before it is committed to a
// public repository. Reads run-evidence JSON on stdin, writes redacted JSON.
//
// Redacted: account home, DSH home (env DSH_HOME), eval scratch root (env EVAL_SCRATCH),
// user name, host name. Nothing else is altered.
import { homedir, hostname, userInfo } from 'node:os'

const replacements = [
  [process.env.DSH_HOME, '<DSH_HOME>'],
  [process.env.EVAL_SCRATCH || '/tmp/mr-eval', '<SCRATCH>'],
  [homedir(), '<ACCOUNT_HOME>'],
  [userInfo().username, '<ACCOUNT>'],
  [hostname(), '<HOST>'],
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
