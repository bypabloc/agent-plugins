// session-handoff para OpenCode V2 (spec 001 · 03 §6.3): en proceso, con el mismo núcleo que Codex y Antigravity.
//   context            → el handoff en el system prompt (texto estable mientras el disco no cambie) y los hashes pendientes
//   compaction         → marca la sesión como compactada: la próxima inyección lo dice (compactación nativa, V-24)
//   execute.before     → la tool question se rechaza con una spec en curso
//   execute.after      → commits (hash pendiente) y PROGRESS.md (líneas largas, fase inválida)
//   session.execution.succeeded → fin del turno: si el trabajo sigue, se reinyecta el siguiente paso (V-25)
import * as actions from '../../hooks/actions'
import { patchPaths } from '../../hooks/hosts'
import { nodeIo } from '../../cli/io-node'
import { loadState, saveState } from '../../hooks/state'
import { logEvent, placeOf } from '../../hooks/store'

type Ev = Record<string, any>

export default {
  id: 'bypabloc.session-handoff',
  async setup(ctx: any) {
    const cwd: string = ctx?.location?.directory ?? process.cwd()
    const base = (session: string) => ({ io: nodeIo, host: 'opencode' as const, session, cwd })
    const started = new Set<string>()

    ctx.session.hook('context', async (ev: Ev) => {
      const session = String(ev.sessionID ?? '')
      if (!session || !Array.isArray(ev.system)) return
      const place = await placeOf(nodeIo, cwd)
      const state = await loadState(nodeIo, place.store, session, 'opencode')
      const source = state.compacted ? 'compact' : 'startup'
      // La primera vez por sesión registra el inicio (HEAD, log); después solo reconstruye el texto
      const text = started.has(session) && !state.compacted
        ? await actions.messageFor(base(session), place, source)
        : await actions.sessionStart({ ...base(session), source })
      started.add(session)
      if (state.compacted) await saveState(nodeIo, place.store, { ...(await loadState(nodeIo, place.store, session, 'opencode')), compacted: false })
      const pending = await actions.prompt(base(session))
      for (const part of [text, pending]) if (part) ev.system.push({ type: 'text', text: part })
    })

    ctx.session.hook('compaction', async (ev: Ev) => {
      const session = String(ev.sessionID ?? '')
      if (!session) return
      const place = await placeOf(nodeIo, cwd)
      await saveState(nodeIo, place.store, { ...(await loadState(nodeIo, place.store, session, 'opencode')), compacted: true })
      await logEvent(nodeIo, place.store, { event: 'compact.native', host: 'opencode', session })
    })

    ctx.tool.hook('execute.before', async (ev: Ev) => {
      if (ev.tool !== 'question') return
      const text = await actions.askQuestion(base(String(ev.sessionID ?? '')))
      if (text) throw new Error(text)
    })

    ctx.tool.hook('execute.after', async (ev: Ev) => {
      const input = (ev.input ?? {}) as Ev
      const post: actions.PostTool | null =
        ev.tool === 'shell' || ev.tool === 'bash'
          ? { tool: 'shell', command: String(input.command ?? ''), output: String(ev.result?.output?.output ?? '') }
          : ev.tool === 'write' || ev.tool === 'edit'
            ? { tool: 'write', paths: [String(input.path ?? input.filePath ?? '')] }
            : ev.tool === 'patch'
              ? { tool: 'write', paths: patchPaths(String(input.patchText ?? '')) }
              : null
      if (!post) return
      const text = await actions.postTool({ ...base(String(ev.sessionID ?? '')), event: post })
      if (text && Array.isArray(ev.result?.content)) ev.result.content.push({ type: 'text', text })
    })

    const continueSession = async (session: string, text: string) => {
      const place = await placeOf(nodeIo, cwd)
      const attempts: Array<[string, () => unknown]> = [
        ['prompt.text', () => ctx.session.prompt({ sessionID: session, prompt: { text } })],
        ['text', () => ctx.session.prompt({ sessionID: session, text })],
      ]
      const errors: string[] = []
      for (const [shape, call] of attempts) {
        try {
          await call()
          await logEvent(nodeIo, place.store, { event: 'stop.continue', host: 'opencode', session, shape })
          return
        } catch (e) {
          errors.push(`${shape}: ${String(e).slice(0, 160)}`)
        }
      }
      await logEvent(nodeIo, place.store, { event: 'stop.continue_failed', host: 'opencode', session, errors })
    }

    ;(async () => {
      for await (const ev of ctx.event.subscribe({ types: ['session.execution.succeeded'] }) as AsyncIterable<Ev>) {
        if (ev?.type !== 'session.execution.succeeded') continue
        const session = String(ev.data?.sessionID ?? '')
        if (!session) continue
        try {
          const text = await actions.stop({ ...base(session), active: false, turn: '' })
          if (text) await continueSession(session, text)
        } catch {
          // Un fallo del handoff nunca rompe la sesión
        }
      }
    })().catch(() => {})
  },
}
