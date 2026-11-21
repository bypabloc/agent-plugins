# Plugins del monorepo (siempre activa)

Este repo es la **fuente única** de tres plugins. Antes de tocar uno, lee su manual: sus invariantes mandan.

| Plugin | Qué hace | Manual | Hosts |
| :--- | :--- | :--- | :--- |
| `synapse` | Guardrails antes de cada tool (Python, reglas deterministas + Laya) | [`plugins/synapse/AGENTS.md`](../../plugins/synapse/AGENTS.md) | Claude Code, Codex, Antigravity, OpenCode |
| `session-handoff` | Estado del trabajo en disco, reinyección, `Stop`, hashes (TypeScript) | [`plugins/session-handoff/AGENTS.md`](../../plugins/session-handoff/AGENTS.md) | Claude Code (mod), Codex, Antigravity, OpenCode |
| `spanish-latam-style` | Español neutro latinoamericano en respuestas, docs y commits | [`plugins/spanish-latam-style/README.md`](../../plugins/spanish-latam-style/README.md) | Claude Code (Codex ejecuta sus hooks) |

## Reglas al cambiar un plugin

- **Nunca edites los espejos** (`agent-plugin-synapse`, `agent-plugin-session-handoff`, `claude-plugin-spanish-latam`):
  reciben `git subtree split` en cada release.
- **Claude Code sin regresiones**: el golden de Synapse (`tests/golden/claude-1.6.1.json`) y `register.test.ts` de
  session-handoff no cambian salvo en casos nuevos.
- **Ningún host falla abierto**: un error interno o un payload desconocido termina en `ask` o `force_ask`, nunca en `allow`.
- **Autosuficiencia**: un plugin no debe dejar a un agente detenido sin decirle cómo seguir. En Codex, un `ask`
  detiene al agente hasta que vuelve el usuario. Cada `ask` nuevo justifica ese costo y su texto indica qué puede
  seguir haciendo el agente.
- **Codificación**: los hosts leen UTF-8. En Windows, toda salida hacia el host se escribe en UTF-8 explícito.
- **Test antes que el arreglo**: el test reproduce el síntoma real y se ve fallar.
- **Versión** solo con `scripts/bump.py`, y una entrada en `plugins/<x>/docs/bitacora/versiones/` por versión.
- **Windows y WSL**: los tests de Synapse que asumen POSIX son `xfail` en Windows. Un caso nuevo de
  `tests/cases/*.json` necesita su golden generado en WSL o Linux.

## Investigación

La investigación vive centralizada en [`docs/research/`](../../docs/research/README.md): `multi_agent_support/`
(hosts), `claude_plugins/` y `laya/`. Antes de basarte en ella, confirma la versión del host.
