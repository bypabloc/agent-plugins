# 03 · session-handoff Multi-Agente

> session-handoff 0.4.4 → 0.5.0. Antecedentes: [`10-caso-de-estudio-session-handoff.md`](../../research/multi_agent_support/10-caso-de-estudio-session-handoff.md). El plugin ya separa el núcleo puro (`handoff.ts`, `store.ts` con la interfaz `Io`, `status.ts`, `metrics.ts`, `tail.ts`) del cableado (`register.tsx`). Portar significa **escribir un cableado por host** sin tocar la lógica.

---

## 1. Principios

1. **El núcleo no cambia de lógica.** `stopDecision`, `boundMessage`, `pendingText`, `missingHashes`, `testCounts` y `keepTail` se reutilizan tal cual.
2. **Claude Code no cambia.** `register.tsx` y `hooks/hooks.json` (`{"modules": …}`) quedan iguales, y los tests de `register.test.ts` pasan sin cambios. Los textos que se inyectan en Claude son idénticos a los de 0.4.4 (golden en T-40).
3. **El núcleo no importa nada del host.** Ni `claude-code` ni `node:*` ni `@opencode/plugin`. Un test lo verifica sobre los imports de `handoff.ts`, `store.ts`, `status.ts`, `metrics.ts`, `tail.ts`, `terms.ts` y `state.ts`.
4. **session-handoff no es un guardrail:** ante un error interno, la salida es neutra (no bloquear, no inyectar). La única obligación de formato es la de Codex en `Stop` y `SubagentStop`: siempre JSON válido.
5. **Mismo estado en disco para los hosts por subprocess:** `tmp/handoff/` del checkout principal, como hoy, más `tmp/handoff/.state/` (§4).

---

## 2. Componentes Nuevos

| Archivo | Responsabilidad |
| :--- | :--- |
| `hooks/terms.ts` | Nombres por host para los textos (§5) |
| `hooks/hosts.ts` | `HostEvent`, `normalize(host, event, raw)` y `emit(host, event, Outcome)` |
| `hooks/cli.ts` | Entrada `node dist/hook.mjs <host> <evento>`. Lee stdin, normaliza, ejecuta la acción y emite |
| `hooks/io-node.ts` | `Io` sobre `node:fs/promises` y `child_process.execFile('git', …)`, con un timeout de 10 s por `git` |
| `hooks/state.ts` | Estado por sesión en archivo (§4). Reemplaza los atoms de `register.tsx` fuera de Claude |
| `hooks/actions.ts` | Las acciones que hoy están dentro de `register.tsx` (`onSessionStart`, `onStop`, `onPostTool`, `onPrompt`, `onAskQuestion`) escritas contra `Io` + `State`. `register.tsx` **no** las usa: se mantiene igual por D-07. Se evalúa unificarlo en una versión posterior |
| `adapters/codex/hooks.json`, `hooks.json` (Antigravity), `adapters/opencode/index.ts` | Cableado (§6) |
| `dist/hook.mjs` | Bundle de `cli.ts`, versionado (§9) |

---

## 3. Evento Interno y Normalización

```ts
// hooks/hosts.ts
export type Host = 'codex' | 'antigravity' | 'opencode'
export type HostEvent =
  | { kind: 'session-start'; source: 'startup' | 'resume' | 'clear' | 'compact' | 'fork' }
  | { kind: 'prompt' }
  | { kind: 'pre-invocation'; invocation: number }               // solo Antigravity
  | { kind: 'post-tool'; tool: 'shell'; command: string; output: string; background: boolean }
  | { kind: 'post-tool'; tool: 'write'; paths: string[] }         // rutas tocadas (patch → todas)
  | { kind: 'ask-question' }
  | { kind: 'stop'; active: boolean; turn: string }
export type Base = { host: Host; session: string; cwd: string; agent?: string }   // agent: subagente → se ignora
```

| Host | `session` | `cwd` | `session-start.source` | `stop.active` | Subagente |
| :--- | :--- | :--- | :--- | :--- | :--- |
| codex | `session_id` | `cwd` | `source` (incluye `compact` y `fork`) | `stop_hook_active` | `agent_id` presente → se ignora `UserPromptSubmit` y `Stop` (H-03) |
| antigravity | `conversationId` | `cwd` → `workspacePaths[0]` | Siempre `startup` (no trae `source`) | `continuation_active` | No aplica |
| opencode | `sessionID` | `ctx.location.directory` | `startup`, o `compact` tras un evento de compactación (§6.3) | Contador propio (`State.lastStop`) | Sesión con `parentID` → se ignora |

Herramientas que cuentan como `post-tool`:

| Host | shell | write |
| :--- | :--- | :--- |
| codex | `Bash` (`tool_response`: forma por confirmar, V-21) | `apply_patch` (rutas desde el patch: parser propio en `hosts.ts`, mismas reglas que [02 §4.3](./02-synapse.md#43-patchpy)) |
| antigravity | — (`PostToolUse` no trae output: §6.2) | — |
| opencode | `shell` / `bash` (`ev.result`) | `write`, `edit` (`path`), `patch` (rutas del `patchText`) |

---

## 4. Estado por Sesión

Cada invocación es un proceso nuevo en Codex y Antigravity, y en OpenCode se usa el mismo archivo para tener una sola implementación. El estado vive en `<store>/tmp/handoff/.state/<session>.json`, donde `<store>` es el checkout principal (`placeOf`).

```ts
export type SessionState = {
  v: 1
  session: string
  host: Host
  headAtStart: string | null        // HEAD del checkout al iniciar (Antigravity: commits desde aquí)
  lastStop: StopState | null        // mismo tipo que handoff.ts
  lastStopTurn: string | null       // idempotencia: Stop duplicado del mismo turno (H-02)
  lastStopOutcome: string | null    // salida emitida para ese turno (se repite tal cual)
  pendingCommits: string[]
  backgroundCommits: { dir: string; base: string }[]
  compacted: boolean                // OpenCode: la próxima inyección usa source 'compact'
  updatedAt: number
}
```

- **Escritura atómica:** archivo temporal en la misma carpeta y `rename`. Ante una lectura corrupta, se usa un estado vacío y se registra `state.reset` en `events.jsonl`.
- **Concurrencia:** Codex corre hooks en paralelo, pero cada uno escribe campos distintos (`Stop` escribe `lastStop*`; `PostToolUse`, `pendingCommits`). Se relee y se fusiona por campo justo antes de escribir. No hay lock.
- **Poda:** se conservan los 20 estados más recientes y se borran los de más de 7 días. Lo hace `SessionStart`.
- **Idempotencia (H-02):** un `Stop` con el mismo `turn` que `lastStopTurn` devuelve `lastStopOutcome` sin volver a contar bloqueos.
- **Métricas:** el `Meter` de Claude (costo, tokens, caché, límites) no se porta, porque esos hosts no exponen telemetría a los hooks ([10 §3.2](../../research/multi_agent_support/10-caso-de-estudio-session-handoff.md#32-detalle-de-telemetría)). Solo se conserva lo que alimenta los textos (`pendingCommits`).
- `tmp/handoff/.state/` ya queda cubierto por la regla de `.gitignore` de `tmp/`.

---

## 5. Textos por Host (`terms.ts`)

Los textos del núcleo nombran herramientas de Claude: `WRITE_TEXT` dice "Write o Edit" (`handoff.ts:140`). Se parametrizan sin cambiar el texto de Claude:

```ts
export type Terms = { writeTools: string; shellWriteVerbs: string; askTool: string }
export const TERMS: Record<'claude' | Host, Terms> = {
  claude:      { writeTools: 'Write o Edit',                         shellWriteVerbs: 'echo, cat o tee', askTool: 'AskUserQuestion' },
  codex:       { writeTools: 'apply_patch',                          shellWriteVerbs: 'echo, cat o tee', askTool: 'request_user_input' },
  antigravity: { writeTools: 'write_to_file o replace_file_content', shellWriteVerbs: 'echo, cat o tee', askTool: 'ask_question' },
  opencode:    { writeTools: 'write, edit o patch',                  shellWriteVerbs: 'echo, cat o tee', askTool: 'question' },
}
```

- `WRITE_TEXT` pasa a `writeText(terms = TERMS.claude)`. Lo mismo con cualquier texto que nombre una tool. La salida de Claude queda idéntica (golden T-40).
- Los `askTool` de Codex y OpenCode se confirman con V-22 y V-27.

---

## 6. Cableado por Host

Mapeo de cada función actual (tabla de [`10 §3`](../../research/multi_agent_support/10-caso-de-estudio-session-handoff.md#3-viabilidad-de-cada-función-por-agente)) a su implementación:

| Función (Claude 0.4.4) | Codex | Antigravity | OpenCode V2 |
| :--- | :--- | :--- | :--- |
| Reinyectar al iniciar | `SessionStart` | `SessionStart` | `session.hook("context")` |
| Reinyectar tras compactar | `SessionStart` `source=compact` | `PreInvocation` (corto, en cada invocación) | `context` con `source=compact` |
| Bloquear el fin del turno | `Stop` `block` | `Stop` `continue` | `session.idle` → `ctx.session.prompt` |
| Rechazar la pregunta al usuario | `PreToolUse` (si V-22) | `PreToolUse` `ask_question` | `execute.before` `question` (si V-27) |
| Validar `PROGRESS.md` al escribirlo | `PostToolUse` `apply_patch` | En `Stop` (no hay salida en `PostToolUse`) | `execute.after` |
| Hash tras `git commit` | `PostToolUse` `Bash` | En `Stop`, con `git log headAtStart..HEAD` | `execute.after` `shell` |
| Recordar hashes en cada mensaje | `UserPromptSubmit` | `PreInvocation` | `context` |
| Contar tests y ediciones (banda) | No se porta | No se porta | No se porta (la banda TUI es opcional, T-91) |
| Compactar sin resumen | No (§7) | No | `session.hook("compaction")` |
| Spinner y banda | No | Statusline del usuario, opcional (T-92) | Slots TUI, opcional (T-91) |

### 6.1 Codex: `adapters/codex/hooks.json`

```json
{
  "hooks": {
    "SessionStart": [{ "matcher": "startup|resume|clear|compact|fork", "hooks": [
      { "type": "command", "command": "node \"$PLUGIN_ROOT/dist/hook.mjs\" codex session-start",
        "commandWindows": "node \"%PLUGIN_ROOT%\\dist\\hook.mjs\" codex session-start", "timeout": 30 } ] }],
    "UserPromptSubmit": [{ "hooks": [
      { "type": "command", "command": "node \"$PLUGIN_ROOT/dist/hook.mjs\" codex prompt",
        "commandWindows": "node \"%PLUGIN_ROOT%\\dist\\hook.mjs\" codex prompt", "timeout": 30 } ] }],
    "PostToolUse": [{ "matcher": "^(Bash|apply_patch)$", "hooks": [
      { "type": "command", "command": "node \"$PLUGIN_ROOT/dist/hook.mjs\" codex post-tool",
        "commandWindows": "node \"%PLUGIN_ROOT%\\dist\\hook.mjs\" codex post-tool", "timeout": 30 } ] }],
    "Stop": [{ "hooks": [
      { "type": "command", "command": "node \"$PLUGIN_ROOT/dist/hook.mjs\" codex stop",
        "commandWindows": "node \"%PLUGIN_ROOT%\\dist\\hook.mjs\" codex stop", "timeout": 30 } ] }]
  }
}
```

Si V-22 confirma que la tool de preguntas pasa por `PreToolUse`, se agrega `"PreToolUse": [{"matcher": "^request_user_input$", …codex ask-question}]`.

| Evento | Salida (exit 0) | Notas |
| :--- | :--- | :--- |
| `session-start` | `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"<texto>"}}`, o nada sin texto | **Presupuesto de 8000 caracteres**: Codex recorta `additionalContext` a unos 2500 tokens y manda el resto a un archivo temporal. Si `boundMessage` excede el presupuesto, se emite la versión compacta: líneas de estado, `Next step`, instrucción de fase, spec y la orden de leer `<folder>/PROGRESS.md`, `DECISIONS.md` y `NOTES.md` con la herramienta de lectura. Se registra `inject.compact` en `events.jsonl` |
| `prompt` | `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"<pendingText>"}}`, o nada | |
| `post-tool` | `{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"<avisos>"}}`, o nada | **No se usa `decision: "block"`**: en Codex reemplaza el resultado del tool y el agente perdería la salida del commit. Los avisos (hash pendiente, línea de estado larga, fase inválida) van como contexto |
| `stop` | **Siempre JSON**: `{"decision":"block","reason":"<texto>"}` o `{}` | `stop_hook_active` → sin recordatorio de commits (igual que en Claude). Idempotencia por `turn_id` (§4) |
| `ask-question` | `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"<askDeniedText>"}}`, o nada | Solo si V-22 |

**Compactación:** se documenta para el usuario un `compact_prompt` mínimo en `~/.codex/config.toml`, porque un plugin no puede fijarlo (§7). El handoff completo vuelve a entrar por `SessionStart source=compact`.

### 6.2 Antigravity: `hooks.json` en la Raíz

```json
{
  "session-handoff": {
    "enabled": true,
    "SessionStart": [{ "type": "command", "command": "node dist/hook.mjs antigravity session-start", "timeout": 30 }],
    "PreInvocation": [{ "type": "command", "command": "node dist/hook.mjs antigravity pre-invocation", "timeout": 30 }],
    "PreToolUse": [{ "matcher": "^ask_question$", "hooks": [
      { "type": "command", "command": "node dist/hook.mjs antigravity ask-question", "timeout": 30 } ] }],
    "Stop": [{ "type": "command", "command": "node dist/hook.mjs antigravity stop", "timeout": 30 }]
  }
}
```

Siempre exit 0 y JSON. Ante un error: `{}`.

| Evento | Salida | Notas |
| :--- | :--- | :--- |
| `session-start` | `{"injectSteps":[<paso systemMessage con el texto>]}` | Guarda `headAtStart`. La forma exacta de cada paso (`{"systemMessage": "…"}` u objeto con `content`) se fija con V-23 |
| `pre-invocation` | `invocationNum == 0` → `{}`. Si no: `{"injectSteps":[<ephemeralMessage>]}` de **600 caracteres como máximo** (trabajo, `Status`, `Phase`, `Next step`, ruta de `PROGRESS.md` y `pendingText` si hay) | `ephemeralMessage` no queda en el historial, así que repetirlo no acumula tokens. Cubre la compactación, que Antigravity no notifica |
| `ask-question` | `{"decision":"deny","reason":"<askDeniedText>"}` o `{"decision":"allow"}` | Mismas condiciones que en Claude (spec en curso, sin `blocked` válido) |
| `stop` | `{"decision":"continue","reason":"<texto>"}` o `{}` | Antes de `stopDecision`: (1) los commits desde `headAtStart` (`git log --first-parent --no-merges --format=%h headAtStart..HEAD`) se cruzan con `missingHashes`; (2) `tooLong` y `badPhaseText` sobre `PROGRESS.md`. Si hay avisos, `continue` con esos avisos. `continuation_active` equivale a `stop_hook_active` |

Statusline opcional (T-92): `node dist/hook.mjs antigravity statusline` lee el stdin de la statusline del CLI de Antigravity (`cost.total_usd`, `context_window.used_percentage`, `quota`) y el `PROGRESS.md` del trabajo vinculado, y devuelve una línea: `● <Phase> · <Current> · ETA · ctx N% · $X`. La configura el usuario en `~/.gemini/antigravity-cli/settings.json`; el README trae el bloque.

### 6.3 OpenCode V2 (en Proceso)

`adapters/opencode/index.ts`, con `Plugin.define({ id: "bypabloc.session-handoff", setup(ctx) })`:

| Registro | Comportamiento |
| :--- | :--- |
| `ctx.session.hook("context", ev)` | Se ignoran las sesiones con `parentID`. Se agrega a `ev.system` el texto de `messageFor(…)` con `source = state.compacted ? 'compact' : 'startup'` y después se limpia `compacted`. **El texto debe ser estable** entre llamadas mientras `PROGRESS.md`, `DECISIONS.md` y `NOTES.md` no cambien (cache por `mtime`) para no romper el caché de prompts. Se agrega `pendingText` si hay hashes pendientes |
| `ctx.session.hook("compaction", ev)` | Con un trabajo vinculado: `ev.result` = `[MARKER, ACK?, …keepTail(messages)]`, adaptando `tail.ts` al tipo de mensaje de OpenCode (V-24), y `state.compacted = true`. Sin trabajo, o con un tramo demasiado grande: no se toca `ev` (compactación nativa) y se registra `compact.fallback`. **Es el único host fuera de Claude con compactación sin resumen** |
| `ctx.event.subscribe({types: ["session.idle"]})` | Evalúa `stopDecision` (con los mismos topes, `MAX_BLOCKS` y `external-wait`). Si bloquea: `ctx.session.prompt({sessionID, text: <block>})`. Si la API difiere, lo ajusta V-25. Los recordatorios de commits van primero, como en Claude |
| `ctx.tool.hook("execute.after", ev)` | `shell`: detecta commits y tests en `ev.result` (V-26). `write`, `edit` y `patch` sobre `PROGRESS.md`: avisos. Los avisos se agregan al final del resultado (`ev.result.output += "\n\n" + avisos`, según V-26) |
| `ctx.tool.hook("execute.before", ev)` | `ev.tool === "question"` con spec en curso y sin `blocked` válido → `throw new Error(askDeniedText(config, TERMS.opencode))` (V-27) |
| `Io` | `node:fs/promises` (Bun lo implementa) y `Bun.spawn(['git', …])`. El estado es el mismo archivo de §4 |

---

## 7. Compactación por Host

| Host | Qué hace el plugin | Qué se documenta para el usuario |
| :--- | :--- | :--- |
| Claude | Sin cambios (`session.compact`) | — |
| Codex | Reinyecta en `SessionStart source=compact` | Agregar a `~/.codex/config.toml`: `compact_prompt = "Resume en 10 líneas: objetivo, archivos tocados y el último comando. El estado del trabajo llega aparte (session-handoff)."` |
| Antigravity | Puntero efímero en cada `PreInvocation` | — (no hay claves documentadas) |
| OpenCode | Reemplaza el resultado (sin resumen del modelo) | — |

---

## 8. Errores y Degradación

| Situación | Salida |
| :--- | :--- |
| `node` < 20 o ausente | El comando falla. Codex y Antigravity siguen sin el hook (no es un guardrail). `README` y `doctor` (T-48) lo informan |
| stdin vacío o JSON inválido | Codex `Stop`: `{}`. Resto: sin salida (o `{}` en Antigravity). Se registra `input.error` |
| Error de `git` (sin repo) | `placeOf` usa `cwd` como raíz, igual que hoy |
| Error de disco en `.state` | Se sigue sin estado. Se registra `state.error` |

`node dist/hook.mjs doctor` muestra la versión de Node, si `dist/hook.mjs` está al día con la versión del plugin, el trabajo vinculado del `cwd` y el último evento de cada tipo en `events.jsonl`.

---

## 9. Build y Distribución del CLI

- `bun build hooks/cli.ts --target=node --format=esm --outfile=dist/hook.mjs`, sin minificar para que se pueda auditar y sin dependencias externas.
- `dist/hook.mjs` **se versiona**: los espejos se instalan sin build. El `.gitignore` raíz tiene la excepción `!plugins/session-handoff/dist/`.
- **CI:** `bun run build && git diff --exit-code plugins/session-handoff/dist/`. Falla si el bundle no corresponde al código.
- `cli.ts` comprueba al inicio `process.versions.node` ≥ 20. Si no se cumple, emite la salida neutra del evento.
- `VERSION` de `handoff.ts` se registra en cada línea de `events.jsonl` (`v`) junto con `host`, el campo nuevo.

---

## 10. Bitácora y Documentación

- `docs/bitacora/versiones/0.5.0.md`: qué se portó por host, qué se degradó y las verificaciones resueltas.
- `docs/bitacora/vigilancia.md`: se agregan los eventos por host que se vigilan (`inject.compact`, `state.reset`, `compact.fallback` en OpenCode).
- README: tabla "Qué hace en cada agente" con la información de §6 y una sección de instalación por host ([01 §7.2](./01-repos-y-publicacion.md#72-session-handoff)).

---

## 11. Verificaciones Pendientes (session-handoff)

| Id | Host | Pregunta | Cómo se responde |
| :--- | :--- | :--- | :--- |
| V-21 | Codex | Forma de `tool_response` en `PostToolUse Bash` (`stdout`, `stderr`, `exit_code`, ¿texto plano?) y si llega `run_in_background` | Sonda F0 |
| V-22 | Codex | ¿`request_user_input` pasa por `PreToolUse`? ¿Con qué `tool_name`? | Sonda F0 |
| V-23 | Antigravity | Forma exacta de un paso de `injectSteps` (`systemMessage`, `ephemeralMessage`) | Sonda F0 y E2E |
| V-24 | OpenCode | Tipo de mensaje en `session.hook("compaction")` y forma de `ev.result` | Tipos de `@opencode/plugin` 2.3.x |
| V-25 | OpenCode | API para continuar una sesión inactiva (`ctx.session.prompt` u otra) y si `session.idle` existe en 2.3.2 | Tipos y prueba |
| V-26 | OpenCode | Campos de `ev.result` en `execute.after` y si mutarlo llega al modelo | Tipos y prueba |
| V-27 | OpenCode | Nombre de la tool de preguntas y si pasa por `execute.before` | Sonda F0 |
| V-28 | Codex | Si `SessionStart source=compact` se dispara tras la compactación automática (no solo con `/compact`) | E2E |
