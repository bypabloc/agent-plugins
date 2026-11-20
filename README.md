# agent-plugins

Monorepo de plugins **multi-agente** de bypabloc: un mismo plugin para **Claude Code, OpenAI Codex, Google Antigravity y OpenCode**. Es la fuente de verdad: cada plugin se publica también en su propio repo espejo, que es el que se instala.

| Plugin | Qué hace | Espejo (instalación) |
| :--- | :--- | :--- |
| [`synapse`](plugins/synapse/) | Guardrails de seguridad antes de cada tool: comandos destructivos, escrituras fuera del proyecto, lectura de `.env`, secretos y archivos protegidos (reglas deterministas + clasificador Laya) | [`bypabloc/agent-plugin-synapse`](https://github.com/bypabloc/agent-plugin-synapse) |
| [`session-handoff`](plugins/session-handoff/) | Handoff de sesión en disco: lo reinyecta al iniciar y compactar, no deja cerrar el turno con trabajo pendiente y recuerda los hashes de los commits | [`bypabloc/agent-plugin-session-handoff`](https://github.com/bypabloc/agent-plugin-session-handoff) |

> [!IMPORTANT]
> El soporte para Codex, Antigravity y OpenCode está **especificado, aún no implementado**. Hoy ambos plugins funcionan solo en Claude Code. Plan completo: [`docs/specs/001-plugins-multi-agente/`](docs/specs/001-plugins-multi-agente/README.md).

## Estructura

```text
agent-plugins/
├── plugins/synapse/              Historia completa importada de claude-plugin-synapse
├── plugins/session-handoff/      Historia completa importada de claude-plugin-session-handoff
├── docs/research/                Investigación de extensibilidad de cada agente
└── docs/specs/                   Specs numerados (001-…)
```

## Desarrollo

Los cambios se hacen **aquí**, nunca en los espejos. Cada release publica `plugins/<x>` en su espejo con `git subtree split` (ver [`docs/specs/001-plugins-multi-agente/01-repos-y-publicacion.md`](docs/specs/001-plugins-multi-agente/01-repos-y-publicacion.md)).

Licencia MIT (cada plugin incluye la suya).
