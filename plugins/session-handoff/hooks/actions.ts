/**
 * What register.tsx does on each event, for the hosts without Claude Code's mod API (spec 001 · 03 §6): Codex and
 * Antigravity through cli.ts, OpenCode in process. Same core, same texts; state in a file instead of atoms. No
 * metrics or UI here. register.tsx stays as it is (D-07).
 */
import {
  askDeniedText, badPhaseText, blockedForUser, boundMessage, commitDir, commitHash, isCommit, longText,
  missingHashes, pendingText, progressFields, stopDecision, tooLong, unboundMessage,
} from './handoff' // fmt: skip
import { loadState, saveState, type SessionState } from './state'
import {
  activeWorks, boundOf, configOf, currentWork, handoffDir, type Io, logEvent, type Place, placeOf, progressOf,
  specOf, takenOverBy,
} from './store' // fmt: skip
import { type Host, TERMS } from './terms'

export const PROGRESS_PATH = /(?:^|\/)tmp\/handoff\/[^/]+\/PROGRESS\.md$/
/** Codex trims additionalContext to ~2500 tokens and spills the rest to a temp file: the handoff stays within budget. */
export const CODEX_BUDGET = 8000
/** Antigravity's per-invocation reminder: an ephemeral message, so repeating it does not pile up tokens. */
export const REMINDER_MAX = 600

type Ctx = { io: Io; host: Host; session: string; cwd: string; now?: number }
type Here = { place: Place; state: SessionState }

async function here(c: Ctx): Promise<Here> {
  const place = await placeOf(c.io, c.cwd)
  return { place, state: await loadState(c.io, place.store, c.session, c.host) }
}

const writeTools = (host: Host): string => TERMS[host].writeTools

/** The handoff message of a session start (or a reinjection), within the host's budget. */
export async function sessionStart(c: Ctx & { source: string }): Promise<string | null> {
  const { place, state } = await here(c)
  if (c.source === 'startup' || state.headAtStart === null) {
    state.headAtStart = (await c.io.git(place.root, ['rev-parse', 'HEAD'])) || null
  }
  if (c.source === 'startup' || c.source === 'clear') state.lastStop = null
  await saveState(c.io, place.store, state, c.now)
  const text = await messageFor(c, place, c.source)
  if (!text) return null
  const compact = c.host === 'codex' && text.length > CODEX_BUDGET
  const out = compact ? await compactMessage(c, place) : text
  await logEvent(c.io, place.store, { event: compact ? 'inject.compact' : 'inject', host: c.host, session: c.session,
    source: c.source, chars: out.length }) // fmt: skip
  return out
}

export async function messageFor(c: Ctx, place: Place, source: string): Promise<string> {
  const config = await configOf(c.io, place.root)
  const work = await currentWork(c.io, place, c.session)
  if (work) return boundMessage(await boundOf(c.io, place, work, source, config), config, writeTools(c.host))
  return c.session
    ? unboundMessage(c.session, handoffDir(place.store), source, await activeWorks(c.io, place), config, writeTools(c.host))
    : ''
}

/** Status lines, next step and where to read the rest: what fits when the whole handoff does not. */
async function compactMessage(c: Ctx, place: Place): Promise<string> {
  const work = (await currentWork(c.io, place, c.session)) ?? ''
  const folder = `${handoffDir(place.store)}/${work}`
  const progress = await progressOf(c.io, place, work)
  const status = progress.split('\n').filter(l => /^(Status|Phase|Done|Current|Remaining|ETA|Next step):/.test(l))
  return [
    `[session-handoff] Trabajo ${work} · handoff en ${folder}/ (resumido: el completo no cabe en el contexto de Codex).`,
    ...status,
    `Lee ahora ${folder}/PROGRESS.md, DECISIONS.md y NOTES.md con tu herramienta de lectura antes de seguir; el disco manda.`,
  ].join('\n')
}

/** The commits of the session that PROGRESS.md does not name yet, after adding `extra`; updates the state. */
async function missingCommits(c: Ctx, h: Here, work: string, extra: string[]): Promise<string[]> {
  const missing = missingHashes([...h.state.pendingCommits, ...extra], await progressOf(c.io, h.place, work))
  h.state.pendingCommits = missing
  await saveState(c.io, h.place.store, h.state, c.now)
  return missing
}

/** UserPromptSubmit: the hashes still missing, so an interruption does not lose them. */
export async function prompt(c: Ctx): Promise<string | null> {
  const h = await here(c)
  const work = await currentWork(c.io, h.place, c.session)
  if (!work) return null
  return pendingText(work, await missingCommits(c, h, work, []))
}

export type PostTool = { tool: 'shell'; command: string; output: string } | { tool: 'write'; paths: string[] }

/** After a tool: a commit asks for its hash; a PROGRESS.md written too long or with a bad phase is named now. */
export async function postTool(c: Ctx & { event: PostTool }): Promise<string | null> {
  const h = await here(c)
  const work = await currentWork(c.io, h.place, c.session)
  if (c.event.tool === 'shell') {
    if (!work || !isCommit(c.event.command)) return null
    const sha = commitHash(c.event.output) ??
      ((await c.io.git(commitDir(c.event.command, c.cwd), ['log', '-1', '--format=%h'])) || null)
    const text = pendingText(work, await missingCommits(c, h, work, sha ? [sha] : []))
    if (text) await logEvent(c.io, h.place.store, { event: 'commit.remind', host: c.host, session: c.session, work })
    return text
  }
  const progress = c.event.paths.map(p => p.replace(/\\/g, '/')).find(p => PROGRESS_PATH.test(p))
  if (!progress) return null
  return progressNotes((await c.io.read(absolute(progress, c.cwd))) ?? '')
}

const absolute = (p: string, cwd: string): string => (/^([A-Za-z]:)?\//.test(p) ? p : `${cwd.replace(/\\/g, '/')}/${p}`)

function progressNotes(text: string): string | null {
  const long = tooLong(progressFields(text))
  return [long.length ? longText(long) : null, badPhaseText(text)].filter(Boolean).join('\n') || null
}

/** The question tool while a spec runs: denied unless PROGRESS.md carries one of the project's block reasons. */
export async function askQuestion(c: Ctx): Promise<string | null> {
  const { place } = await here(c)
  const work = await currentWork(c.io, place, c.session)
  if (!work) return null
  const config = await configOf(c.io, place.root)
  if (!(await specOf(c.io, place, work, config))) return null
  if (blockedForUser(progressFields(await progressOf(c.io, place, work)), config)) return null
  await logEvent(c.io, place.store, { event: 'ask.deny', host: c.host, session: c.session, work })
  return askDeniedText(config)
}

/**
 * The end of the turn: the same order as register.tsx (commit reminders, a newer session that took the work, then
 * stopDecision). `turn` makes a duplicated Stop answer the same. Antigravity has no PostToolUse output, so the
 * session's commits (since headAtStart) and the PROGRESS.md checks are done here.
 */
export async function stop(c: Ctx & { active: boolean; turn: string }): Promise<string | null> {
  const h = await here(c)
  if (c.turn && h.state.lastStopTurn === c.turn) return h.state.lastStopOutcome
  const answer = await stopAnswer(c, h)
  h.state.lastStopTurn = c.turn || null
  h.state.lastStopOutcome = answer
  await saveState(c.io, h.place.store, h.state, c.now)
  return answer
}

async function stopAnswer(c: Ctx & { active: boolean }, h: Here): Promise<string | null> {
  const work = await currentWork(c.io, h.place, c.session)
  if (!work) return null
  const progress = await progressOf(c.io, h.place, work)
  let notes: string | null = null
  let landed: string[] = []
  if (c.host === 'antigravity') {
    notes = progressNotes(progress)
    if (h.state.headAtStart) {
      const log = await c.io.git(h.place.root, ['log', '--first-parent', '--no-merges', '--format=%h', `${h.state.headAtStart}..HEAD`])
      landed = log.split('\n').map(s => s.trim()).filter(Boolean).reverse()
    }
  }
  const reminder = c.active ? null : pendingText(work, await missingCommits(c, h, work, landed))
  if (reminder || notes) {
    await logEvent(c.io, h.place.store, { event: 'stop.commits', host: c.host, session: c.session, work })
    return [notes, reminder].filter(Boolean).join('\n')
  }
  const owner = await takenOverBy(c.io, h.place, c.session, work)
  if (owner) {
    await logEvent(c.io, h.place.store, { event: 'stop.release', host: c.host, session: c.session, reason: 'handed-off', owner })
    return null
  }
  const config = await configOf(c.io, h.place.root)
  const now = c.now ?? Date.now()
  const decision = stopDecision(progress, h.state.lastStop, work, config, now)
  if ('release' in decision) {
    h.state.lastStop = decision.waits ? { text: progress, blocks: 0, waits: decision.waits } : null
    await logEvent(c.io, h.place.store, { event: 'stop.release', host: c.host, session: c.session, reason: decision.release })
    return null
  }
  h.state.lastStop = { text: progress, blocks: decision.blocks, waits: decision.waits, at: now }
  const event = decision.waits === 0 ? 'stop.recheck' : 'stop.block'
  await logEvent(c.io, h.place.store, { event, host: c.host, session: c.session, blocks: decision.blocks, work })
  return decision.block
}

/** Antigravity's PreInvocation: a short status reminder on every invocation after the first (covers compaction). */
export async function reminder(c: Ctx & { invocation: number }): Promise<string | null> {
  if (c.invocation <= 0) return null
  const h = await here(c)
  const work = await currentWork(c.io, h.place, c.session)
  if (!work) return null
  const f = progressFields(await progressOf(c.io, h.place, work))
  const pending = pendingText(work, missingHashes(h.state.pendingCommits, await progressOf(c.io, h.place, work)))
  const text = [`[session-handoff] Trabajo ${work}: Status ${f.status ?? '?'} · Phase ${f.phase ?? '?'} · Next step: ` +
    `${f.next_step ?? '?'} (${handoffDir(h.place.store)}/${work}/PROGRESS.md).`, pending].filter(Boolean).join(' ') // fmt: skip
  return text.slice(0, REMINDER_MAX)
}
