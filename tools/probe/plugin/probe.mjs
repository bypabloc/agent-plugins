#!/usr/bin/env node
// Sonda de payloads (spec 001 · 04 §2): guarda stdin y entorno filtrado de cada hook y responde neutro.
// Uso: node probe.mjs <host> <evento>. Escribe en <cwd del payload>/tmp/probe/<host>/<evento>-<n>.json.
import fs from 'node:fs'
import path from 'node:path'

const [host = 'unknown', event = 'unknown'] = process.argv.slice(2)
// Nombres que se registran; solo los de VALUE_KEEP guardan su valor (nunca tokens ni secretos heredados)
const ENV_KEEP = /^(PLUGIN_|CLAUDE_|CODEX_|GEMINI_|ANTIGRAVITY_|OPENCODE_|XDG_)|^(PWD|SHELL|COMSPEC|PATHEXT|TERM)$/
const VALUE_KEEP = /^(PLUGIN_ROOT|PLUGIN_DATA|CLAUDE_PLUGIN_ROOT|CLAUDE_PLUGIN_DATA|CODEX_HOME|PWD|SHELL|COMSPEC|PATHEXT|TERM)$/

let raw = ''
try {
  raw = fs.readFileSync(0, 'utf8')
} catch {}
let stdin
try {
  stdin = raw.trim() ? JSON.parse(raw) : null
} catch {
  stdin = { unparsed: raw.slice(0, 4000) }
}

const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => ENV_KEEP.test(k))
  .map(([k, v]) => [k, VALUE_KEEP.test(k) ? v : '<set>']))
const base = stdin?.cwd || stdin?.workspacePaths?.[0] || process.env.PROBE_DIR || process.cwd()
const tool = stdin?.tool_name || stdin?.toolCall?.name || ''
const dir = path.join(base, 'tmp', 'probe', host)
try {
  fs.mkdirSync(dir, { recursive: true })
  const stamp = `${Date.now()}-${process.pid}`
  const name = `${event}${tool ? '-' + String(tool).replace(/[^\w.-]/g, '_') : ''}-${stamp}.json`
  fs.writeFileSync(path.join(dir, name), JSON.stringify({ argv: process.argv.slice(2), cwd: process.cwd(),
    platform: process.platform, stdin, env }, null, 2))
} catch {}

// Respuesta neutra por host y evento
if (host === 'codex' && (event === 'Stop' || event === 'SubagentStop')) process.stdout.write('{}')
else if (host === 'antigravity') process.stdout.write(event === 'PreToolUse' ? '{"decision":"allow"}' : '{}')
process.exit(0)
