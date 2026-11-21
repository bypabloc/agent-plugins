# AGENTS.md — Monorepo agent-plugins

Manual para agentes y personas que trabajan en este repo. Cada plugin tiene su propio manual, que manda sobre su
lógica:
- [`plugins/synapse/AGENTS.md`](plugins/synapse/AGENTS.md)
- [`plugins/session-handoff/AGENTS.md`](plugins/session-handoff/AGENTS.md)
- [README de spanish-latam-style](plugins/spanish-latam-style/README.md)

## 1. Qué Hay Aquí

| Ruta | Contenido |
| :--- | :--- |
| `plugins/synapse/` | Guardrails de seguridad (Python + Laya). Espejo: `bypabloc/agent-plugin-synapse` |
| `plugins/session-handoff/` | Handoff de sesión (TypeScript, mod de Claude Code + CLI Node). Espejo: `bypabloc/agent-plugin-session-handoff` |
| `plugins/spanish-latam-style/` | Español neutro latinoamericano (Claude Code; Codex ejecuta sus hooks). Espejo: `bypabloc/claude-plugin-spanish-latam` |
| `.claude-plugin/marketplace.json` | Marketplace `bypabloc-agents` para Claude Code y Codex (fuentes relativas) |
| `scripts/` | `bump.py` (versiones), `release.py` (release y espejos), `vigilancia.py` (colector), `actualizar_instalaciones.py` (todos los CLI tras un release) |
| `docs/research/` | Investigación centralizada: hosts (`multi_agent_support`), plugins de Claude (`claude_plugins`), Laya |
| `docs/vigilancia/` | Proyectos vigilados (`proyectos.json`) y reportes de cada revisión |
| `plugins/<x>/docs/bitacora/` | Una entrada por versión, vigilancia propia, aprendizajes y mejoras pendientes |
| `tools/probe/`, `tools/fake-llm/` | Sondas de payload de cada host y LLM falso para los E2E |
| `.claude/rules/`, `.claude/skills/` | Reglas siempre activas y skills `vigilar-plugins` y `reparar-plugin` |

## 2. Reglas

1. **Los cambios se hacen solo aquí.** Los espejos reciben `git subtree split` en cada release y nunca commits directos.
2. **Flujo:** `feature/<NNN>-<tema>` o `fix/<plugin>-<tema>` → PR a `dev` → PR de `dev` a `main`. El release es un
   tag `<plugin>-v<semver>` sobre `main`.
3. **Commits:** Conventional Commits con el plugin como scope (`feat(synapse): …`, `fix(session-handoff): …`,
   `chore(repo): …`, `docs(repo): …`).
4. **Idioma:** documentación, commits y logs en español latinoamericano neutro. Identificadores de código en inglés.
5. **Archivos temporales** solo en `./tmp/` (está en `.gitignore`). Nunca en `/tmp` del sistema.
6. **Claude Code sin regresiones.** El golden de Synapse (`tests/golden/claude-1.6.1.json`) y los tests de
   `register.tsx` fijan la salida en Claude Code. Solo cambian para sumar casos nuevos.
7. **Versiones:** se cambian solo con `scripts/bump.py <plugin> <versión>`, y `scripts/bump.py --check` debe pasar.
   Cada versión lleva su archivo en `plugins/<x>/docs/bitacora/versiones/`.
8. **Autosuficiencia:** ningún plugin deja a un agente detenido sin decirle cómo seguir. Detalle en
   [`.claude/rules/plugins.md`](.claude/rules/plugins.md).
9. **Toda reparación termina publicada e instalada** (decisión del usuario, 2026-11-21). Con la CI en verde, el
   agente fusiona a `dev`, luego a `main`, etiqueta cada plugin con versión nueva y ejecuta
   `scripts/actualizar_instalaciones.py --apply` en todos los CLI y perfiles. Pasos y límites en
   [`.claude/rules/vigilancia.md`](.claude/rules/vigilancia.md) y en la skill `reparar-plugin`.

## 3. Decisiones Vigentes

Se tomaron con el usuario en el spec 001 (2026-11-20), que ya está implementado y archivado (ver §8).

| # | Decisión |
| :--- | :--- |
| D-01 | Este monorepo es la fuente de verdad. Los espejos se generan con `git subtree split` en cada release |
| D-02 | Nombres neutros `agent-plugin-*` (renombrados desde `claude-plugin-*`; GitHub redirige las URLs viejas) |
| D-04 | **Codex `ask`**: es un `deny` con id de un solo uso. El usuario ejecuta `synapse approve <id>` en su terminal; el agente nunca puede aprobar |
| D-05 | **Antigravity**: un error interno de Synapse emite `force_ask`, porque ahí un exit ≠ 0 equivale a permitir |
| D-06 | OpenCode: solo V2 |
| D-07 | Claude Code es host de primera: el mod de session-handoff y los hooks de Synapse no cambian de comportamiento |
| D-08 | session-handoff fuera de Claude Code y OpenCode corre como un JS empaquetado (`dist/hook.mjs`) con `node` ≥ 20 |
| D-09 | El host se **declara** (`--host <h>` o argumento del CLI) en cada cableado. Nunca se autodetecta |
| D-10 | El `name` de cada plugin no cambia: conserva namespaces e instalaciones existentes |
| D-11 | (2026-11-21) El marketplace es `bypabloc-agents`, en este repo. `bypabloc/claude-plugins` queda solo como historia |

## 4. Versiones Mínimas por Host

| Host | Mínima | Probada | Motivo |
| :--- | :--- | :--- | :--- |
| Claude Code | 2.1.287 | 2.1.329 | API de mods (session-handoff) |
| Codex CLI | 0.171.0 | 0.171.0 | Autoactualización de marketplaces; fixtures capturados en esta versión |
| Antigravity CLI (`agy`) | 1.5.4 | 1.5.13 | `cwd`, `hookEventName` y `toolCall.id` en stdin; `PLUGIN_ROOT` en hooks |
| OpenCode | 2.3.0 | 2.3.2 | `Plugin.define` estable; `bash` pasó a llamarse `shell` (2.2.5) |
| Node / Python | 20 / 3.10 | 24–26 / 3.12 | ESM y `node:fs/promises` / tipado de Synapse |

## 5. Pruebas

```bash
# Synapse (desde plugins/synapse)
python -m pytest                  # determinista: unit + e2e (en Windows, lo POSIX es xfail)
python -m pytest --laya gpu       # con Laya en GPU (local)

# session-handoff (desde plugins/session-handoff)
claude plugin test .              # hooks/*.test.ts: importan claude-code/testing, no corren con bun test
bun test tests/cli && bun run build && git diff --exit-code dist/

# spanish-latam-style (desde plugins/spanish-latam-style)
python -m pytest

# Todo el repo (desde la raíz)
python scripts/bump.py --check
python -m pytest scripts/tests
claude plugin validate --strict plugins/<x>   # y `claude plugin validate --strict .` para el marketplace
```

En Windows, con una consola cp1252, exporta `PYTHONUTF8=1` antes de usar los scripts que imprimen `✓`.

Para probar sin publicar:

| Host | Cómo |
| :--- | :--- |
| Claude Code | `claude --plugin-dir ./plugins/synapse` |
| Codex | `codex plugin marketplace add ./` y luego `codex plugin add synapse@bypabloc-agents` |
| Antigravity | `agy plugin install ./plugins/synapse` |
| OpenCode | `"plugins": ["./plugins/synapse"]` en el `opencode.json` del proyecto de prueba |

## 6. Release

```bash
python scripts/release.py synapse 1.7.1 --pr   # bump, rama release/… y PR a dev
# tras el merge a main:
git tag synapse-v1.7.1 && git push origin synapse-v1.7.1   # release.yml publica el espejo (fast-forward + LFS)
python scripts/actualizar_instalaciones.py --apply          # todos los CLI y perfiles (Windows y WSL)
```

- El split debe ser fast-forward. Si el `main` del espejo no es ancestro del split, el job falla: nadie empuja al
  espejo por fuera del release.
- Secretos de la CI: `MIRROR_DEPLOY_KEY_SYNAPSE`, `MIRROR_DEPLOY_KEY_HANDOFF` y `MIRROR_DEPLOY_KEY_SPANISH` (deploy
  keys con escritura, una por espejo).
- `python scripts/release.py --mirror <plugin>` publica el espejo en local, para emergencias, con la llave personal
  (`core.sshCommand "ssh -i ~/.ssh/pacg1991 -o IdentitiesOnly=yes"`). Sin `--push` es un dry-run.

**Después de publicar, por host:**

| Host | Cómo se actualiza |
| :--- | :--- |
| Claude Code | `claude plugin marketplace update bypabloc-agents && claude plugin update <plugin>@bypabloc-agents` en cada perfil (`CLAUDE_CONFIG_DIR`) y cada scope `project`; `/reload-plugins` en las sesiones abiertas |
| Codex | `codex plugin marketplace upgrade` y luego `/hooks` para **volver a confiar**: Codex ata los hooks al hash de los scripts |
| Antigravity | `agy plugin install https://github.com/bypabloc/agent-plugin-<x>` (no hay `update` para instalaciones por URL) |
| OpenCode | Con `#vX.Y.Z` fijado, se cambia la referencia; con `#main`, se actualiza al arrancar |

## 7. Vigilancia

El repo vigila los plugins en los proyectos reales que los usan y los repara con evidencia. Ver
[`docs/vigilancia/README.md`](docs/vigilancia/README.md) y [`.claude/rules/vigilancia.md`](.claude/rules/vigilancia.md).

```bash
python scripts/vigilancia.py --since 6h   # Windows + WSL, solo lectura
```

## 8. Historia

- El diseño multi-agente (spec 001) está archivado en el tag
  [`synapse-v1.7.0`](https://github.com/bypabloc/agent-plugins/tree/synapse-v1.7.0/docs/specs/001-plugins-multi-agente).
  Las referencias `spec 001 · NN §X` en comentarios del código apuntan a esos documentos.
- `plugins/synapse` y `plugins/session-handoff` se importaron con su historia completa desde `claude-plugin-*`;
  `plugins/spanish-latam-style`, desde `claude-plugin-spanish-latam`, también con su historia.

## 9. LFS

`plugins/synapse/models/*.safetensors` (el delta de Laya, unos 100 MB) va por Git LFS. Tras clonar:
`git lfs install --local && git lfs pull`. Al publicar un espejo, el split necesita también `git lfs push`.
