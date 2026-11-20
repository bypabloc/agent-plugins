# AGENTS.md — Monorepo agent-plugins

Manual para agentes y personas que trabajan en este repo. Cada plugin tiene además su propio manual, vigente para su lógica: [`plugins/synapse/AGENTS.md`](plugins/synapse/AGENTS.md) y el [README de session-handoff](plugins/session-handoff/README.md).

## 1. Qué Hay Aquí

| Ruta | Contenido |
| :--- | :--- |
| `plugins/synapse/` | Guardrails de seguridad (Python + Laya). Espejo: `bypabloc/agent-plugin-synapse` |
| `plugins/session-handoff/` | Handoff de sesión (TypeScript, mod de Claude Code). Espejo: `bypabloc/agent-plugin-session-handoff` |
| `.claude-plugin/marketplace.json` | Marketplace `bypabloc-agents` para Claude Code y Codex (fuentes relativas) |
| `scripts/` | `bump.py` (versiones), `release.py` (release y espejos) |
| `docs/research/` | Investigación de extensibilidad de cada agente |
| `docs/specs/NNN-…/` | Specs numerados. El activo: [`001-plugins-multi-agente`](docs/specs/001-plugins-multi-agente/README.md) |

## 2. Reglas

1. **Los cambios se hacen solo aquí.** Los espejos reciben `git subtree split` en cada release y nunca commits directos.
2. **Flujo:** `feature/<NNN>-<tema>` → PR a `dev` → PR de `dev` a `main`. El release es un tag `<plugin>-v<semver>` sobre `main`.
3. **Commits:** Conventional Commits con el plugin como scope (`feat(synapse): …`, `fix(session-handoff): …`, `chore(repo): …`, `docs(spec): …`).
4. **Idioma:** documentación, commits y logs en español latinoamericano neutro. Identificadores de código en inglés.
5. **Archivos temporales** solo en `./tmp/` (está en `.gitignore`). Nunca en `/tmp` del sistema.
6. **Claude Code sin regresiones.** Todo cambio multi-agente mantiene idéntica la salida en Claude Code (goldens del spec 001).
7. **Versiones:** se cambian solo con `scripts/bump.py <plugin> <versión>`, y `scripts/bump.py --check` debe pasar.

## 3. Pruebas

```bash
# Synapse (desde plugins/synapse)
python3 -m pytest                  # determinista: unit + e2e
python3 -m pytest --laya gpu       # con Laya en GPU (local)

# session-handoff (desde plugins/session-handoff)
claude plugin test .               # los tests importan claude-code/testing: no corren con bun test

# Todo el repo (desde la raíz)
python3 scripts/bump.py --check
claude plugin validate --strict plugins/synapse
claude plugin validate --strict plugins/session-handoff
```

## 4. Release

```bash
python3 scripts/release.py synapse 1.7.0    # bump + rama release/… + PR a dev
# tras el merge a main:
git tag synapse-v1.7.0 && git push origin synapse-v1.7.0   # release.yml publica el espejo
```

`python3 scripts/release.py --mirror <plugin>` publica el espejo de forma local, para emergencias, con la llave personal (`core.sshCommand "ssh -i ~/.ssh/pacg1991 -o IdentitiesOnly=yes"`). Detalle: [spec 001 · 01 §6](docs/specs/001-plugins-multi-agente/01-repos-y-publicacion.md#6-release-y-espejos).

## 5. LFS

`plugins/synapse/models/*.safetensors` (el delta de Laya, unos 100 MB) va por Git LFS. Tras clonar: `git lfs install --local && git lfs pull`. Al publicar un espejo, el split necesita también `git lfs push`.
