# 06 · Tareas

> El orden es el de ejecución. Cada tarea es un commit o un PR pequeño con Conventional Commits y scope (`feat(synapse): …`, `chore(repo): …`). **Dep** = tareas que deben estar cerradas antes. Un lote: un solo handoff (`tmp/handoff/001-plugins-multi-agente/`) y una rama por fase (`feature/001-fN-<tema>`).

```text
F0 Repo ──▶ F1 Sondas ──┬──▶ F2 Synapse núcleo ──┬──▶ F3 Codex ──▶ F4 Antigravity ──▶ F5 OpenCode ─┐
                         │                         │                                                 ├──▶ F10 Docs y release
                         └──▶ F6 Handoff núcleo ───┴──▶ F7 Codex ──▶ F8 Antigravity ──▶ F9 OpenCode ─┘
```

F2 y F6 pueden avanzar en paralelo. Dentro de cada plugin, el orden de hosts va de menor a mayor esfuerzo: Codex (formato cercano a Claude), Antigravity (bloqueo solo por JSON) y OpenCode (TS en proceso).

---

## F0 · Repo y Publicación

| Id | Tarea | Dep | Cierre |
| :--- | :--- | :--- | :--- |
| T-00 | ✅ Monorepo creado con la historia de ambos plugins, investigación movida a `docs/research/`, repos renombrados a `agent-plugin-*` y CLI actualizados en WSL y Windows (2026-11-20) | — | Hecho |
| T-01 | **Usuario:** `git clone git@github.com:bypabloc/agent-plugins.git ~/projects/bypabloc/agent-plugins` (con `core.sshCommand` de la llave personal y `git lfs install --local && git lfs pull`), y borrar `~/projects/bypabloc/agent-plugins-probe-clone` | — | Clon local con el delta de Laya real |
| T-02 | `AGENTS.md` del monorepo ([01 §9](./01-repos-y-publicacion.md#9-agentsmd-del-monorepo)) | — | Archivo revisado |
| T-03 | Primer split hacia los espejos. Antes, `README.md` de cada plugin con el aviso "espejo de agent-plugins". Verificar fast-forward, `git lfs push`, borrar las ramas viejas fusionadas del espejo (listar las no fusionadas en el PR), proteger `main` del espejo y crear las deploy keys | T-02 | Los dos espejos tienen en `main` el split actual, solo `main` y tags, y `main` protegido |
| T-04 | Descripciones y URLs neutras: `homepage` y `repository` a `agent-plugin-*`, sin "para Claude Code", y `marketplace-entry.json` con fuente `url` | — | `claude plugin validate --strict` en verde |
| T-05 | `.claude-plugin/marketplace.json` del monorepo (`bypabloc-agents`, fuentes relativas) | T-04 | Se instala en Claude (`--plugin-dir` y marketplace) y en Codex (`codex plugin marketplace add ./`) |
| T-06 | `scripts/bump.py` y `.version-bump.json` por plugin (`--check`, `--audit`) | — | Test que falla ante una versión distinta |
| T-07 | `scripts/release.py` y `.github/workflows/release.yml` ([01 §6](./01-repos-y-publicacion.md#6-release-y-espejos)) | T-03, T-06 | Dry-run publica a un espejo de prueba |
| T-08 | `.github/workflows/ci.yml` base: tests actuales de ambos plugins en ubuntu y windows, y `bump --check` | T-06 | CI verde en `dev`. Los tests que fallen en Windows se documentan, se marcan `xfail` con issue y no se ocultan |

## F1 · Sondas y Fixtures

| Id | Tarea | Dep | Cierre |
| :--- | :--- | :--- | :--- |
| T-10 | `tools/probe/` ([04 §2](./04-pruebas-y-verificacion.md#2-sondas-de-payload-toolsprobe)) | — | La sonda se instala en los tres hosts |
| T-11 | Ver si `agy` y `codex` se pueden instalar en los runners de GitHub, para `agy plugin validate` y los schemas | — | Decisión anotada en DECISIONS.md del handoff |
| T-12 | Capturas en **WSL**: escenarios S-01…S-11 × 3 hosts | T-10 | Fixtures sanitizados |
| T-13 | Capturas en **Windows**: mismos escenarios (incluido S-10) | T-10 | Fixtures sanitizados |
| T-14 | Responder V-01…V-28 editando sus filas en este spec, y versionar los fixtures | T-12, T-13 | Ninguna V-xx sin respuesta o decisión |
| T-15 | Catálogo `bypabloc/claude-plugins`: entradas `synapse` y `session-handoff` con fuente `url` a los espejos, borrar las copias `plugins/synapse` y `plugins/session-handoff`, y actualizar la memoria del flujo de release | T-03 | `claude plugin marketplace update bypabloc && claude plugin update synapse@bypabloc` instala desde el espejo |

## F2 · Synapse: Núcleo Neutral

| Id | Tarea | Dep | Cierre |
| :--- | :--- | :--- | :--- |
| T-20 | Golden de Claude 1.6.1 (`tests/golden/claude-1.6.1.jsonl`) **antes de tocar código** | — | Test golden en verde sobre 1.6.1 |
| T-21 | `hosts.py`: modelo (§3), emisores `single`/`collect` y `normalize("claude")`. `emit_decision`/`emit_block` delegan en el emisor | T-20 | Golden idéntico |
| T-22 | `patch.py` con sus tests (Add, Update, Move, Delete, malformado) | — | Unit en verde |
| T-23 | `evaluate(event)` y filtro por `kind` en los 4 hooks | T-21 | Golden idéntico |
| T-24 | `dispatch.py` con combinación por precedencia y `try/except BaseException` total | T-21, T-23 | Unit en verde |
| T-25 | Rutas neutrales: `project_dir`, plugin root desde `__file__`, logs por host, `.synapse/` con respaldo `.claude/`, estado y clave del daemon de Laya ([02 §11](./02-synapse.md#11-rutas-neutrales)) | T-21 | Golden idéntico. `--laya gpu` en verde. Dos instalaciones de la misma versión comparten daemon |
| T-27 | Reglas R-01…R-05 ([02 §12](./02-synapse.md#12-reglas-nuevas-o-ajustadas)) con casos en `tests/cases/*.json`. R-04 cierra la brecha de `git clone` y `git -C` | T-23 | Casos nuevos en verde. Golden de los casos viejos idéntico |
| T-28 | Mínimo de Windows ([02 §9](./02-synapse.md#9-windows-cobertura-mínima-de-powershell-y-cmd)) | T-23, T-14 (V-07) | Casos `windows.*` en verde |
| T-29 | `scripts/synapse.py` (`doctor`, `log`; `approve` va en T-31) | T-25 | `doctor` reporta un puntero LFS, falta de intérprete y versión de CLI |

## F3 · Synapse en Codex

| Id | Tarea | Dep | Cierre |
| :--- | :--- | :--- | :--- |
| T-30 | `.codex-plugin/plugin.json`, `adapters/codex/hooks.json`, `normalize("codex")` y emisión Codex ([02 §5.2](./02-synapse.md#52-codex)) | T-24, T-14 | Equivalencia y protocolo de Codex en verde |
| T-31 | `approvals.py` y `synapse.py approve` ([02 §6](./02-synapse.md#6-aprobación-de-un-solo-uso-codex)) | T-30 | Casos de [04 §3.3](./04-pruebas-y-verificacion.md#33-aprobación-de-un-solo-uso) en verde |
| T-32 | Contratos y schemas de Codex en `tests/schemas/codex/` | T-30 | Ninguna emisión con claves extra |
| T-33 | E2E Codex E-01…E-04 en WSL y Windows | T-31 | Escenarios en verde (o en `MANUAL.md` si el modo no interactivo no lo permite) |

## F4 · Synapse en Antigravity

| Id | Tarea | Dep | Cierre |
| :--- | :--- | :--- | :--- |
| T-34 | `.antigravity-plugin/plugin.json`, `hooks.json` raíz, `trigger: always_on` en la regla y borrar `commands/synapse-status.md` (la skill lo cubre) | T-24, T-14 | `agy plugin validate --json` sin errores y con solo los warnings permitidos. `claude plugin validate --strict` en verde |
| T-35 | `run-hook.cmd` ([02 §8](./02-synapse.md#8-lanzador-e-intérprete-windows-y-linux)), con su bit 0755 | — | Protocolo en Linux y Windows. Sin intérprete emite `force_ask` |
| T-36 | `normalize("antigravity")` y emisión con `force_ask` ante errores (D-05) | T-34 | Equivalencia y protocolo en verde, incluidos el payload inválido y el import roto |
| T-37 | E2E Antigravity E-01…E-04 en WSL y Windows (V-04, V-05, V-08) | T-35, T-36 | Escenarios en verde o en `MANUAL.md` |

## F5 · Synapse en OpenCode

| Id | Tarea | Dep | Cierre |
| :--- | :--- | :--- | :--- |
| T-38 | `package.json` en la raíz del plugin, `adapters/opencode/index.ts` (§7.3) y `normalize("opencode")` | T-24, T-14 (V-10) | `opencode plugin check` en verde. Equivalencia en verde |
| T-26 | Medir la latencia del shim (p50 y p95, con y sin Laya) en WSL y Windows | T-38 | Resultado en `docs/bitacora` o NOTES. Si p95 > 150 ms, se abre el spec 002 |
| T-39 | E2E OpenCode E-01…E-04 en WSL y Windows (V-11, V-14) | T-38 | Escenarios en verde |

## F6 · session-handoff: Núcleo para Hosts Externos

| Id | Tarea | Dep | Cierre |
| :--- | :--- | :--- | :--- |
| T-40 | Golden de los textos de Claude 0.4.4 **antes de tocar `handoff.ts`** | — | Golden en verde |
| T-41 | `terms.ts` y textos parametrizados ([03 §5](./03-session-handoff.md#5-textos-por-host-termsts)) | T-40 | Golden idéntico |
| T-42 | `hosts.ts`, `cli.ts` e `io-node.ts` | T-41, T-14 | Unit en verde |
| T-43 | `state.ts` (atómico, poda, idempotencia) | — | Unit en verde |
| T-44 | `actions.ts` y test de pureza de imports del núcleo | T-42, T-43 | Escenario canónico ([04 §3.2](./04-pruebas-y-verificacion.md#32-session-handoff)) en verde con `Io` en memoria |
| T-45 | Build de `dist/hook.mjs`, excepción en `.gitignore` y chequeo de bundle al día en CI | T-44 | CI verde |

## F7 – F9 · session-handoff por Host

| Id | Tarea | Dep | Cierre |
| :--- | :--- | :--- | :--- |
| T-46 | Codex: `.codex-plugin/plugin.json`, `adapters/codex/hooks.json`, emisiones y presupuesto de 8000 caracteres ([03 §6.1](./03-session-handoff.md#61-codex-adapterscodexhooksjson)), y `compact_prompt` documentado | T-45 | Protocolo en verde. E2E E-05…E-07 |
| T-47 | Antigravity: `.antigravity-plugin/plugin.json`, `hooks.json`, `headAtStart` y avisos en `Stop` ([03 §6.2](./03-session-handoff.md#62-antigravity-hooksjson-en-la-raíz)) | T-45 | `agy plugin validate`, protocolo y E2E E-05…E-07 |
| T-48 | `node dist/hook.mjs doctor` ([03 §8](./03-session-handoff.md#8-errores-y-degradación)) | T-45 | Reporta Node, bundle y vínculo |
| T-49 | OpenCode: `adapters/opencode/index.ts` con contexto, compactación, `session.idle`, `execute.after` y `question` ([03 §6.3](./03-session-handoff.md#63-opencode-v2-en-proceso)), y `tail.ts` adaptado | T-44, T-14 (V-24…V-27) | E2E E-05…E-07, incluida la compactación sin resumen |

## F10 · Documentación y Release

| Id | Tarea | Dep | Cierre |
| :--- | :--- | :--- | :--- |
| T-50 | README de cada plugin: "Qué hace en cada agente", instalación por host en WSL y Windows ([01 §7](./01-repos-y-publicacion.md#7-instalación-por-host)), limitaciones (Windows parcial en Synapse, Codex sin `ask` nativo) | T-33, T-37, T-39, T-46, T-47, T-49 | Revisado |
| T-51 | `AGENTS.md` de Synapse (protocolo multi-host, `dispatch`, aprobación, rutas) y bitácora 0.5.0 de session-handoff | T-50 | Revisado |
| T-52 | Release `synapse` 1.7.0 (`scripts/release.py`) | T-50, T-51 | Espejo con tag `v1.7.0`. El catálogo `claude-plugins` lo instala |
| T-53 | Release `session-handoff` 0.5.0 | T-50, T-51 | Espejo con tag `v0.5.0` |
| T-54 | Instalación real en el equipo del autor: 4 hosts × WSL y Windows, con humo E-01 y E-05 en cada uno | T-52, T-53 | Checklist completa en el handoff |
| T-55 | Cerrar el spec: marcarlo como implementado y mover lo diferido a "spec 002" | T-54 | Spec actualizado |

## Opcionales (fuera del criterio de cierre)

| Id | Tarea |
| :--- | :--- |
| T-91 | session-handoff: banda en slots TUI de OpenCode (`session.composer.top`) con estado, fase y `ctx %` |
| T-92 | session-handoff: `antigravity statusline` ([03 §6.2](./03-session-handoff.md#62-antigravity-hooksjson-en-la-raíz)) |
| T-93 | Statusline vía MCP de Codex (experimental, `tui_extensions_statusline`) |
| T-94 | Spec 002: cobertura completa de PowerShell en Synapse y servidor `dispatch` persistente si T-26 lo pide |
