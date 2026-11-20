// Sonda de OpenCode V2 (spec 001 · F1): registra la forma de ctx y de cada evento, sin mutar nada.
import fs from 'node:fs'
import path from 'node:path'

let n = 0
function shape(value: unknown, depth = 0): unknown {
  if (value === null || typeof value !== 'object') return typeof value === 'function' ? '[function]' : value
  if (depth > 4) return '[…]'
  if (Array.isArray(value)) return value.slice(0, 4).map(v => shape(v, depth + 1))
  const out: Record<string, unknown> = {}
  for (const key of Object.keys(value as object).slice(0, 60)) {
    let v: unknown
    try {
      v = (value as Record<string, unknown>)[key]
    } catch {
      v = '[getter error]'
    }
    out[key] = typeof v === 'string' && v.length > 1500 ? v.slice(0, 1500) + '…' : shape(v, depth + 1)
  }
  return out
}

export default {
  id: 'bypabloc.probe',
  async setup(ctx: any) {
    const base = ctx?.location?.directory ?? process.cwd()
    const dir = path.join(base, 'tmp', 'probe', 'opencode')
    fs.mkdirSync(dir, { recursive: true })
    const dump = (name: string, data: unknown) => {
      try {
        fs.writeFileSync(path.join(dir, `${name}-${Date.now()}-${n++}.json`), JSON.stringify(shape(data), null, 2))
      } catch {}
    }
    dump('ctx', ctx)
    const tries: Array<[string, () => unknown]> = [
      ['tool.execute.before', () => ctx.tool.hook('execute.before', (ev: unknown) => dump('tool-before', ev))],
      ['tool.execute.after', () => ctx.tool.hook('execute.after', (ev: unknown) => dump('tool-after', ev))],
      ['session.context', () => ctx.session.hook('context', (ev: unknown) => dump('session-context', ev))],
      ['session.compaction', () => ctx.session.hook('compaction', (ev: unknown) => dump('session-compaction', ev))],
      ['session.prompt', () => ctx.session.hook('prompt', (ev: unknown) => dump('session-prompt', ev))],
      ['permission.evaluate', () => ctx.permission.hook('evaluate', (ev: unknown) => dump('permission-evaluate', ev))],
    ]
    const registered: Record<string, string> = {}
    for (const [name, fn] of tries) {
      try {
        fn()
        registered[name] = 'ok'
      } catch (e) {
        registered[name] = String(e)
      }
    }
    try {
      const sub = ctx.event.subscribe({})
      ;(async () => {
        for await (const ev of sub) dump(`event-${(ev as any)?.type ?? 'x'}`, ev)
      })().catch(e => dump('event-error', String(e)))
      registered['event.subscribe'] = 'ok'
    } catch (e) {
      registered['event.subscribe'] = String(e)
    }
    dump('registered', registered)
  },
}
