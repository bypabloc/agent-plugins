// @ts-nocheck — corre en Bun (bun:test, node:fs), no en el motor de mods que tipa `claude plugin validate`
// Acciones y emisión para Codex y Antigravity (spec 001 · 04 §3.2). Corre con: bun test tests/cli
// (los tests de register.tsx usan claude-code/testing y corren con `claude plugin test .`).
import { describe, expect, test } from 'bun:test'
import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

import * as actions from '../../hooks/actions'
import { emit, handle, patchPaths } from '../../hooks/hosts'
import type { Io } from '../../hooks/store'

const ROOT = '/r'
const SESSION = 's1'
const PENDING = 'Status: in-progress\nPhase: implementation\nNext step: commit group 2\n'

function memoryIo(files: Record<string, string>, git: Record<string, string> = {}, mtimes: Record<string, number> = {}): Io {
  return {
    read: async p => files[p] ?? null,
    write: async (p, t) => {
      files[p] = t
    },
    list: async dir => {
      const names = new Map<string, string>()
      for (const p of Object.keys(files)) {
        if (!p.startsWith(`${dir}/`)) continue
        const rest = p.slice(dir.length + 1).split('/')
        names.set(rest[0]!, rest.length > 1 ? 'dir' : 'file')
      }
      if (!names.size) throw new Error(`ENOENT ${dir}`)
      return [...names].map(([name, kind]) => ({ name, kind, mtimeMs: mtimes[`${dir}/${name}`] }))
    },
    git: async (_cwd, args) => git[args.join(' ')] ?? (args[0] === 'rev-parse' && args[1] === '--show-toplevel' ? ROOT : ''),
  }
}

function boundWorld(progress = PENDING, extra: Record<string, string> = {}): Record<string, string> {
  return {
    [`${ROOT}/tmp/handoff/012-x/PROGRESS.md`]: progress,
    [`${ROOT}/tmp/handoff/.sessions/${SESSION}`]: '012-x\n',
    ...extra,
  }
}

const ctx = (io: Io, host: 'codex' | 'antigravity' = 'codex') => ({ io, host, session: SESSION, cwd: ROOT })

describe('stop', () => {
  test('blocks while the next step is pending, answers a duplicated Stop the same, and releases after the cap', async () => {
    const io = memoryIo(boundWorld())
    const first = await actions.stop({ ...ctx(io), active: false, turn: 't1', now: 1_000_000 })
    expect(first).toContain('[session-handoff] El trabajo 012-x no terminó')
    expect(await actions.stop({ ...ctx(io), active: false, turn: 't1', now: 1_000_000 })).toBe(first)
    expect(await actions.stop({ ...ctx(io), active: false, turn: 't2', now: 2_000_000 })).toContain('Segunda parada')
    expect(await actions.stop({ ...ctx(io), active: false, turn: 't3', now: 3_000_000 })).toContain('Último aviso')
    expect(await actions.stop({ ...ctx(io), active: false, turn: 't4', now: 4_000_000 })).toBeNull()
  })

  test('done or unbound releases', async () => {
    expect(await actions.stop({ ...ctx(memoryIo(boundWorld('Status: done\n'))), active: false, turn: 't' })).toBeNull()
    expect(await actions.stop({ ...ctx(memoryIo({})), active: false, turn: 't' })).toBeNull()
  })

  test('a newer session that took the work releases this one', async () => {
    const files = boundWorld(PENDING, { [`${ROOT}/tmp/handoff/.sessions/s2`]: '012-x\n' })
    const mtimes = { [`${ROOT}/tmp/handoff/.sessions/${SESSION}`]: 1, [`${ROOT}/tmp/handoff/.sessions/s2`]: 2 }
    expect(await actions.stop({ ...ctx(memoryIo(files, {}, mtimes)), active: false, turn: 't' })).toBeNull()
  })

  test('antigravity: the commits since the session started are asked for at Stop', async () => {
    const io = memoryIo(boundWorld(), { 'rev-parse HEAD': 'base1', 'log --first-parent --no-merges --format=%h base1..HEAD': 'abc1234' })
    await actions.sessionStart({ ...ctx(io, 'antigravity'), source: 'startup' })
    const text = await actions.stop({ ...ctx(io, 'antigravity'), active: false, turn: '' })
    expect(text).toContain('abc1234')
  })
})

describe('commits, prompt and PROGRESS.md', () => {
  test('a commit asks for its hash until PROGRESS.md names it', async () => {
    const files = boundWorld()
    const io = memoryIo(files)
    const text = await actions.postTool({ ...ctx(io), event: { tool: 'shell', command: 'git commit -m x', output: '[main abc1234] x\n 1 file changed' } })
    expect(text).toContain('abc1234')
    expect(await actions.prompt(ctx(io))).toContain('abc1234')
    files[`${ROOT}/tmp/handoff/012-x/PROGRESS.md`] = `${PENDING}Done: abc1234\n`
    expect(await actions.prompt(ctx(io))).toBeNull()
  })

  test('a PROGRESS.md written through apply_patch with a long status line is named', async () => {
    const files = boundWorld(`${PENDING}Current: ${'x'.repeat(200)}\n`)
    const text = await actions.postTool({ ...ctx(memoryIo(files)), event: { tool: 'write', paths: ['tmp/handoff/012-x/PROGRESS.md'] } })
    expect(text).toContain('Current')
  })

  test('patch paths', () => {
    expect(patchPaths('*** Begin Patch\n*** Add File: a.md\n+x\n*** Update File: b.md\n*** Move to: c.md\n*** End Patch'))
      .toEqual(['a.md', 'b.md', 'c.md'])
  })
})

describe('question tool and session start', () => {
  test('the question is denied while a spec runs', async () => {
    const io = memoryIo(boundWorld(PENDING, { [`${ROOT}/docs/specs/012-x/README.md`]: '# spec' }))
    expect(await actions.askQuestion(ctx(io))).toContain('Con una spec en ejecución')
    expect(await actions.askQuestion(ctx(memoryIo(boundWorld())))).toBeNull()
  })

  test('codex gets a compact handoff when the whole one does not fit', async () => {
    const io = memoryIo(boundWorld(PENDING, { [`${ROOT}/tmp/handoff/012-x/NOTES.md`]: 'n'.repeat(20_000) }))
    const text = (await actions.sessionStart({ ...ctx(io), source: 'startup' }))!
    expect(text.length).toBeLessThanOrEqual(actions.CODEX_BUDGET)
    expect(text).toContain('Lee ahora')
  })

  test('the write tools are named per host', async () => {
    const io = memoryIo(boundWorld())
    expect(await actions.sessionStart({ ...ctx(io), source: 'startup' })).toContain('apply_patch')
    expect(await actions.sessionStart({ ...ctx(io, 'antigravity'), source: 'startup' })).toContain('write_file o edit_file')
  })

  test('antigravity reminds on every invocation after the first, within its budget', async () => {
    const io = memoryIo(boundWorld())
    expect(await actions.reminder({ ...ctx(io, 'antigravity'), invocation: 0 })).toBeNull()
    const text = (await actions.reminder({ ...ctx(io, 'antigravity'), invocation: 3 }))!
    expect(text).toContain('commit group 2')
    expect(text.length).toBeLessThanOrEqual(actions.REMINDER_MAX)
  })
})

describe('emission contracts (H-01)', () => {
  test('codex', () => {
    expect(JSON.parse(emit('codex', 'stop', null))).toEqual({})
    expect(Object.keys(JSON.parse(emit('codex', 'stop', 'x')))).toEqual(['decision', 'reason'])
    expect(emit('codex', 'prompt', null)).toBe('')
    expect(Object.keys(JSON.parse(emit('codex', 'post-tool', 'x')).hookSpecificOutput)).toEqual(['hookEventName', 'additionalContext'])
    expect(JSON.parse(emit('codex', 'ask-question', 'x')).hookSpecificOutput.permissionDecision).toBe('deny')
  })

  test('antigravity', () => {
    expect(JSON.parse(emit('antigravity', 'stop', 'x'))).toEqual({ decision: 'continue', reason: 'x' })
    expect(JSON.parse(emit('antigravity', 'ask-question', null))).toEqual({ decision: 'allow' })
    expect(JSON.parse(emit('antigravity', 'session-start', 'x'))).toEqual({ injectSteps: [{ systemMessage: 'x' }] })
  })
})

describe('real fixtures', () => {
  const dir = path.join(import.meta.dir, '..', 'fixtures')
  const cases: Array<[string, 'codex' | 'antigravity', string]> = []
  for (const host of ['codex', 'antigravity'] as const) {
    for (const os of readdirSync(path.join(dir, host))) {
      for (const version of readdirSync(path.join(dir, host, os))) {
        for (const file of readdirSync(path.join(dir, host, os, version))) cases.push([path.join(dir, host, os, version, file), host, file])
      }
    }
  }
  const eventOf = (file: string) =>
    file.startsWith('SessionStart') ? 'session-start' : file.startsWith('Stop') ? 'stop' : file.startsWith('UserPromptSubmit')
      ? 'prompt' : file.startsWith('PostToolUse') ? 'post-tool' : file.startsWith('PreInvocation') ? 'pre-invocation' : 'ask-question' // fmt: skip

  for (const [file, host, name] of cases) {
    test(`${host} ${name}`, async () => {
      const raw = JSON.parse(readFileSync(file, 'utf8')).stdin
      const out = await handle(host, eventOf(name) as never, raw, memoryIo({}))
      if (out) expect(() => JSON.parse(out)).not.toThrow()
      if (host === 'codex' && name.startsWith('Stop')) expect(out).not.toBe('')
    })
  }
})
