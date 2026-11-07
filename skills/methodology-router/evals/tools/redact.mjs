#!/usr/bin/env node
// Redact local identifiers from collected run evidence before it is committed to a
// public repository. Reads a run-evidence JSON on stdin, writes redacted JSON.
//
// Redacted: account home, DSH home, ticket work directory, scratch directories,
// user name, host name. Nothing is removed except those identifiers.
import { homedir, hostname } from 'node:os'

const replacements = [
  [/\/vol1\/@appshare\/fn-deepseek-harness/g, '<ACCOUNT_HOME>'],
  [/\/vol1\/@apphome\/fn-deepseek-harness/g, '<DSH_HOME>'],
  [/\/tmp\/mr-eval/g, '<SCRATCH>'],
]
const user = process.env.USER || ''
const host = hostname()

let input = ''
process.stdin.on('data', (d) => (input += d))
process.stdin.on('end', () => {
  let text = input
  for (const [re, to] of replacements) text = text.replace(re, to)
  if (user) text = text.split(user).join('<ACCOUNT>')
  if (host) text = text.split(host).join('<HOST>')
  // basic sanity: no unredacted home-style paths left
  const leaks = text.match(/\/vol1\/[^\s"')]+/g)
  if (leaks) {
    console.error(`redaction warning: ${[...new Set(leaks)].join(', ')}`)
  }
  process.stdout.write(text)
})
