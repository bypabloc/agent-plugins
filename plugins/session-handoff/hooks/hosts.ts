/**
 * Codex and Antigravity: from the hook's stdin to an action, and from the action's text to the host's output
 * (spec 001 · 03 §6). Only the keys each host accepts: Codex and agy reject unknown output fields (H-01).
 */
import * as actions from './actions'
import type { Io } from './store'

export type SubprocessHost = 'codex' | 'antigravity'
export type HostEvent = 'session-start' | 'prompt' | 'post-tool' | 'stop' | 'ask-question' | 'pre-invocation'

type Raw = Record<string, unknown>
const str = (v: unknown): string => (typeof v === 'string' ? v : '')

/** Paths an apply_patch / patchText touches (Add, Update, Move to, Delete). */
export function patchPaths(text: string): string[] {
  return [...text.matchAll(/^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$/gm)].map(m => m[1]!.trim())
}

export async function handle(host: SubprocessHost, event: HostEvent, raw: Raw, io: Io): Promise<string> {
  const base = host === 'codex'
    ? { io, host, session: str(raw.session_id), cwd: str(raw.cwd) }
    : { io, host, session: str(raw.conversationId), cwd: str(raw.cwd) || str((raw.workspacePaths as unknown[])?.[0]) } // fmt: skip
  const subagent = host === 'codex' && Boolean(raw.agent_id)
  switch (event) {
    case 'session-start': {
      const source = host === 'codex' ? str(raw.source) || 'startup' : 'startup'
      return emit(host, event, await actions.sessionStart({ ...base, source }))
    }
    case 'prompt':
      return emit(host, event, subagent ? null : await actions.prompt(base))
    case 'post-tool': {
      const tool = str(raw.tool_name)
      const input = (raw.tool_input ?? {}) as Raw
      const post: actions.PostTool | null = tool === 'Bash'
        ? { tool: 'shell', command: str(input.command), output: str(raw.tool_response) }
        : tool === 'apply_patch' ? { tool: 'write', paths: patchPaths(str(input.command)) } : null // fmt: skip
      return emit(host, event, post ? await actions.postTool({ ...base, event: post }) : null)
    }
    case 'stop': {
      if (subagent) return emit(host, event, null)
      const active = host === 'codex' ? raw.stop_hook_active === true : raw.continuationActive === true
      const turn = host === 'codex' ? str(raw.turn_id) : `${str(raw.executionNum)}`
      return emit(host, event, await actions.stop({ ...base, active, turn: host === 'codex' ? turn : '' }))
    }
    case 'ask-question':
      return emit(host, event, await actions.askQuestion(base))
    case 'pre-invocation':
      return emit(host, event, await actions.reminder({ ...base, invocation: Number(raw.invocationNum ?? 0) }))
  }
}

const HOOK_EVENT: Record<string, string> = { 'session-start': 'SessionStart', prompt: 'UserPromptSubmit', 'post-tool': 'PostToolUse' }

export function emit(host: SubprocessHost, event: HostEvent, text: string | null): string {
  if (host === 'codex') {
    if (event === 'stop') return JSON.stringify(text ? { decision: 'block', reason: text } : {}) // Stop exige JSON
    if (event === 'ask-question') {
      return text
        ? JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny', permissionDecisionReason: text } })
        : ''
    }
    // PostToolUse con decision:block reemplazaría la salida del tool: los avisos van como contexto
    return text ? JSON.stringify({ hookSpecificOutput: { hookEventName: HOOK_EVENT[event], additionalContext: text } }) : ''
  }
  if (event === 'stop') return JSON.stringify(text ? { decision: 'continue', reason: text } : {})
  if (event === 'ask-question') return JSON.stringify(text ? { decision: 'deny', reason: text } : { decision: 'allow' })
  if (event === 'session-start') return JSON.stringify(text ? { injectSteps: [{ systemMessage: text }] } : {})
  if (event === 'pre-invocation') return JSON.stringify(text ? { injectSteps: [{ ephemeralMessage: text }] } : {})
  return '{}'
}

/** What a host gets when something fails: nothing that blocks (session-handoff is not a guardrail). */
export function neutral(host: SubprocessHost, event: HostEvent): string {
  return emit(host, event, null)
}
