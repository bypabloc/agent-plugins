# Spec 001 · Plugins Multi-Agente: Synapse y session-handoff en Codex, Antigravity y OpenCode

> **Estado:** aprobado para implementar · **Fecha:** 2026-11-20 · **Autor:** Pablo Contreras
> **Plugins:** `synapse` 1.6.1 → **1.7.0**, `session-handoff` 0.4.4 → **0.5.0**
> **Base:** [`docs/research/multi_agent_support/`](../../research/multi_agent_support/README.md) (corte 2026-11-19) y [`05-referencias.md`](./05-referencias.md) (cómo lo hacen otros proyectos)

---

## 1. Objetivo

Que **Synapse** (guardrails antes de cada tool) y **session-handoff** (estado del trabajo en disco, reinyección, bloqueo del fin de turno) funcionen como plugins nativos en **OpenAI Codex**, **Google Antigravity** y **OpenCode V2**, además de Claude Code, desde un solo monorepo, **sin regresiones en Claude Code** y **sin fallar abierto** en ningún host.

## 2. Alcance

| Dentro | Fuera (specs futuros) |
| :--- | :--- |
| Codex CLI ≥ 0.171.0 (y la app de escritorio, que comparte hooks) | Cursor, Copilot, Gemini CLI, Herdr (la investigación los cubre; aquí no se implementan) |
| Antigravity CLI `agy` ≥ 1.5.13 y App (IDE standalone: solo si los hooks corren, ver verificación V-08) | OpenCode V1 (1.19.x) |
| OpenCode V2 ≥ 2.3.0 (CLI y Desktop) | Statusline MCP de Codex, paneles de la App de Antigravity, banda TUI de OpenCode (quedan como tareas opcionales T-9x) |
| WSL (Linux) y Windows nativo para los tres hosts | Reglas completas de PowerShell para Synapse (este spec solo define un mínimo, §02-synapse §9) |
| Monorepo `bypabloc/agent-plugins` + espejos `agent-plugin-synapse` y `agent-plugin-session-handoff` | Publicar en el directorio público de Codex (no admite hooks) o en el marketplace curado de Antigravity |

## 3. Decisiones Tomadas (con el usuario, 2026-11-20)

| # | Decisión |
| :--- | :--- |
| D-01 | Monorepo `bypabloc/agent-plugins` como fuente de verdad; espejos por `git subtree split` en cada release |
| D-02 | Nombres neutros `agent-plugin-*` (renombrados desde `claude-plugin-*`, historia conservada; GitHub redirige las URLs viejas) |
| D-03 | `bypabloc/claude-plugins` sigue siendo el catálogo de los demás plugins y apunta a los espejos |
| D-04 | **Codex `ask`** → aprobación de un solo uso: `deny` con un id; el usuario ejecuta `synapse approve <id>` en su terminal; el agente no puede aprobar |
| D-05 | **Antigravity**: un error interno de un hook de Synapse emite `force_ask` (un exit ≠ 0 equivale a permitir) |
| D-06 | Solo OpenCode V2 |
| D-07 | Claude Code sigue siendo host de primera: el mod de session-handoff y los hooks de Synapse no cambian de comportamiento |
| D-08 | session-handoff fuera de Claude Code y OpenCode corre como **un JS empaquetado ejecutado con `node`** (≥ 20); binarios compilados quedan fuera |
| D-09 | El host se **declara** (`--host <h>` / argumento del CLI) en cada archivo de hooks; no se autodetecta |
| D-10 | El `name` de cada plugin no cambia (`synapse`, `session-handoff`): conserva namespaces (`synapse:synapse-status`) e instalaciones existentes |

## 4. Documentos del Spec

| Archivo | Contenido |
| :--- | :--- |
| [`01-repos-y-publicacion.md`](./01-repos-y-publicacion.md) | Monorepo, espejos, manifiestos por host, marketplaces, versionado, release, CI, instalación por host |
| [`02-synapse.md`](./02-synapse.md) | Núcleo neutral (`hosts.py`, `patch.py`, `dispatch.py`), normalización y emisión por host, aprobación de un solo uso, adaptadores Codex, Antigravity y OpenCode, Windows |
| [`03-session-handoff.md`](./03-session-handoff.md) | CLI Node (`cli.ts`, `io-node.ts`, `state.ts`), textos por host, cableado Codex, Antigravity y OpenCode, compactación |
| [`04-pruebas-y-verificacion.md`](./04-pruebas-y-verificacion.md) | Sondas de payload, fixtures, matriz de equivalencia, contratos de emisión, E2E con binarios reales en WSL y Windows, CI |
| [`05-referencias.md`](./05-referencias.md) | Investigación de cómo lo hacen otros proyectos y estándar adoptado |
| [`06-tareas.md`](./06-tareas.md) | Tareas ordenadas con dependencias y criterios de cierre |

## 5. Criterios de Aceptación Globales

1. **Claude Code sin regresiones:** `tests/cases/*.json` de Synapse producen exactamente las mismas decisiones y salidas; los tests de `register.tsx` de session-handoff pasan sin cambios.
2. **Ningún host falla abierto por formato:** para cada caso canónico que en Claude es `block` o `ask`, el host emite un bloqueo o una confirmación real (tabla de emisión de [`02-synapse.md`](./02-synapse.md#5-emisión-por-host)).
3. **Instalación documentada y probada** en WSL y Windows para cada host (README de cada plugin, sección por host).
4. **Fixtures reales** capturados con las sondas (F0) para cada host y versión mínima, versionados y sanitizados.
5. **E2E reales** contra `codex`, `agy` y `opencode` en WSL y Windows: un comando destructivo se bloquea, un `ask` se confirma, un `Stop` con `Next step` pendiente continúa el turno.
6. **Release reproducible:** `scripts/release.py <plugin> <versión>` actualiza todos los manifiestos, etiqueta y publica el espejo; un test verifica que todas las versiones de un plugin coinciden.

## 6. Versiones Mínimas por Host

| Host | Mínima | Probada (2026-11-20, WSL y Windows) | Motivo del mínimo |
| :--- | :--- | :--- | :--- |
| Claude Code | 2.1.287 | 2.1.327 | API de mods (session-handoff) |
| Codex CLI | 0.171.0 | 0.171.0 | Autoactualización de marketplaces; fixtures capturados en esta versión |
| Antigravity CLI | 1.5.4 | 1.5.13 | `cwd`, `hookEventName` y `toolCall.id` en el stdin; `PLUGIN_ROOT` en hooks (1.5.3) |
| OpenCode | 2.3.0 | 2.3.2 | API `Plugin.define` estable, `bash` → `shell` (2.2.5) |
| Node | 20 | 26.10 (WSL) / 24.19 (Windows) | `node:fs/promises`, ESM |
| Python | 3.10 | 3.12 | Tipado actual de Synapse |

## 7. Glosario

- **Host:** agente que ejecuta el plugin (`claude`, `codex`, `antigravity`, `opencode`).
- **Evento interno:** representación neutral de un payload de host (`HookEvent` en Synapse, `HostEvent` en session-handoff).
- **Emisión:** traducción de una decisión interna (`block`, `ask`, `allow`, `pass`, `context`) al contrato del host.
- **Degradación:** emisión distinta a la intención cuando el host no la soporta; siempre hacia el lado seguro y registrada en la traza (`emitted`).
- **Espejo:** repo de un solo plugin generado desde el monorepo; nunca recibe commits directos.
