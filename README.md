# agent-plugins

Monorepo de plugins de bypabloc para agentes de código: un mismo plugin para **Claude Code, OpenAI Codex, Google
Antigravity y OpenCode**. Es la fuente de verdad: cada plugin se publica también en su propio repo espejo.

| Plugin | Qué hace | Hosts | Espejo |
| :--- | :--- | :--- | :--- |
| [`synapse`](plugins/synapse/) | Guardrails de seguridad antes de cada tool: comandos destructivos, escrituras fuera del proyecto, lectura de `.env`, secretos y archivos protegidos (reglas deterministas + clasificador Laya) | Todos | [`agent-plugin-synapse`](https://github.com/bypabloc/agent-plugin-synapse) |
| [`session-handoff`](plugins/session-handoff/) | Handoff de sesión en disco: lo reinyecta al iniciar y compactar, no deja cerrar el turno con trabajo pendiente y recuerda los hashes de los commits | Todos | [`agent-plugin-session-handoff`](https://github.com/bypabloc/agent-plugin-session-handoff) |
| [`spanish-latam-style`](plugins/spanish-latam-style/) | Español neutro latinoamericano en respuestas, documentación y commits | Claude Code (Codex ejecuta sus hooks) | [`claude-plugin-spanish-latam`](https://github.com/bypabloc/claude-plugin-spanish-latam) |

| Agente | Instalación |
| :--- | :--- |
| Claude Code | `claude plugin marketplace add bypabloc/agent-plugins` · `claude plugin install synapse@bypabloc-agents` (o `session-handoff`, `spanish-latam-style`) |
| Codex | `codex plugin marketplace add bypabloc/agent-plugins` · `codex plugin add synapse@bypabloc-agents` · `/hooks` para confiar |
| Antigravity | `agy plugin install https://github.com/bypabloc/agent-plugin-synapse` (o `…/agent-plugin-session-handoff`) |
| OpenCode | `"plugins": ["@bypabloc/synapse@git+https://github.com/bypabloc/agent-plugin-synapse.git"]` en `opencode.json` |

Versiones mínimas: Codex ≥ 0.171, `agy` ≥ 1.5.4, OpenCode V2 ≥ 2.3; Linux, WSL y Windows. Cada README trae la
instalación por agente y sus límites.

## Estructura

```text
agent-plugins/
├── plugins/<x>/                  Cada plugin, con su historia completa y su docs/bitacora/
├── docs/research/                Investigación: hosts, plugins de Claude Code, Laya
├── docs/vigilancia/              Proyectos vigilados y reportes
├── scripts/                      bump.py, release.py, vigilancia.py
└── tools/                        Sondas de payload y LLM falso para los E2E
```

## Desarrollo

Los cambios se hacen **aquí**, nunca en los espejos. Manual completo: [`AGENTS.md`](AGENTS.md) (reglas, pruebas,
release y vigilancia).

Licencia MIT (cada plugin incluye la suya).
