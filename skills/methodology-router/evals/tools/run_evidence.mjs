#!/usr/bin/env node
// Harness evidence for one eval run, read from the recorded session transcript —
// not from model self-report.
//
// usage: node run_evidence.mjs <session.v4.jsonl.zstd>
//
// output JSON:
//   session_id, model, started_at, finished (session reached turn/end)
//   prompt               first user message of the session, as recorded
//   read_eval_materials  tool calls that touched the eval materials or the ticket checkout
//   catalog_lists_skill  the skill appeared in an injected <available_skills> catalog
//   skill_loaded_calls   recorded `skill` tool calls that named the skill
//   final_text           last assistant text of the session
//   sent_messages        texts the session sent with send_message (its reported answer)
import { readFileSync } from 'node:fs'
import { zstdDecompressSync } from 'node:zlib'

const SKILL = 'methodology-router'
const file = process.argv[2]
const raw = readFileSync(file)
const text = (file.endsWith('zstd') ? zstdDecompressSync(raw) : raw).toString('utf8')
const events = text.split('\n').filter(Boolean).map((line) => JSON.parse(line))

// The catalog is delivered as a system-reminder user message; a changed catalog is
// re-sent the same way, so any event carrying the block counts.
const catalog = events.some((e) => {
  const s = JSON.stringify(e.data ?? {})
  return s.includes('available_skills') && s.includes(`\`${SKILL}\``)
})
const loads = events.filter(
  (e) => e.type === 'tool/call' && e.data.name === 'skill' && String(e.data.arguments).includes(SKILL),
).length
let finalText = ''
for (const e of events) {
  if (e.type !== 'assistant/message') continue
  const parts = (e.data.message.content ?? []).filter((c) => c.type === 'text').map((c) => c.text)
  if (parts.length) finalText = parts.join('\n')
}
const sent = events
  .filter((e) => e.type === 'tool/call' && e.data.name === 'send_message')
  .map((e) => JSON.parse(e.data.arguments).message)

const textOf = (e) => (e.data.content ?? []).map((c) => c.text ?? '').join('')
const firstUser = events.find((e) => {
  if (e.type !== 'user/message') return false
  const t = textOf(e)
  return !t.startsWith('<system-reminder') && !t.startsWith('The working directory changed')
})
const cleanPrompt = firstUser ? textOf(firstUser).split('Your parent agent id is')[0] : null
const EVAL_PATHS = /rubric\.md|scenarios\.md|trigger_set|prompts\.jsonl|holdout|evals\/|results\/v\d|methodology-router-skill/
const readEval = events
  .filter((e) => e.type === 'tool/call' && e.data.name !== 'send_message' && EVAL_PATHS.test(String(e.data.arguments)))
  .map((e) => `${e.data.name}: ${String(e.data.arguments).slice(0, 160)}`)

const head = events.find((e) => e.type === 'session')
const descriptor = events.find((e) => e.type === 'subagent/descriptor')

console.log(
  JSON.stringify(
    {
      session_id: head?.id ?? null,
      model: descriptor?.data?.agentModel ?? null,
      started_at: head ? new Date(head.createdAt).toISOString() : null,
      finished: events.some((e) => e.type === 'turn/end'),
      prompt: cleanPrompt,
      read_eval_materials: readEval,
      catalog_lists_skill: catalog,
      skill_loaded_calls: loads,
      final_text: finalText,
      sent_messages: sent,
    },
    null,
    2,
  ),
)
