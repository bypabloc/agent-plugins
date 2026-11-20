/**
 * session-handoff for Codex and Antigravity: `node dist/hook.mjs <codex|antigravity> <event>` with the hook's JSON
 * on stdin (spec 001 · 03, D-08). Always exits 0; on any error it answers neutrally (Codex's Stop still gets JSON).
 *   node dist/hook.mjs doctor    Node version, bundle, bound work of the cwd and the last events
 */
import { readFileSync } from 'node:fs'

import { VERSION } from './handoff'
import { handle, type HostEvent, neutral, type SubprocessHost } from './hosts'
import { nodeIo } from './io-node'
import { currentWork, handoffDir, placeOf } from './store'

const HOSTS: SubprocessHost[] = ['codex', 'antigravity']
const EVENTS: HostEvent[] = ['session-start', 'prompt', 'post-tool', 'stop', 'ask-question', 'pre-invocation']
const MIN_NODE = 20

async function doctor(): Promise<void> {
  const major = Number(process.versions.node.split('.')[0])
  console.log(`${major >= MIN_NODE ? '✓' : '✗'} Node ${process.versions.node} (mínimo ${MIN_NODE})`)
  console.log(`✓ session-handoff ${VERSION}`)
  const place = await placeOf(nodeIo, process.cwd())
  const session = process.argv[3] ?? ''
  const work = session ? await currentWork(nodeIo, place, session) : null
  console.log(`  handoff: ${handoffDir(place.store)}${session ? ` · sesión ${session}: ${work ?? 'sin trabajo vinculado'}` : ''}`)
  const log = (await nodeIo.read(`${handoffDir(place.store)}/.log/events.jsonl`)) ?? ''
  const last = new Map<string, string>()
  for (const line of log.trim().split('\n').filter(Boolean)) {
    try {
      const e = JSON.parse(line) as { event?: string; ts?: string; host?: string }
      if (e.event) last.set(e.event, `${e.ts ?? ''} ${e.host ?? 'claude'}`)
    } catch {}
  }
  for (const [event, when] of last) console.log(`  último ${event}: ${when}`)
}

async function main(): Promise<number> {
  const [host, event] = process.argv.slice(2) as [SubprocessHost, HostEvent]
  if ((host as string) === 'doctor') {
    await doctor()
    return 0
  }
  if (!HOSTS.includes(host) || !EVENTS.includes(event)) {
    process.stderr.write(`uso: hook.mjs <${HOSTS.join('|')}> <${EVENTS.join('|')}>\n`)
    return 0
  }
  let out: string
  try {
    if (Number(process.versions.node.split('.')[0]) < MIN_NODE) throw new Error(`Node ${process.versions.node}`)
    const text = readFileSync(0, 'utf8')
    out = await handle(host, event, text.trim() ? JSON.parse(text) : {}, nodeIo)
  } catch {
    out = neutral(host, event)
  }
  if (out) process.stdout.write(out)
  return 0
}

main().then(code => process.exit(code), () => process.exit(0))
