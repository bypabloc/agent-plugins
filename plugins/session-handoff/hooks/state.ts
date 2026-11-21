/**
 * Per-session state outside Claude Code (spec 001 · 03 §4): each hook is a new process in Codex and Antigravity, so
 * what the mod keeps in atoms lives in `tmp/handoff/.state/<session>.json` of the main checkout.
 */
import type { StopState } from './handoff'
import { handoffDir, type Io } from './store'

export type SessionState = {
  v: 1
  session: string
  host: string
  /** HEAD when the session started: Antigravity finds the session's commits from here (no PostToolUse output). */
  headAtStart: string | null
  lastStop: StopState | null
  /** Idempotence: Codex may deliver the same Stop twice (H-02); the same turn gets the same answer. */
  lastStopTurn: string | null
  lastStopOutcome: string | null
  /** When the last Stop of `lastStopTurn` was evaluated: a Stop of the same turn after this window is evaluated again. */
  lastStopAt: number | null
  pendingCommits: string[]
  /** OpenCode: the next injection says the conversation was compacted. */
  compacted: boolean
  updatedAt: number
}

const SAFE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/

export const stateDir = (store: string): string => `${handoffDir(store)}/.state`

export const emptyState = (session: string, host: string): SessionState => ({
  v: 1, session, host, headAtStart: null, lastStop: null, lastStopTurn: null, lastStopOutcome: null, lastStopAt: null,
  pendingCommits: [], compacted: false, updatedAt: 0,
})

export async function loadState(io: Io, store: string, session: string, host: string): Promise<SessionState> {
  if (!SAFE.test(session)) return emptyState(session, host)
  const text = await io.read(`${stateDir(store)}/${session}.json`)
  if (!text) return emptyState(session, host)
  try {
    const data = JSON.parse(text) as Partial<SessionState>
    return data.v === 1 ? { ...emptyState(session, host), ...data } : emptyState(session, host)
  } catch {
    return emptyState(session, host) // a corrupt file starts over (logged by the caller as state.reset)
  }
}

/** Rereads and merges field by field before writing: Codex runs hooks in parallel and each writes its own fields. */
export async function saveState(io: Io, store: string, state: SessionState, now = Date.now()): Promise<void> {
  if (!SAFE.test(state.session)) return
  try {
    const current = await loadState(io, store, state.session, state.host)
    await io.write(`${stateDir(store)}/${state.session}.json`, JSON.stringify({ ...current, ...state, updatedAt: now }))
  } catch {
    // Without state the hook still answers; it only forgets counters.
  }
}
