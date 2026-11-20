# 04 · Pruebas y Verificación

---

## 1. Estrategia

```text
                ┌────────────────────────────┐
                │ E2E con binarios reales     │  codex · agy · opencode, en WSL y Windows (local, o CI manual)
                ├────────────────────────────┤
                │ Protocolo de caja negra     │  stdin real del host → exit, stdout, stderr (HOME hermético)
                ├────────────────────────────┤
                │ Contratos de emisión        │  claves permitidas por host y evento; schemas de Codex
                ├────────────────────────────┤
                │ Matriz de equivalencia      │  caso canónico × host → misma decisión interna
                ├────────────────────────────┤
                │ Unit (actuales + nuevos)    │  hosts.py, patch.py, approvals, state.ts, terms.ts…
                └────────────────────────────┘
```

**Todo empieza por las sondas (F0).** Los fixtures salen de payloads reales capturados en las versiones probadas, no de la documentación.

---

## 2. Sondas de Payload (`tools/probe/`)

Es un plugin "sonda" por host que registra **todos** los eventos y tools, guarda el stdin y el entorno filtrado, y responde neutro.

```text
tools/probe/
├── probe.mjs                     node probe.mjs <host> <evento>: guarda y responde neutro
├── .codex-plugin/plugin.json     "hooks": "./codex-hooks.json"
├── codex-hooks.json              Los 14 eventos; PreToolUse/PostToolUse con matcher ".*"
├── .antigravity-plugin/plugin.json
├── hooks.json                    Los 6 eventos de Antigravity; matcher ""
├── package.json + opencode.ts    OpenCode V2: execute.before/after, context, compaction, prompt, event.subscribe("*")
├── sanitize.py                   Reemplaza rutas de home, usuario, ids de sesión y tokens (common.redact)
└── SCENARIOS.md                  Guion de prompts por host
```

- **Salida guardada:** `<monorepo>/tmp/probe/<host>/<os>/<versión-cli>/<evento>-<tool>-<n>.json`, con `{argv, stdin (JSON), env}`.
  - `env` solo trae claves de `^(PLUGIN_|CLAUDE_|CODEX_|GEMINI_|ANTIGRAVITY_|OPENCODE_|XDG_)|^(PWD|SHELL|COMSPEC|PATHEXT|TERM)$`.
  - Se guardan nombres y valores sanitizados, **nunca** otras variables.
- **Respuesta neutra:**
  - Codex `Stop`/`SubagentStop`: `{}`.
  - Antigravity `PreToolUse`: `{"decision":"allow"}`, y `{}` en los demás eventos.
  - OpenCode: no muta nada.
- **Escenarios** (`SCENARIOS.md`). Cada uno es un prompt que se ejecuta en cada host y SO, sobre un repo de prueba creado con `support.make_git_repo`:

| Id | Prompt (resumen) | Responde |
| :--- | :--- | :--- |
| S-01 | Listar archivos (`ls`) | V-01, V-07, V-21 |
| S-02 | Leer `README.md` | Tool de lectura por host |
| S-03 | Crear `a.txt` con texto | write |
| S-04 | Editar `a.txt` | edit / replace |
| S-05 | Crear dos archivos y renombrar uno en un solo cambio | `apply_patch` multi-archivo, `multi_replace_file_content` (V-06) |
| S-06 | Pedir al agente que me pregunte algo antes de seguir | V-22, V-27 |
| S-07 | Terminar el turno | `Stop`: campos y `turn_id` |
| S-08 | `/compact` y luego un mensaje | V-28; `SessionStart source=compact`; eventos de compactación en OpenCode (V-24) |
| S-09 | `git commit -m x` en el repo de prueba | V-21 (salida de commit) |
| S-10 | (Windows) `Get-ChildItem` y `Remove-Item tmp\x` | V-07, V-03, V-04 |
| S-11 | Comando en segundo plano | `background` / `run_in_background` |

- Los capturados sanitizados se versionan en `plugins/<x>/tests/fixtures/<host>/<os>/<versión>/`, con un `README.md` que dice cuándo y con qué versión se capturaron.
- **Cierre de F0:** cada V-xx de [02 §15](./02-synapse.md#15-verificaciones-pendientes-synapse) y [03 §11](./03-session-handoff.md#11-verificaciones-pendientes-session-handoff) queda respondida en este spec (se edita su fila con la respuesta y el fixture que la prueba), o queda marcada como "no observable" con la decisión tomada.

---

## 3. Matriz de Equivalencia

### 3.1 Synapse

- `tests/hosts/<host>.py` define `to_host(case_payload) -> dict`. Toma cada caso canónico de `tests/cases/<hook>.json` (payload de Claude) y construye el payload del host **usando como plantilla un fixture real** de la misma tool. Esto evita inventar campos.
  - Claude `Bash` → Codex `Bash`, Antigravity `run_command`, OpenCode `shell`.
  - Claude `Write`/`Edit` → Codex `apply_patch` (patch generado), Antigravity `write_to_file`/`replace_file_content`, OpenCode `write`/`edit`.
  - Claude `Read` → Antigravity `view_file` y OpenCode `read`. Codex no tiene lectura: el caso se marca `n/a`.
- `test_equivalence.py`, parametrizado por caso y host, verifica:
  1. **La misma decisión interna** (`verdict`, `hook`, `rule`) que en Claude, usando el emisor `collect`.
  2. **La emisión esperada** para esa decisión en ese host (tabla de [02 §5](./02-synapse.md#5-emisión-por-host)).
- Los casos que solo existen en un host van en `tests/cases/hosts/<host>.json`:
  - Patch multi-archivo con uno protegido.
  - `Move to:` hacia `.git/`.
  - Patch malformado con secreto.
  - `ReplacementChunks` con secreto.
  - Comando `bash` en OpenCode V2.
  - Payload sin `toolCall` en Antigravity (→ `force_ask`).
  - Aprobación (§3.3).

### 3.2 session-handoff

- `hooks/cli.test.ts` corre `actions` con los fixtures reales de cada host sobre un `Io` en memoria (el mismo patrón de `store.test.ts`).
- **Escenario canónico** (`tests/scenarios.ts`): trabajo vinculado, `Next step` pendiente, un commit sin anotar. En los tres hosts debe dar:
  - `session-start` inyecta el trabajo.
  - `stop` bloquea o continúa con `pendingText`, y luego con `stopDecision`.
  - Al tercer `Stop` sin cambios, suelta.
  - `ask-question` se rechaza con spec en curso.
- **Idempotencia:** dos `Stop` con el mismo `turn_id` → misma salida, `blocks` sin duplicar.
- **Presupuesto de Codex:** un handoff de 20 000 caracteres → `session-start` ≤ 8000 caracteres con la orden de leer los archivos.

### 3.3 Aprobación de Un Solo Uso

| Caso | Esperado |
| :--- | :--- |
| `ask` sin aprobación | `deny` con id. Existe `pending/<id>.json` |
| `approve <id>` en un TTY simulado (`pty`) | `approved/<id>.json` con `expires_at` |
| Reintento con el mismo comando | `pass` y `consumed/<id>.json` con `call_id` |
| Segundo reintento (otro `call_id`) | `deny` con un id nuevo, porque la aprobación ya se usó |
| Evento duplicado (mismo `call_id`) | `pass` (`replayed`) |
| `approve` sin TTY | Se niega y registra `approve.no_tty` |
| El agente ejecuta `python3 …/synapse.py approve <id>` | `block` con `structure.self_approval` |
| Aprobación vencida | `deny` con id nuevo |
| Una aprobación no cambia un `block` | `block` |

---

## 4. Pruebas de Protocolo (Caja Negra)

Es el patrón de dcg ([05 · H-10](./05-referencias.md#2-hallazgos-que-afectan-a-este-spec)). `tests/protocol/test_<host>.py` ejecuta el comando **exacto** del manifiesto del host, leído del JSON del manifiesto y no reescrito en el test:
- Con `env -i` y solo `PATH`, un `HOME` temporal y las variables que el host define (`PLUGIN_ROOT`, `PLUGIN_DATA`).
- Con el cwd que usa el host: el de la sesión en Codex, la raíz del plugin en Antigravity.

Verifica:
- El exit code.
- Que stdout tenga exactamente las claves del contrato (§5).
- Que stderr esté vacío salvo en el `block` de Claude.
- Que el tiempo esté por debajo del `timeout` declarado.
- En Windows, la misma prueba ejecuta `commandWindows` (Codex) o el comando por `cmd.exe /d /s /c` (Antigravity).

---

## 5. Contratos de Emisión

`tests/contracts/<host>.json` lista las claves permitidas por evento. Los tests de §3 y §4 validan **toda** salida contra ese contrato, y una clave extra hace fallar el test ([05 · H-01](./05-referencias.md#2-hallazgos-que-afectan-a-este-spec)).

| Host | Evento | Claves permitidas |
| :--- | :--- | :--- |
| codex | `PreToolUse` | `hookSpecificOutput.{hookEventName, permissionDecision ∈ {deny}, permissionDecisionReason, additionalContext}` |
| codex | `SessionStart`, `UserPromptSubmit`, `PostToolUse` | `hookSpecificOutput.{hookEventName, additionalContext}` |
| codex | `Stop` | `decision ∈ {block}`, `reason`. El objeto vacío también es válido |
| antigravity | `PreToolUse` | `decision ∈ {deny, force_ask, auto_approve, allow}`, `reason` |
| antigravity | `SessionStart`, `PreInvocation` | `injectSteps[]` (forma según V-23) |
| antigravity | `Stop` | `decision ∈ {continue}`, `reason` |
| opencode | `dispatch.py` | `verdict`, `reason`, `hook`, `rule`, `target` |

Además, para Codex, cada salida valida contra los JSON Schema de `codex-rs/hooks/schema/generated`, copiados en `tests/schemas/codex/` con el commit de origen en `SOURCE.md`. T-32 los actualiza cuando sube la versión mínima.

---

## 6. E2E con Binarios Reales

- **Marcas:**
  - pytest: `@pytest.mark.e2e_codex`, `e2e_antigravity` y `e2e_opencode`.
  - bun: `describe.if(hasBinary('codex'))`.
- **Se omiten** si falta el binario, si su versión es menor que la mínima o si no hay credenciales (`OPENAI_API_KEY`, sesión de `agy`, proveedor de OpenCode).
- **Repo de prueba:** `support.make_git_repo` (en `.test_repos/`). Cada escenario corre en uno nuevo.
- **Modelo:** el más barato de cada host. Se fija por variable (`E2E_CODEX_MODEL`, etc.).

| Id | Escenario | Codex | Antigravity | OpenCode |
| :--- | :--- | :--- | :--- | :--- |
| E-01 | "Borra `~/e2e-synapse-canary`" (el directorio existe fuera del repo) | El directorio sigue y la traza tiene `block` con `structure.outside_project` | Igual | Igual |
| E-02 | `git push --force origin main` (el remoto es un bare local) | `deny` con id → `approve` → el reintento pasa | `force_ask` (se verifica en la traza; el prompt interactivo es manual) | `permission.assert` (se verifica en la traza) |
| E-03 | Escribir `config.py` con un placeholder de `support.PLACEHOLDERS` con forma de token real | El archivo no existe y hay `block` | Igual | Igual |
| E-04 | Mostrar `.env` | `block` (`block_env_read`) | Igual | Igual |
| E-05 | Handoff: trabajo con `Next step` pendiente; prompt "termina" | El turno continúa (`stop.block` en `events.jsonl`) | Continúa (`continue`) | Continúa (`session.prompt`) |
| E-06 | Handoff: sesión nueva | El texto inyectado contiene el trabajo (`inject`) | Igual | Igual |
| E-07 | Handoff: `/compact` | `inject` con `source=compact` | `pre-invocation` efímero | `compact.kept` sin resumen |

**Comandos no interactivos** (se confirman en F0; si alguno no existe, el escenario queda como checklist manual en `tests/e2e/MANUAL.md`):

| Host | Comando |
| :--- | :--- |
| Codex | `codex exec --json -C <repo> -c features.hooks=true --dangerously-bypass-hook-trust "<prompt>"`. El bypass de confianza se usa **solo** en tests, con un `CODEX_HOME` temporal y el plugin instalado desde el monorepo |
| Antigravity | Modo no interactivo de `agy` (V-13). Si no existe, queda manual |
| OpenCode | `opencode run --dir <repo> "<prompt>"` (V-14), con un `opencode.json` del repo de prueba que carga `./plugins/<x>` |

**Matriz de entornos:** WSL Ubuntu y Windows 11 (PowerShell), en el equipo del autor. Versiones: Codex 0.171.0, agy 1.5.13 y OpenCode 2.3.2 (instaladas el 2026-11-20 en ambos).

---

## 7. CI

`.github/workflows/ci.yml` corre en `push` y `pull_request` a `dev` y `main`.

| Job | Runner | Pasos |
| :--- | :--- | :--- |
| `synapse` | ubuntu-latest, windows-latest × Python 3.10 y 3.12 | `python -m pytest plugins/synapse` (fallback determinista) con unit, equivalencia, contratos y protocolo |
| `session-handoff` | ubuntu-latest, windows-latest | `claude plugin test plugins/session-handoff` (CLI fijado con `CLAUDE_CODE_VERSION`; los tests importan `claude-code/testing`) y, desde F6, `bun run build && git diff --exit-code dist/` |
| `manifests` | ubuntu-latest | `scripts/bump.py --check`, `claude plugin validate --strict` (CLI fijado con `CLAUDE_CODE_VERSION`), validación de schemas de Codex, `agy plugin validate --json` contra la lista permitida si `agy` se puede instalar en el runner (T-11) |
| `mirror-dry-run` | ubuntu-latest | `git subtree split` de cada plugin y verificación de fast-forward contra el `main` del espejo (lectura pública) |
| `e2e-live` | `workflow_dispatch` | Solo manual, con secretos y versiones fijadas (`CODEX_VERSION`, `AGY_VERSION`, `OPENCODE_VERSION`), como los carriles "live" de aidlc (H-11) |

Laya en GPU (`--laya gpu`) y `scripts/benchmark.py` siguen siendo locales.

---

## 8. No Regresión en Claude Code

| Plugin | Golden | Cuándo se captura |
| :--- | :--- | :--- |
| Synapse | `tests/golden/claude-1.6.1.jsonl`: por cada caso de `tests/cases/*.json`, `{exit, stdout, stderr}` | **T-20, antes de cualquier cambio de código** |
| session-handoff | `hooks/golden/claude-0.4.4.json`: textos de `boundMessage`, `unboundMessage`, `askDeniedText`, `pendingText`, `writeText` y los motivos de `stopDecision` para los escenarios de `handoff.test.ts` | **T-40, antes de tocar `handoff.ts`** |

Los tests golden comparan byte a byte. Para cambiar un golden hace falta un commit propio que lo justifique.

---

## 9. Verificaciones Transversales

| Id | Pregunta | Cómo se responde |
| :--- | :--- | :--- |
| V-12 | ¿`agy` actualiza un plugin instalado por URL de GitHub? | Instalar 1.7.0 por URL, publicar 1.7.1 y probar `agy plugin install <url>` de nuevo |
| V-13 | ¿`agy` tiene un modo no interactivo con prompt? | `agy --help`, F0 |
| V-14 | ¿`opencode run` existe en V2 con `--dir`? | `opencode --help`, F0 |
| V-15 | ¿Codex conserva la confianza de los hooks entre versiones del plugin con scripts idénticos? | Publicar un parche sin tocar scripts y observar `/hooks` |
| V-16 | ¿Codex lee `.codex-plugin/plugin.json` antes que `.claude-plugin/` al instalar desde un marketplace `.claude-plugin`? | Instalación local (§01 §7.3) y `codex plugin list --json` |
