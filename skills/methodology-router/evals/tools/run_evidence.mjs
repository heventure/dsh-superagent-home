#!/usr/bin/env node
// Harness evidence for one eval run, read from the session transcript (not model self-report).
// usage: node run_evidence.mjs <session.v4.jsonl.zstd>
// Prints JSON: catalog_lists_skill (the skill appeared in the system message's skill catalog),
// skill_loaded_calls (recorded `skill` tool calls naming methodology-router), final_text (last assistant text),
// sent_messages (texts the run sent with send_message, where it reported its answer).
import { readFileSync } from 'node:fs'
import { zstdDecompressSync } from 'node:zlib'

const file = process.argv[2]
const raw = readFileSync(file)
const text = (file.endsWith('zstd') ? zstdDecompressSync(raw) : raw).toString('utf8')
const events = text.split('\n').filter(Boolean).map((line) => JSON.parse(line))

const skill = 'methodology-router'
const catalog = events.some((e) => e.type === 'system/message' && JSON.stringify(e.data).includes(skill))
const loads = events.filter(
  (e) => e.type === 'tool/call' && e.data.name === 'skill' && String(e.data.arguments).includes(skill),
).length
let finalText = ''
for (const e of events) {
  if (e.type !== 'assistant/message') continue
  const parts = e.data.message.content.filter((c) => c.type === 'text').map((c) => c.text)
  if (parts.length) finalText = parts.join('\n')
}
const sent = events
  .filter((e) => e.type === 'tool/call' && e.data.name === 'send_message')
  .map((e) => JSON.parse(e.data.arguments).message)
console.log(JSON.stringify({ catalog_lists_skill: catalog, skill_loaded_calls: loads, final_text: finalText, sent_messages: sent }, null, 2))
