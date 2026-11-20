# 02 · Synapse Multi-Agente

> Synapse 1.6.1 → 1.7.0. Antecedentes: [`09-caso-de-estudio-synapse.md`](../../research/multi_agent_support/09-caso-de-estudio-synapse.md). Este documento define **qué cambia, con qué contratos y en qué archivos**.

---

## 1. Principios

1. **La lógica de decisión no cambia.** Solo cambian la entrada (normalización) y la salida (emisión). Las reglas, Laya, el alcance git y la traza se reutilizan.
2. **Claude Code no cambia.** `hooks/hooks.json` sigue invocando un script por hook sin `--host`. La salida en Claude debe ser **idéntica byte a byte** a la de 1.6.1 para todos los casos de `tests/cases/*.json`.
3. **El host se declara** con `--host` en `adapters/codex/hooks.json`, en `hooks.json` (Antigravity) y en el shim de OpenCode.
4. **Ningún host falla abierto por formato.** Toda emisión se valida contra el contrato del host (§5) con tests que fallan ante campos extra ([05 · H-01](./05-referencias.md#2-hallazgos-que-afectan-a-este-spec)).
5. **Degradar hacia el lado seguro** y dejar registro: la traza guarda `decision` (intención) y `emitted` (lo que se emitió).

---

## 2. Componentes Nuevos

| Archivo | Responsabilidad |
| :--- | :--- |
| `hooks/hosts.py` | `HOSTS`, `HookEvent`, `FileChange`, `Decision`, `normalize(host, raw, env) -> HookEvent` y `emit(host, decision) -> Emission` (stdout, stderr, exit) |
| `hooks/patch.py` | `parse(text) -> list[FileChange]` para el formato `*** Begin Patch` de Codex `apply_patch` y OpenCode `patch.patchText` |
| `hooks/dispatch.py` | Entrada única de los hosts distintos de Claude: lee stdin, normaliza, corre en el mismo proceso los hooks que aplican al tipo de acción, combina las decisiones y emite una sola salida |
| `hooks/approvals.py` | Aprobación de un solo uso (§6) |
| `hooks/run-hook.cmd` | Lanzador políglota bash/cmd (§8) |
| `scripts/synapse.py` | CLI de usuario: `approve`, `doctor`, `log` (§10) |
| `adapters/codex/hooks.json`, `hooks.json`, `adapters/opencode/index.ts` | Cableado por host (§7) |

---

## 3. Modelo Interno

```python
# hooks/hosts.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal

Host = Literal["claude", "codex", "antigravity", "opencode"]
Kind = Literal["shell", "read", "write", "other"]
Op = Literal["write", "edit", "add", "update", "delete", "move"]
Verdict = Literal["block", "ask", "allow", "pass"]


@dataclass(frozen=True)
class FileChange:
    path: str                  # absoluta tras resolver contra cwd
    op: Op
    new_text: str = ""         # contenido nuevo: Write completo, new_string, líneas '+' o cuerpo de Add File
    old_text: str = ""         # old_string o líneas '-'
    move_to: str | None = None # destino de '*** Move to:' (también se evalúa como ruta)


@dataclass(frozen=True)
class HookEvent:
    host: Host
    kind: Kind
    tool: str                  # nombre nativo (Bash, apply_patch, run_command, shell…)
    command: str = ""          # shell
    read_path: str = ""        # read
    files: tuple[FileChange, ...] = ()
    cwd: str = ""
    project_dir: str = ""      # ancla de allowed_roots (§11)
    session: str = ""
    call_id: str = ""          # tool_use_id / toolCall.id / callID (idempotencia, §6)
    parse_error: str | None = None   # patch malformado (§4.3)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    hook: str
    rule: str
    decided_by: Literal["python", "laya"]
    reason: str = ""
    target: str = ""
    context: str | None = None       # additionalContext (git_recoverable_delete…)
    evidence: dict[str, Any] | None = None
```

### 3.1 Adaptación de los Hooks Actuales

- Cada hook expone `evaluate(event: HookEvent) -> None`. La lógica actual queda tal cual y decide llamando a `emit_decision` o `emit_block`.
- `emit_decision` y `emit_block` (`common.py:380` y `common.py:411`) dejan de escribir y salir por su cuenta: construyen un `Decision` y lo entregan al **emisor activo** (`hosts.current_emitter()`).
  - Emisor `single`: es el modo Claude y el de cada script suelto. Escribe exactamente lo mismo que hoy y sale con el mismo código.
  - Emisor `collect`: lo usa `dispatch.py`. Guarda el `Decision` y corta la evaluación del hook con una excepción privada `_Decided`.
- `main()` de cada hook queda como `run_main(lambda: evaluate(read_event("<hook>")))`. Para Claude, `read_event` llama a `normalize("claude", …)`.
- **Filtro por tipo, no por nombre de tool:**

| Hook | Hoy filtra | Pasa a filtrar | Lee |
| :--- | :--- | :--- | :--- |
| `block_dangerous` | `tool_name == "Bash"` (`block_dangerous.py:1132`) | `event.kind == "shell"` | `event.command` |
| `block_env_read` | `Read` / `Bash` | `kind in {"read", "shell"}` | `event.read_path`, `event.command` |
| `protect_files` | `{"Edit", "Write"}` | `kind == "write"` | Cada `f.path` y `f.move_to` de `event.files` |
| `detect_secrets` | `Edit.new_string` / `Write.content` | `kind == "write"` | `"\n".join(f.new_text for f in event.files)`. La línea que coincide se informa con su archivo |

### 3.2 Combinación en `dispatch.py`

| Tipo | Hooks, en orden |
| :--- | :--- |
| `shell` | `block_dangerous`, `block_env_read` |
| `read` | `block_env_read` |
| `write` | `protect_files`, `detect_secrets` |
| `other` | ninguno: `pass` con regla `exit.other_tool` |

Precedencia: **`block` > `ask` > `allow` > `pass`**, igual que combina Claude Code varias decisiones de `PreToolUse`.
- El primer `block` corta la evaluación.
- Varios `ask` se combinan en un motivo con un ítem por hook.
- Los `context` se concatenan.

Cada hook deja sus propios pasos en la traza. La traza de `dispatch` agrega un paso `dispatch` con la lista de hooks evaluados y la decisión combinada.

---

## 4. Normalización por Host

### 4.1 Tabla de Campos

| Host | `kind=shell` | `kind=read` | `kind=write` | `session` | `call_id` | `cwd` | `project_dir` |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **claude** | `Bash.command` | `Read.file_path` | `Write{file_path, content}` → `op=write`; `Edit{file_path, old_string, new_string}` → `op=edit` | `session_id` | `tool_use_id` | `cwd` | `CLAUDE_PROJECT_DIR` → `cwd` |
| **codex** | `Bash.command` (string; si llega como lista `["bash","-lc",X]` se toma `X`, y otra lista se une con `shlex.join`; V-01) | — (no existe tool de lectura) | `apply_patch.command` → `patch.parse` | `session_id` | `tool_use_id` (o `turn_id` + `tool_name`) | `cwd` (+ `workdir` del input si existe, V-01) | `git rev-parse --show-toplevel` del `cwd` de la sesión → `cwd` |
| **antigravity** | `run_command.CommandLine` (cwd del comando = `args.Cwd`) | `view_file.AbsolutePath` | `write_to_file{TargetFile, CodeContent}` → `op=write`; `replace_file_content{TargetFile, TargetContent, ReplacementContent}` → `op=edit`; `multi_replace_file_content{TargetFile, ReplacementChunks[]}` → `op=edit` (§4.2) | `conversationId` | `toolCall.id` | `args.Cwd` → `cwd` → `workspacePaths[0]` | `workspacePaths[0]` → `cwd` |
| **opencode** | `shell.command` (o `bash.command`; cwd = `workdir`) | `read.path` | `write{path, content}`; `edit{path, oldString, newString}`; `patch.patchText` → `patch.parse` | `sessionID` | `callID` / `id` | `directory` que envía el shim | `project` que envía el shim (`ctx.location.project.directory`) |

Las rutas relativas se resuelven contra `cwd`. Las de `apply_patch` se resuelven contra el `cwd` de la sesión, como hace Codex.

### 4.2 `multi_replace_file_content` (Antigravity)

Los campos de `ReplacementChunks` no están documentados (V-06). Hasta confirmarlos con la sonda:
- `new_text` es la concatenación de todo valor string de cada chunk cuya clave contiene `Replacement`.
- Si el chunk no es un objeto o no tiene esas claves, se serializa el chunk completo como `new_text`. Es conservador: `detect_secrets` ve más texto, nunca menos.

### 4.3 `patch.py`

| Línea | Efecto |
| :--- | :--- |
| `*** Begin Patch` / `*** End Patch` | Delimitan el patch. Si falta `Begin`, es error de parseo |
| `*** Add File: p` | `FileChange(p, "add", new_text=<líneas '+' sin el prefijo>)` |
| `*** Update File: p` | `FileChange(p, "update", new_text=<'+'>, old_text=<'-'>)`. Las líneas `@@` y de contexto se ignoran |
| `*** Move to: q` (tras un Update) | `move_to=q`. `protect_files` evalúa `p` y `q` |
| `*** Delete File: p` | `FileChange(p, "delete")`. `protect_files` lo evalúa como modificación |
| Patch malformado | `parse_error` se llena y `files=()`. `dispatch` pasa el texto completo a `detect_secrets` como un solo `FileChange("<patch>", "update", new_text=raw)` y registra `patch.parse_error` en la traza |

Un archivo protegido dentro de un patch rechaza **el patch completo**, nombrando el archivo, porque Codex solo puede rechazar el patch entero.

### 4.4 Normalización Inválida

Si el payload no tiene la forma esperada para el `--host` declarado (falta `toolCall`, `tool_input` no es objeto…):
- La traza registra `normalize.error`.
- El evento queda como `kind="other"`.
- La emisión es `pass` en Claude y Codex (igual que hoy ante entrada vacía) y **`force_ask` en Antigravity**, por D-05: un payload irreconocible en Antigravity es la señal de un cambio de API.

---

## 5. Emisión por Host

**Contrato estricto:** solo se emiten las claves listadas. Los tests de contrato (§04 §5) fallan ante cualquier otra.

### 5.1 Claude Code (sin cambios)

| Verdict | Exit | stdout | stderr |
| :--- | :---: | :--- | :--- |
| `block` | 2 | — | `🚫 BLOCKED · <atribución>\n<motivo>\n` |
| `ask` / `allow` | 0 | `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask\|allow","permissionDecisionReason":"<atribución>: <motivo>"[,"additionalContext":"…"]}}` | — |
| `pass` | 0 | — | — |

### 5.2 Codex

| Verdict | Exit | stdout | Notas |
| :--- | :---: | :--- | :--- |
| `block` | 0 | `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"<atribución>: <motivo>"}}` | Se prefiere JSON al exit 2 (doc de Codex) |
| `ask` | 0 | Si hay una aprobación vigente para la clave (§6): sin stdout (`emitted=pass`, regla `approval.consumed`). Si no: el mismo `deny` con el texto de aprobación (§6.3) | `emitted=deny` |
| `allow` | 0 | Sin stdout | Codex rechaza un `allow` sin `updatedInput` |
| `allow` con `context` | 0 | `{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"…"}}` **solo si V-02 confirma** que Codex lo acepta sin `permissionDecision`. Si no, sin stdout y la traza registra `context.dropped` | |
| `pass` | 0 | Sin stdout | |
| Error interno | 0 | Sin stdout | Igual que en Claude: error no bloqueante, registrado (`hook.error`) |

### 5.3 Antigravity

Siempre **exit 0** y JSON en stdout. Cualquier otro código falla abierto.

| Verdict | stdout | Motivo |
| :--- | :--- | :--- |
| `block` | `{"decision":"deny","reason":"<atribución>: <motivo>"}` | |
| `ask` | `{"decision":"force_ask","reason":"<atribución>: <motivo>"}` | `force_ask` y no `ask`: con `ask`, un "Always Allow" previo saltaría la pregunta de Synapse |
| `allow` | `{"decision":"auto_approve","reason":"<atribución>: <motivo>"}` | Equivale al `allow` de Claude (salta el prompt). No salta una revisión impuesta por el admin |
| `pass` | `{"decision":"allow"}` | En Antigravity `allow` significa "pasa al siguiente hook o a la política" |
| Error interno, normalización inválida o import fallido | `{"decision":"force_ask","reason":"Synapse · error interno (<tipo>): confirma manualmente. Revisa synapse doctor."}` | D-05. `dispatch.py` envuelve **todo**, incluidos los imports, en `try/except BaseException` |
| `context` | Se agrega al final de `reason` (no hay `additionalContext` en `PreToolUse`) | |

### 5.4 OpenCode V2

`dispatch.py --host opencode` siempre sale con 0 e imprime un JSON neutral: `{"verdict":"block|ask|allow|pass","reason":"…","hook":"…","rule":"…","target":"…"}`. El shim lo traduce así:

| Verdict | Acción en el shim |
| :--- | :--- |
| `block` | `throw new Error(reason)`. El modelo ve el mensaje y sigue |
| `ask` | `await ctx.permission.assert({sessionID, agent, source: {type: "tool", messageID, id}, action: "synapse", resources: [target], metadata: {reason, hook, rule}})`. Si el usuario rechaza, `assert` lanza un error y la llamada se cancela |
| `allow` / `pass` | `return`. Se aplican los permisos nativos de OpenCode. Synapse no auto-aprueba en OpenCode: correlacionar `permission.hook("evaluate")` con la llamada queda fuera de alcance |
| Error del shim: spawn fallido, timeout de 15 s, exit ≠ 0 o JSON inválido | `ask` con el motivo `Synapse no pudo evaluar (<causa>): confirma manualmente`. Es el mismo criterio que D-05 |

---

## 6. Aprobación de Un Solo Uso (Codex)

Codex no tiene `ask` en `PreToolUse`. Si se degrada a `deny` sin más, el reintento se rechaza siempre. Este mecanismo (D-04) le da al usuario una vía de aprobación que el agente no puede usar.

### 6.1 Clave y Almacenamiento

- **Clave:** `sha256(host \0 project_dir \0 hook \0 rule \0 target_canónico)`.
  - Para shell, el target canónico es el comando sin comentarios y con los espacios colapsados.
  - Para escrituras, son las rutas ordenadas más el `sha256` de cada `new_text`.
  - **id** = los primeros 8 caracteres hex de la clave.
- **Directorio de estado:** `SYNAPSE_STATE_DIR`, luego `${XDG_STATE_HOME:-~/.local/state}/synapse` en Linux o `%LOCALAPPDATA%\synapse` en Windows. Subcarpetas:
  - `approvals/pending/<id>.json`: `{key, host, hook, rule, reason, preview, cwd, project_dir, session, created_at}`. `preview` va redactado con `common.redact` y tiene como máximo 200 caracteres. Vence a los **30 min**.
  - `approvals/approved/<id>.json`: lo anterior más `approved_at` y `expires_at`. Vence a los **10 min** desde la aprobación.
  - `approvals/consumed/<id>.json`: lo anterior más `consumed_at` y `call_id`. Se borra a las 24 h y sirve para auditoría.
- Las escrituras son atómicas (archivo temporal más `os.replace`). Al leer se purgan los vencidos.

### 6.2 Flujo

```text
PreToolUse (codex) ─▶ hooks evalúan ─▶ verdict = ask
     │
     ├─ ¿approved/<id> vigente con la misma clave? ── sí ──▶ mover a consumed/ (guarda call_id) ─▶ pass
     │                                                       regla approval.consumed, decided_by python
     ├─ ¿consumed/<id> con el mismo call_id? ─────── sí ──▶ pass (evento duplicado de Codex, H-02)
     │
     └─ no ──▶ escribir pending/<id> ─▶ deny con el texto de aprobación (§6.3)

Terminal del usuario: python3 "<plugin_root>/scripts/synapse.py" approve <id>
     └─ muestra hook, regla, motivo, preview, cwd ─▶ exige confirmación en un TTY ─▶ pending → approved
```

- Una aprobación **nunca** convierte un `block` en `allow`: solo aplica a verdicts `ask`.
- **Solo Codex** usa este flujo. En los demás hosts el `ask` es nativo.

### 6.3 Texto del `deny`

```text
Synapse · <hook> (<motor>) · regla <regla>: <motivo>
Requiere confirmación del usuario. Codex no permite preguntar desde un hook, así que la aprobación es manual:
  ejecuta en TU terminal (fuera del agente):  python3 "<plugin_root>/scripts/synapse.py" approve <id>
  (vence en 30 min; aprueba una sola ejecución de este mismo comando)
Agente: no intentes aprobarlo, reformular el comando ni rodear la regla. Informa al usuario y espera su respuesta.
```

### 6.4 Protección contra la Auto-Aprobación

| Defensa | Regla |
| :--- | :--- |
| `block_dangerous` bloquea de forma determinista cualquier subcomando que invoque `synapse.py approve`, `synapse approve` o un alias que resuelva al script (`python… …/scripts/synapse.py approve`), en **todos** los hosts | `structure.self_approval` (block) |
| Escribir o borrar bajo `SYNAPSE_STATE_DIR` desde shell. Ya está fuera del proyecto, así que aplica `structure.outside_project` | Existente |
| `protect_files` bloquea escrituras (`apply_patch`, `write_to_file`…) con destino bajo `SYNAPSE_STATE_DIR` | `path.synapse_state` (block) |
| `synapse.py approve` exige `sys.stdin.isatty()` y una confirmación `y/N`. Sin TTY se niega y lo registra (`approve.no_tty`) | Defensa adicional; no se depende solo de ella |

---

## 7. Adaptadores por Host

### 7.1 Codex: `adapters/codex/hooks.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "^(Bash|apply_patch)$",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$PLUGIN_ROOT/hooks/dispatch.py\" --host codex",
            "commandWindows": "\"%PLUGIN_ROOT%\\hooks\\run-hook.cmd\" dispatch --host codex",
            "timeout": 30,
            "statusMessage": "Synapse"
          }
        ]
      }
    ]
  }
}
```

- `matcher` usa los nombres nativos. Los alias `Edit`/`Write` de `apply_patch` no se usan, para que el filtro no dependa de ellos.
- **V-03:** hay que confirmar qué shell ejecuta `commandWindows` (cmd o PowerShell) y ajustar las comillas y la expansión de `PLUGIN_ROOT`.
- Si `python3` no existe en Linux, el comando falla y Codex **falla abierto**. `synapse doctor` lo detecta, y el README lo pone como requisito. Usar el lanzador también en Linux queda como alternativa si V-03 muestra que no agrega latencia.

### 7.2 Antigravity: `hooks.json` en la Raíz del Plugin

```json
{
  "synapse": {
    "enabled": true,
    "PreToolUse": [
      {
        "matcher": "^(run_command|view_file|write_to_file|replace_file_content|multi_replace_file_content)$",
        "hooks": [
          { "type": "command", "command": "hooks/run-hook.cmd dispatch --host antigravity", "timeout": 30 }
        ]
      }
    ]
  }
}
```

- El cwd del hook es la raíz del plugin. `${PLUGIN_ROOT}` no se expande dentro de `command`, así que se usan rutas relativas. En Windows el comando va tal cual a `cmd.exe`.
- Se usa el lanzador también en Linux, porque es la única forma de garantizar una salida JSON válida si falta el intérprete (§8).
- **V-04:** confirmar que `cmd.exe` resuelve `hooks/run-hook.cmd` con barra normal. Si no, se usa `hooks\run-hook.cmd` con un `commandWindows` equivalente, si Antigravity lo admite, o un `hooks.json` generado por plataforma en el release.
- **V-05:** confirmar con `agy plugin validate` y un E2E que el formato indexado por nombre es el que carga (H-13).
- Regla de Antigravity: se agrega a `rules/security-guardrails.md` el frontmatter `---\ntrigger: always_on\ndescription: Política de guardrails de Synapse\n---`. Claude Code ignora esas claves (verificar con `claude plugin validate --strict`).

### 7.3 OpenCode V2

`adapters/opencode/index.ts` debe cumplir lo siguiente. Es el contrato; el código final puede diferir:

```ts
import { Plugin } from "@opencode/plugin"
import { spawn } from "node:child_process"
import { fileURLToPath } from "node:url"
import path from "node:path"

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..")
const TOOLS = new Set(["shell", "bash", "read", "write", "edit", "patch"])
const TIMEOUT_MS = 15_000

export default Plugin.define({
  id: "bypabloc.synapse",
  async setup(ctx) {
    const python = String(ctx.options?.python ?? (process.platform === "win32" ? "python" : "python3"))
    ctx.tool.hook("execute.before", async (ev) => {
      if (!TOOLS.has(ev.tool)) return
      const payload = {
        tool: ev.tool, input: ev.input, sessionID: ev.sessionID, callID: ev.id,
        directory: ctx.location.directory, project: ctx.location.project?.directory,
      }
      const verdict = await runDispatch(python, payload)   // { verdict, reason, target, hook, rule } | { error }
      if (verdict.verdict === "block") throw new Error(verdict.reason)
      if (verdict.verdict === "ask" || "error" in verdict) {
        await ctx.permission.assert({
          sessionID: ev.sessionID, agent: ev.agent,
          source: { type: "tool", messageID: ev.messageID, id: ev.id },
          action: "synapse", resources: [verdict.target ?? ev.tool],
          metadata: { reason: verdict.reason ?? `Synapse no pudo evaluar (${verdict.error}): confirma manualmente` },
        })
      }
    })
  },
})
```

- `runDispatch` ejecuta `spawn(python, [ROOT + "/hooks/dispatch.py", "--host", "opencode"])` con el JSON por stdin y un timeout de 15 s. Resuelve `{error}` ante spawn fallido, timeout, exit ≠ 0 o JSON inválido. **Nunca** resuelve `pass` por un error.
- `ctx.options.python` permite fijar el intérprete: `["@bypabloc/synapse@git+…", {"python": "C:/…/python.exe"}]`.
- **Latencia:** se mide en T-26. El objetivo es p95 < 150 ms sin Laya, por llamada a una tool vigilada. Si no se cumple, el spec 002 evalúa un proceso Python persistente (reutilizar el daemon de Laya como servidor de `dispatch`).
- `ev.tool === "bash"` se acepta como alias de `shell` (OpenCode ≥ 2.2.5 ejecuta `bash` como `shell`).

---

## 8. Lanzador e Intérprete (Windows y Linux)

`hooks/run-hook.cmd` es un script políglota: bash lo ejecuta como shell script y `cmd.exe` como batch. Es el patrón de superpowers ([05 · H-05](./05-referencias.md#2-hallazgos-que-afectan-a-este-spec)).

- **Uso:** `run-hook.cmd <entrada> --host <h>`, donde `<entrada>` es `dispatch` o el nombre de un hook.
- **Búsqueda de intérprete:**
  - Linux: `SYNAPSE_PYTHON`, `python3`, `python`.
  - Windows: `SYNAPSE_PYTHON`, `py -3`, `python`, `python3`.
  - Se descarta el alias de Microsoft Store: se exige que `--version` responda `Python 3.1x`.
- **Sin intérprete válido:** emite la salida de seguridad del host y sale con 0.
  - Antigravity: `{"decision":"force_ask","reason":"Synapse: no se encontró Python 3.10+ …"}`.
  - Codex: `deny` con el mismo motivo.
  - OpenCode no usa el lanzador: el shim tiene su propia ruta de error.
- **Permisos:** 0755 en el repo (`git update-index --chmod=+x`). Un test verifica el bit.

---

## 9. Windows: Cobertura Mínima de PowerShell y cmd

En Windows, Codex y Antigravity ejecutan PowerShell o cmd (V-07 confirma cuál usa cada host). El analizador de Synapse entiende bash. **Este spec define un mínimo determinista**; la cobertura completa queda para el spec 002.

| Patrón (sin distinguir mayúsculas) | Verdict | Regla |
| :--- | :--- | :--- |
| `Remove-Item` / `rm` / `ri` / `del` / `erase` / `rd` / `rmdir` con `-Recurse`, `-r`, `/s` o `-Force` sobre una ruta fuera de `./tmp/` | ask | `windows.destructive` |
| `Format-Volume`, `diskpart`, `format <unidad>:`, `Clear-Disk` | block | `windows.disk` |
| `iex`/`Invoke-Expression` combinado con `iwr`/`irm`/`Invoke-WebRequest`/`Invoke-RestMethod`/`DownloadString` | block | `windows.remote_exec` |
| `Get-Content`/`gc`/`type`/`cat`/`Select-String` sobre un archivo `.env` real | block | `block_env_read` (`env.read`) |
| `git push --force`, `git reset --hard` (mismos patrones `ask` actuales) | ask | Existente |
| Cualquier otro comando PowerShell | Laya (si está encendida) o `pass` | — |

La detección de dialecto corre solo cuando el host está en Windows (`os.name == "nt"`) y el comando no se parsea como bash simple o contiene cmdlets (`\b[A-Z][a-z]+-[A-Z][a-z]+\b`). El README declara **cobertura parcial en Windows**.

---

## 10. CLI de Usuario: `scripts/synapse.py`

| Subcomando | Qué hace |
| :--- | :--- |
| `approve <id>` | §6.2. Muestra el detalle y exige TTY y confirmación |
| `approve --list` | Pendientes y aprobadas vigentes |
| `doctor [--host h]` | Revisa intérprete y versión, `run-hook.cmd` ejecutable, manifiestos presentes, delta de Laya (contenido real o puntero LFS), daemon de Laya, directorio de logs escribible y, por host, la versión del CLI instalado contra la mínima ([README §6](./README.md#6-versiones-mínimas-por-host)). Con `--payload archivo.json`, compara la forma real del payload con la declarada por `--host` (detección solo diagnóstica, [05 §3](./05-referencias.md#3-estándar-adoptado)) |
| `log …` | Alias de `scripts/synapse_log.py` con `--host` |

Las skills `synapse-status` y la regla mencionan `synapse doctor` y dejan de mencionar `${CLAUDE_CONFIG_DIR}`.

---

## 11. Rutas Neutrales

| Concepto | Resolución |
| :--- | :--- |
| Raíz del proyecto (`allowed_roots`) | `event.project_dir` (§4.1). El cálculo de raíces (`_roots_for`) no cambia |
| Memoria de Claude como raíz permitida | Solo `host == "claude"` |
| Raíz del plugin | `Path(__file__).resolve().parents[1]`. Ya no se lee `CLAUDE_PLUGIN_ROOT` dentro del código |
| Logs | `SYNAPSE_LOG_DIR` → si `host == "claude"`: `${CLAUDE_CONFIG_DIR:-~/.claude}/logs/synapse` (sin cambios); si no: `<SYNAPSE_STATE_DIR>/logs`. `synapse_log.py` lee ambos directorios por defecto y filtra con `--host` |
| Config por proyecto | `.synapse/commands.json` y `.synapse/secrets.json` (neutros), con respaldo en `.claude/synapse-commands.json` y `.claude/synapse-secrets.json`. Si existen ambos, gana el neutro y la traza registra `config.legacy_ignored` |
| Estado (aprobaciones) | `SYNAPSE_STATE_DIR` (§6.1) |
| Daemon de Laya | La clave del socket pasa de "ruta de instalación" a `sha256(versión + sha256 del delta)`. Así un mismo Synapse instalado en Claude, Codex y OpenCode **comparte un solo daemon** y una sola copia del modelo en VRAM. La ruta del socket no cambia (`$XDG_RUNTIME_DIR/synapse/`). En Windows, donde no hay sockets Unix en todos los hosts, se usa un puerto TCP en `127.0.0.1` con token en archivo (V-09) |

---

## 12. Reglas Nuevas o Ajustadas

| # | Regla | Verdict | Detalle |
| :--- | :--- | :--- | :--- |
| R-01 | `structure.self_approval` | block | §6.4 |
| R-02 | `path.synapse_state` | block | §6.4 |
| R-03 | Archivos de gobierno por host (`protect_files`) | ask | Codex: `.codex/config.toml`, `.codex/hooks.json`, `.codex/rules/*.rules`, `.codex/agents/*.toml`, `AGENTS.override.md`, `.agents/plugins/marketplace.json`. Antigravity: `.agents/hooks.json`, `.agents/mcp_config.json`, `.agents/plugins.json`, `.agents/rules/**`. OpenCode: `opencode.json`, `opencode.jsonc`, `.opencode/plugins/**`, `.opencode/tools/**`. Synapse: `.synapse/**` |
| R-04 | `git` que escribe en un directorio objetivo | block si el destino está fuera del proyecto | **Brecha encontrada el 2026-11-20:** `git clone <url> <dir>` y `git -C <dir> remote set-url …` hacia afuera del proyecto **no se bloquearon**. Se evalúa como escritura en `<dir>`: el destino de `clone` e `init`, y `-C <dir>` (o `--git-dir`/`--work-tree`) con un subcomando que escribe (`config`, `remote add\|set-url\|remove`, `commit`, `checkout`, `switch`, `reset`, `merge`, `rebase`, `pull`, `fetch`, `worktree add`, `init`, `apply`, `am`, `stash`). Va con caso en `tests/cases/block_dangerous.json` |
| R-05 | `structure.agent_wrapper` | ask | Un agente que lanza otro agente sin los guardrails del host actual: `codex exec`, `claude -p`, `opencode run`, `agy` con prompt no interactivo, `gemini -p`. Si además lleva flags que apagan protecciones (`--dangerously-*`, `--yolo`, `--dangerously-bypass-hook-trust`, `--dangerously-bypass-approvals-and-sandbox`), el verdict es **block**. `is_dev_routine` los excluye de forma explícita |
| R-06 | `windows.*` | §9 | |

---

## 13. Traza JSONL

Campos nuevos (los existentes no cambian):

| Paso | Campos |
| :--- | :--- |
| `input` | `host`, `kind`, `tool` (nativo), `call_id`, `files` (solo rutas y `op`, nunca contenido) |
| `normalize.error` | `error`, `keys` (claves de primer nivel del payload) |
| `patch.parse_error` | `error`, `chars` |
| `dispatch` | `hooks`, `verdicts` |
| `decision` | Además: `emitted` (si difiere de `decision`) y `approval_id` |
| `approval` | `action` (`pending`, `consumed`, `replayed`, `expired`), `id` |

`scripts/learn_from_log.py` y `scripts/benchmark.py` aceptan `--host` y por defecto incluyen todos los hosts.

---

## 14. Compatibilidad y No Regresión

- **Claude:** `tests/cases/*.json`, `tests/unit` y `tests/e2e` sin cambios de expectativa. Se agrega un test que compara la salida de 1.6.1 y 1.7.0 byte a byte sobre todos los casos (golden capturado antes de tocar el código, en T-20).
- **Laya:** no cambian la pregunta, la entrada ni la calibración. `--laya gpu` en verde.
- `python3 -m pytest` y `python3 -m pytest --laya gpu` siguen siendo el gate (AGENTS.md §6).

---

## 15. Verificaciones Pendientes (Synapse)

| Id | Host | Pregunta | Cómo se responde | Si la respuesta es negativa |
| :--- | :--- | :--- | :--- | :--- |
| V-01 | Codex | Forma de `Bash.tool_input` (¿`command` string o lista? ¿`workdir`?) y si unified exec dispara siempre `PreToolUse` | Sonda F0 | Ajustar `normalize` |
| V-02 | Codex | ¿`additionalContext` sin `permissionDecision` en `PreToolUse`? | Sonda F0 y E2E | `context.dropped` |
| V-03 | Codex | Shell que ejecuta `commandWindows`, expansión de `PLUGIN_ROOT` en Windows y Linux | Sonda F0 en Windows | Ajustar el comando |
| V-04 | Antigravity | `cmd.exe` con `hooks/run-hook.cmd` relativo | E2E en Windows | `hooks.json` por plataforma generado en el release |
| V-05 | Antigravity | Formato del `hooks.json` del plugin (por nombre o `{hooks}`) | `agy plugin validate` y E2E | Cambiar el formato |
| V-06 | Antigravity | Campos de `ReplacementChunks` | Sonda F0 | Mantener el modo conservador |
| V-07 | Codex, Antigravity | Shell de los comandos del agente en Windows (PowerShell, cmd o bash) | Sonda F0 | Ajustar §9 |
| V-08 | Antigravity | ¿Hooks en el IDE standalone? | Prueba manual en IDE 2.8 | Documentar "solo CLI y App" |
| V-09 | Todos | Sockets Unix disponibles para el daemon de Laya en Windows nativo | Prueba en Windows | TCP local con token |
| V-10 | OpenCode | Firma real de `ctx.permission.assert` y de `ev` en `execute.before` (2.3.2) | Tipos de `@opencode/plugin` y sonda | Ajustar el shim |
| V-11 | OpenCode | Instalación desde un subdirectorio de Git | Prueba | `package.json` en la raíz (ya previsto) |
