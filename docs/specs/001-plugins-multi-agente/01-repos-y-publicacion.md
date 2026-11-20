# 01 · Repos, Manifiestos, Publicación e Instalación

---

## 1. Repos

| Repo | Rol | Estado al 2026-11-20 |
| :--- | :--- | :--- |
| [`bypabloc/agent-plugins`](https://github.com/bypabloc/agent-plugins) | **Fuente de verdad.** Monorepo con `plugins/synapse` y `plugins/session-handoff`, que conservan su historia completa (`git subtree add` sin squash). También tiene `docs/research` y `docs/specs` | Creado. Ramas `main` y `dev`. LFS con el delta de Laya (100 MB) |
| [`bypabloc/agent-plugin-synapse`](https://github.com/bypabloc/agent-plugin-synapse) | Espejo de `plugins/synapse` | Renombrado desde `claude-plugin-synapse`. GitHub redirige la URL vieja |
| [`bypabloc/agent-plugin-session-handoff`](https://github.com/bypabloc/agent-plugin-session-handoff) | Espejo de `plugins/session-handoff` | Renombrado desde `claude-plugin-session-handoff` |
| [`bypabloc/claude-plugins`](https://github.com/bypabloc/claude-plugins) | Catálogo de Claude Code de los demás plugins (`spanish-latam-style`…). **Deja de tener copias** de synapse y session-handoff y apunta a los espejos (T-15) | Sin cambios todavía |

**Reglas:**
1. Los cambios se hacen solo en el monorepo, con el flujo `feature/<x>` → PR a `dev` → PR a `main`.
2. Los espejos **solo** reciben `git subtree split` desde el release (§6). La rama `main` de cada espejo se protege: solo la puede actualizar el token del workflow de publicación.
3. Las ramas viejas de los espejos (`dev`, `feature/*`, `fix/*`, `chore/*`) se borran cuando se confirma que están fusionadas en el monorepo (T-03). Las que no estén fusionadas se listan en el PR de T-03 antes de borrarlas.

---

## 2. Layout de Cada Plugin y de su Espejo

Cada espejo es la carpeta del plugin con el plugin en la raíz. Ese es el layout que esperan `agy plugin install <url>` y OpenCode por Git, y el que usan superpowers, ECC y compound-engineering ([05 · H-06](./05-referencias.md#2-hallazgos-que-afectan-a-este-spec)).

### 2.1 Synapse

```text
plugins/synapse/
├── .claude-plugin/plugin.json        Claude Code (sin cambios de rutas)
├── hooks/hooks.json                  Claude Code (sin cambios: un script por hook, sin --host)
├── .codex-plugin/plugin.json         Codex. Tiene prioridad sobre .claude-plugin/ → "hooks": "./adapters/codex/hooks.json"
├── adapters/codex/hooks.json         PreToolUse Bash | apply_patch → dispatch.py --host codex
├── .antigravity-plugin/plugin.json   Antigravity
├── hooks.json                        Antigravity (raíz, indexado por nombre de hook) → dispatch.py --host antigravity
├── package.json                      OpenCode V2: exports "." → ./adapters/opencode/index.ts
├── adapters/opencode/index.ts        Shim TS → dispatch.py --host opencode
├── hooks/
│   ├── common.py                     (sin cambios de decisión) + emisión delegada a hosts.py
│   ├── hosts.py                      NUEVO: HookEvent, normalize(host, raw), emit(host, Decision)
│   ├── patch.py                      NUEVO: parser de apply_patch / patchText
│   ├── dispatch.py                   NUEVO: corre en un proceso los hooks que aplican al evento
│   ├── approvals.py                  NUEVO: aprobación de un solo uso (Codex)
│   ├── run-hook.cmd                  NUEVO: lanzador políglota bash/cmd (busca python3 | python | py -3)
│   └── block_dangerous.py … protect_files.py   main() consume HookEvent en vez de tool_name/tool_input
├── scripts/synapse.py                NUEVO: CLI de usuario `synapse approve|doctor|log`
├── skills/synapse-status/SKILL.md    Todos los hosts (se elimina commands/synapse-status.md, que la duplica)
├── rules/security-guardrails.md      + frontmatter `trigger: always_on` (Antigravity; Claude lo ignora)
├── .version-bump.json                NUEVO: archivos y claves donde vive la versión
└── tests/ …                          + tests/hosts/, tests/fixtures/<host>/, tests/protocol/
```

### 2.2 session-handoff

```text
plugins/session-handoff/
├── .claude-plugin/plugin.json        Claude Code (sin cambios)
├── hooks/hooks.json                  Claude Code: {"modules": ["./register.tsx"]} (sin cambios)
├── .codex-plugin/plugin.json         Codex: "hooks": "./adapters/codex/hooks.json" (evita que Codex lea {"modules"})
├── adapters/codex/hooks.json         SessionStart · UserPromptSubmit · PostToolUse · Stop → node dist/hook.mjs codex <evento>
├── .antigravity-plugin/plugin.json   Antigravity
├── hooks.json                        Antigravity: SessionStart · PreInvocation · PreToolUse(ask_question) · Stop
├── package.json                      OpenCode V2 + scripts de build y test
├── adapters/opencode/index.ts        Plugin en proceso con el núcleo
├── hooks/
│   ├── handoff.ts store.ts status.ts metrics.ts tail.ts   Núcleo puro (sin cambios de lógica)
│   ├── terms.ts                      NUEVO: nombres de tools y comandos por host para los textos
│   ├── register.tsx                  Claude Code (sin cambios de comportamiento)
│   ├── cli.ts                        NUEVO: entrada de los hosts por subprocess
│   ├── hosts.ts                      NUEVO: normalize/emit por host
│   ├── io-node.ts                    NUEVO: Io sobre node:fs y git
│   ├── actions.ts                    NUEVO: acciones por evento contra Io + State (hosts por subprocess y OpenCode)
│   └── state.ts                      NUEVO: estado por sesión en archivo (sin lanzador: `node` se llama igual en ambos SO)
├── dist/hook.mjs                     NUEVO, versionado: bundle ESM de cli.ts (bun build --target=node)
├── .version-bump.json                NUEVO
└── docs/bitacora/versiones/0.5.0.md  Bitácora de la versión
```

### 2.3 Archivos de la Raíz del Monorepo

```text
agent-plugins/
├── .claude-plugin/marketplace.json   Claude Code y Codex (fuentes relativas ./plugins/<x>)
├── .github/workflows/ci.yml          Tests por plugin, contratos, validadores (ubuntu + windows)
├── .github/workflows/release.yml     Tag <plugin>-v<semver> → split → espejo + tag v<semver>
├── scripts/bump.py                   Sincroniza versiones (--check, --audit)
├── scripts/release.py                Bump + bitácora + tag (local) y mirror (CI)
├── tools/probe/                      Sondas de payload por host (F0)
├── AGENTS.md                         Manual del monorepo para agentes
├── docs/research/ · docs/specs/
└── .gitignore                        (excepción: !plugins/session-handoff/dist/)
```

---

## 3. Manifiestos por Host

> Todos llevan la misma `version`, sincronizada por `scripts/bump.py`. Las descripciones dejan de decir "para Claude Code" (T-04). El `displayName` de Antigravity no puede incluir "Claude", "Gemini", "Antigravity" ni "Cursor".

### 3.1 Synapse

`.codex-plugin/plugin.json`. Es el formato legacy, porque el portable no carga hooks en `main` de Codex:

```json
{
  "name": "synapse",
  "version": "1.7.0",
  "description": "Guardrails de seguridad antes de cada tool: comandos destructivos, escrituras fuera del proyecto, lectura de .env, secretos y archivos protegidos.",
  "keywords": ["security", "guardrails", "hooks", "secrets-detection"],
  "skills": "./skills/",
  "hooks": "./adapters/codex/hooks.json",
  "interface": {
    "displayName": "Synapse",
    "shortDescription": "Guardrails de seguridad para el agente",
    "developerName": "Pablo Contreras",
    "category": "Security",
    "websiteURL": "https://github.com/bypabloc/agent-plugin-synapse"
  }
}
```

`.antigravity-plugin/plugin.json`:

```json
{
  "$schema": "https://antigravity.google/schemas/v1/plugin.json",
  "name": "synapse",
  "displayName": "Synapse",
  "description": "Guardrails de seguridad antes de cada tool: comandos destructivos, escrituras fuera del proyecto, lectura de .env, secretos y archivos protegidos.",
  "version": "1.7.0",
  "author": { "name": "Pablo Contreras", "url": "https://github.com/bypabloc" },
  "homepage": "https://github.com/bypabloc/agent-plugin-synapse",
  "repository": "https://github.com/bypabloc/agent-plugin-synapse",
  "license": "MIT",
  "keywords": ["security", "guardrails", "hooks"]
}
```

`package.json` (OpenCode). Va en la raíz del plugin porque no está verificado que OpenCode instale desde un subdirectorio de Git (V-11):

```json
{
  "name": "@bypabloc/synapse",
  "version": "1.7.0",
  "type": "module",
  "exports": { ".": "./adapters/opencode/index.ts" },
  "files": ["adapters/opencode", "hooks", "models", "scripts", "skills"],
  "peerDependencies": { "@opencode/plugin": "^2.3.0" },
  "engines": { "opencode": ">=2.3.0" },
  "license": "MIT"
}
```

Los archivos de hooks de Codex y Antigravity están en [02-synapse.md §7](./02-synapse.md#7-adaptadores-por-host).

### 3.2 session-handoff

Usa el mismo esquema con `name: "session-handoff"`, `displayName: "Session Handoff"`, `category: "Productivity"`, `version: "0.5.0"` y `"hooks": "./adapters/codex/hooks.json"` en `.codex-plugin/plugin.json`. En `package.json` van además:
- `"scripts": {"build": "bun build hooks/cli.ts --target=node --format=esm --outfile=dist/hook.mjs", "test": "bun test"}`
- `"engines": {"node": ">=20", "opencode": ">=2.3.0"}`

Los archivos de hooks están en [03-session-handoff.md §6](./03-session-handoff.md#6-cableado-por-host).

### 3.3 Validación de Manifiestos

| Validador | Uso | Criterio |
| :--- | :--- | :--- |
| `claude plugin validate --strict plugins/<x>` | CI y local | Sin errores ni warnings |
| `agy plugin validate --json plugins/<x>` | Local (y CI si se puede instalar `agy` en el runner, ver T-11) | Sin errores. Los warnings deben estar en una lista permitida versionada (`tests/agy-allowed-warnings.json`): `hooks/hooks.json` (es de Claude) y nada más. No se usa `--strict` porque Claude necesita `hooks/hooks.json` |
| Schemas de Codex (`codex-rs/hooks/schema/generated`, copiados en `tests/schemas/codex/` con el commit de origen) | CI | La salida de cada emisión Codex valida contra el schema de su evento (`additionalProperties: false`) |
| `opencode plugin check` | Local | El paquete carga y `Plugin.define` resuelve el `id` |
| `scripts/bump.py --check` | CI | Todos los manifiestos de un plugin tienen la misma versión |

---

## 4. Marketplaces

| Archivo | Lo leen | Contenido |
| :--- | :--- | :--- |
| `agent-plugins/.claude-plugin/marketplace.json` | **Claude Code y Codex** (Codex lee `.claude-plugin/marketplace.json`) | `name: "bypabloc-agents"` y dos entradas con `source: "./plugins/synapse"` y `"./plugins/session-handoff"`. Fuentes relativas, que Codex y Claude aceptan. **Nunca `source: "github"`**, porque Codex omite esas entradas |
| `claude-plugins/.claude-plugin/marketplace.json` | Claude Code | Las entradas `synapse` y `session-handoff` pasan a `{"source": "url", "url": "https://github.com/bypabloc/agent-plugin-<x>.git"}`, y se borran las copias `plugins/synapse` y `plugins/session-handoff` (T-15) |
| `marketplace-entry.json` de cada plugin | Plantilla para catálogos | URLs actualizadas a `agent-plugin-*` y fuente `url` |

Antigravity no tiene marketplaces de terceros (el oficial es curado) y OpenCode no tiene marketplace. Se instala por URL (§7).

> [!WARNING]
> **LFS.** Claude Code no descarga contenido LFS al clonar un marketplace. Con eso el delta de Laya llega como puntero y Synapse cae al perfil `zeroshot`, como ya pasa hoy. Codex, `agy` y OpenCode tampoco tienen descarga LFS documentada. El README de Synapse documenta `git lfs pull` en la caché de cada host, y `synapse doctor` (§02 §10) detecta el puntero y lo informa.

---

## 5. Versionado

- SemVer por plugin: `synapse` **1.7.0** (nuevo soporte de hosts, sin cambios de decisión en Claude) y `session-handoff` **0.5.0**.
- `.version-bump.json` por plugin, en el formato de superpowers ([05 · H-07](./05-referencias.md#2-hallazgos-que-afectan-a-este-spec)):

```json
{
  "files": [
    { "path": ".claude-plugin/plugin.json", "key": "version" },
    { "path": ".codex-plugin/plugin.json", "key": "version" },
    { "path": ".antigravity-plugin/plugin.json", "key": "version" },
    { "path": "package.json", "key": "version" },
    { "path": "pyproject.toml", "key": "project.version" }
  ]
}
```

  En session-handoff no hay `pyproject.toml`; se agrega `{ "path": "hooks/handoff.ts", "regex": "VERSION = '([^']+)'" }`.
- `scripts/bump.py <plugin> <versión>` escribe la versión en todas las rutas.
  - `--check` falla si alguna versión difiere.
  - `--audit` lista las apariciones de la versión anterior en el plugin (README, bitácora) para revisarlas.
- El marketplace del monorepo y el de `claude-plugins` también llevan la versión. `bump.py` los incluye si existen.

---

## 6. Release y Espejos

```text
feature/<x> ──PR──▶ dev ──PR──▶ main ──tag synapse-v1.7.0──▶ release.yml
                                                             ├─ bump.py --check
                                                             ├─ tests del plugin
                                                             ├─ git subtree split --prefix=plugins/synapse -b split
                                                             ├─ git lfs push (objetos del split) al espejo
                                                             ├─ git push espejo split:main  (fast-forward)
                                                             └─ tag v1.7.0 en el espejo + GitHub Release
```

1. **Local:** `scripts/release.py synapse 1.7.0` corre `bump.py`, crea `docs/bitacora/versiones/1.7.0.md` (session-handoff) o el apartado del CHANGELOG de Synapse a partir de la plantilla, hace commit `chore(release): synapse 1.7.0` en una rama `release/synapse-1.7.0` y abre el PR a `dev`.
2. Tras el merge a `main`, el tag `synapse-v1.7.0` dispara `release.yml`.
3. **El split debe ser fast-forward.** Si el `main` del espejo no es ancestro del split, el job falla: nadie debe empujar al espejo por fuera del release.
4. **Secretos:** `MIRROR_DEPLOY_KEY_SYNAPSE` y `MIRROR_DEPLOY_KEY_HANDOFF`, deploy keys con escritura, una por espejo.
5. **Primera publicación (T-03):** el `main` actual de cada espejo es ancestro del split, porque se importó sin squash. El primer split desde el monorepo debe ser fast-forward; si no lo es, se investiga antes de forzar.
6. `scripts/release.py --mirror <plugin>` hace lo mismo de forma local, para emergencias, con la llave personal (`core.sshCommand` con `~/.ssh/pacg1991`).

**Después de publicar, por host:**

| Host | Cómo se actualiza el usuario |
| :--- | :--- |
| Claude Code | `claude plugin marketplace update bypabloc-agents && claude plugin update synapse@bypabloc-agents` |
| Codex | `codex plugin marketplace upgrade` y luego `/hooks` para **volver a confiar** en los hooks: Codex los ata al hash de los scripts |
| Antigravity | `agy plugin install https://github.com/bypabloc/agent-plugin-synapse` (no existe `agy plugin update` para instalaciones por URL, V-12) |
| OpenCode | Si la versión está fijada con `#v1.7.0`, se cambia la referencia. Con `#main`, se actualiza al arrancar |

---

## 7. Instalación por Host

Va en el README de cada plugin, con una sección por host y comandos probados en WSL y Windows (PowerShell).

### 7.1 Synapse

| Host | WSL / Linux | Windows (PowerShell) | Requisitos |
| :--- | :--- | :--- | :--- |
| Claude Code | `claude plugin marketplace add bypabloc/agent-plugins` · `claude plugin install synapse@bypabloc-agents` | Igual | `python3` ≥ 3.10 |
| Codex | `codex plugin marketplace add bypabloc/agent-plugins` · `codex plugin add synapse@bypabloc-agents` · `/hooks` → confiar | Igual | `python3` (Linux) o `python`/`py` (Windows) |
| Antigravity | `agy plugin install https://github.com/bypabloc/agent-plugin-synapse` | Igual | Igual. Workspace confiado (Workspace Trust) |
| OpenCode | En `opencode.json`: `"plugins": ["@bypabloc/synapse@git+https://github.com/bypabloc/agent-plugin-synapse.git#v1.7.0"]` | Igual | Igual |

Opcional en todos los hosts: Laya en GPU (`SYNAPSE_LAYA=on`, `uv sync` en la raíz del plugin instalado), igual que hoy.

### 7.2 session-handoff

El mismo esquema con `session-handoff@bypabloc-agents` y `agent-plugin-session-handoff`. Requisitos:
- Claude Code: ninguno (es un mod).
- OpenCode: ninguno (corre en el Bun que trae OpenCode).
- Codex y Antigravity: `node` ≥ 20.

Además va `tmp/` en el `.gitignore` del proyecto, como hoy.

### 7.3 Local, sin Publicar

| Host | Comando |
| :--- | :--- |
| Claude Code | `claude --plugin-dir ./plugins/synapse` |
| Codex | `codex plugin marketplace add ./` (raíz del monorepo) · `codex plugin add synapse@bypabloc-agents` |
| Antigravity | `agy plugin install ./plugins/synapse` (o copiar a `.agents/plugins/`) |
| OpenCode | `"plugins": ["./plugins/synapse"]` en `opencode.json` del proyecto de prueba |

---

## 8. Clones Locales

- El clon de trabajo del monorepo va en `~/projects/bypabloc/agent-plugins`. Esta sesión no pudo crearlo porque la Synapse instalada bloquea escrituras fuera del proyecto. Lo hace el usuario (T-01).
- `~/projects/bypabloc/claude-plugin-synapse` y `D:\…\claude-plugin-session-handoff` quedan como clones de los espejos. Se archivan localmente tras T-03 y deja de usarse en ellos el flujo de ramas propio.
- `~/projects/bypabloc/agent-plugins-probe-clone` es un clon de prueba que quedó de esta sesión. Se borra (T-01).

---

## 9. `AGENTS.md` del Monorepo

Contenido mínimo (T-02):
- Mapa de carpetas y regla de "cambios solo aquí".
- Comandos de prueba por plugin (`python3 -m pytest` en `plugins/synapse`, `bun test` en `plugins/session-handoff`).
- Release (§6).
- Política de idioma: español neutro en docs, commits y logs, y Conventional Commits con scope del plugin: `feat(synapse): …`, `fix(session-handoff): …`.
- Enlace a los `AGENTS.md` de cada plugin, que siguen vigentes para su lógica.
