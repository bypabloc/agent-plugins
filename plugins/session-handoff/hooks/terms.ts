/** What each host calls its tools, for the texts the core writes (spec 001 · 03 §5). Claude's are the core's default. */
export type Host = 'codex' | 'antigravity' | 'opencode'

export type Terms = { writeTools: string; askTool: string }

export const TERMS: Record<'claude' | Host, Terms> = {
  claude: { writeTools: 'Write o Edit', askTool: 'AskUserQuestion' },
  codex: { writeTools: 'apply_patch', askTool: 'request_user_input' },
  antigravity: { writeTools: 'write_file o edit_file', askTool: 'ask_question' },
  opencode: { writeTools: 'write, edit o patch', askTool: 'question' },
}
