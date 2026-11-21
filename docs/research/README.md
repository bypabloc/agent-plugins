# Investigación

Investigación técnica que sirve a los plugins del monorepo. Vive centralizada aquí: los plugins enlazan a esta
carpeta en vez de tener una copia propia.

| Carpeta | Tema | Empezar por |
| :--- | :--- | :--- |
| [`multi_agent_support/`](./multi_agent_support/README.md) | Extensibilidad de Codex, Antigravity, Gemini CLI, OpenCode, Cursor, Copilot y Herdr comparada con Claude Code; guía y casos de estudio de synapse y session-handoff | [`01-panorama…`](./multi_agent_support/01-panorama-y-matrices-por-componente.md) |
| [`claude_plugins/`](./claude_plugins/README.md) | Arquitectura, componentes, marketplaces, testing y antipatrones de los plugins de Claude Code | [`README.md`](./claude_plugins/README.md) |
| [`laya/`](./laya/01-panorama-e-indice.md) | Laya (`convaiinnovations/laya`), el clasificador System 1 que usa Synapse: arquitectura, uso, despliegue, rendimiento y fine-tuning | [`01-panorama-e-indice.md`](./laya/01-panorama-e-indice.md) |

## Notas

- `claude_plugins/` se escribió cuando los plugins vivían en `claude-plugins` y `claude-plugin-spanish-latam`. Esos
  repos ya no son la fuente: hoy todo está en [`plugins/`](../../plugins/) de este monorepo.
- `multi_agent_support/` tiene fecha de corte 2026-11-19. Antes de basar un cambio en ella, confirma la versión del
  host contra su changelog.
- Una investigación nueva va en `docs/research/<tema>/` con un `README.md` o un `01-…` de índice, y se suma a esta tabla.
