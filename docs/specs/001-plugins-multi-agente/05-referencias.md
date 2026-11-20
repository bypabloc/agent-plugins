# 05 · Referencias: Cómo lo Hacen Otros y Estándar Adoptado

> Revisión de repos reales que publican un mismo plugin para varios agentes, hecha el 2026-11-20 con `gh api`: árbol de archivos, README, workflows y `package.json`. Las estrellas son aproximadas. La columna "Adoptado" indica qué tomamos para este spec.

---

## 1. Referencias

| Proyecto | Estrellas | Hosts relevantes | Por qué importa |
| :--- | ---: | :--- | :--- |
| [Dicklesworthstone/destructive_command_guard](https://github.com/Dicklesworthstone/destructive_command_guard) (dcg) | ~6.4k | Claude, Codex 0.125+, `agy`, OpenCode V1/V2, Gemini, Copilot, Cursor… | **Guardrail de comandos como Synapse.** Tiene detección de host, emisión estricta por host, shim de OpenCode y pruebas de protocolo con el binario real |
| [obra/superpowers](https://github.com/obra/superpowers) | ~323k | Claude, Codex, Antigravity, OpenCode V1/V2, Cursor, Gemini… | El layout de referencia: un directorio `.<host>-plugin/` por host, versión sincronizada por script y lanzador políglota para Windows |
| [affaan-m/ECC](https://github.com/affaan-m/ECC) | ~308k | Claude, Codex, Antigravity, OpenCode… | Variantes de `hooks.json` por host y un puente que normaliza Antigravity al payload de Claude (`hook-bridge.js`) |
| [awslabs/aidlc-workflows](https://github.com/awslabs/aidlc-workflows) | ~6.2k | Claude, Codex, OpenCode, Copilot, Cursor | `core/` más `harness/<host>/` con `emit.ts`. **Documenta las rarezas reales de Codex** y fija las versiones de los CLIs en CI |
| [EveryInc/compound-engineering-plugin](https://github.com/EveryInc/compound-engineering-plugin) | ~26k | Claude, Codex, Antigravity, OpenCode… | release-please con `extra-files` para versionar todos los manifiestos |
| [dyoshikawa/rulesync](https://github.com/dyoshikawa/rulesync) | ~1.6k | Codex, Antigravity, OpenCode V1/V2… | La única herramienta genérica que traduce hooks. Su plugin de OpenCode V2 le pasa un stdin **con forma de Claude** a un comando |
| [vercel/vercel-plugin](https://github.com/vercel/vercel-plugin) | ~340 | Claude, Antigravity, Cursor… | `hooks/compat.mjs` con `detectPlatform`, `normalizeInput` y `formatOutput`, y tests de compatibilidad por plataforma |
| [anomalyco/opencode `packages/plugins`](https://github.com/anomalyco/opencode/tree/dev/packages/plugins) | — | OpenCode V2 | Plugins oficiales en V2, que se instalan **por URL Git** |
| [code-yeongyu/oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) | ~71k | OpenCode | Capa que ejecuta hooks de Claude dentro de OpenCode: Stop y Notification pasan a `session.idle` |

**Descartados:**
- [intellectronica/ruler](https://github.com/intellectronica/ruler) y [vercel-labs/skills](https://github.com/vercel-labs/skills): solo manejan reglas, skills y MCP, sin hooks.
- `antigravity-plugins-official`: no existe como repo público. La org [google-antigravity](https://github.com/google-antigravity) solo publica `antigravity-cli` y `antigravity-sdk-python`.
- [Cross-Tool Plugin Comparison](https://github.com/awslabs/aidlc-workflows/blob/main/docs/reference/research/Cross-Tool%20Plugin%20Comparison.md) de aidlc (junio 2026): está desactualizado. Dice que Codex no bloquea, y dcg sí bloquea en Codex 0.125+.

---

## 2. Hallazgos que Afectan a Este Spec

| # | Hallazgo | Fuente | Efecto en el spec |
| :--- | :--- | :--- | :--- |
| H-01 | **Codex y `agy` rechazan campos de salida desconocidos.** El parser `protojson` de agy rechaza claves extra | [dcg #573](https://github.com/Dicklesworthstone/destructive_command_guard/issues/573), README de dcg | La emisión es **mínima y por host**. En Antigravity solo `decision` y `reason`. Hay un test de contrato que falla ante una clave extra ([02 §5](./02-synapse.md#5-emisión-por-host)) |
| H-02 | **Codex puede entregar un mismo evento dos veces** | [aidlc-codex-adapter.ts](https://github.com/awslabs/aidlc-workflows/blob/main/harness/codex/hooks/aidlc-codex-adapter.ts) | La aprobación de un solo uso y los contadores de `Stop` son idempotentes por `tool_use_id` o `turn_id` ([02 §6](./02-synapse.md#6-aprobación-de-un-solo-uso-codex), [03 §4](./03-session-handoff.md#4-estado-por-sesión)) |
| H-03 | Codex puede no emitir `SessionEnd` y dispara `UserPromptSubmit` también en subagentes | aidlc | session-handoff no depende de `SessionEnd`. `UserPromptSubmit` ignora a los subagentes (`agent_id`) |
| H-04 | Un guardrail registrado como **comando desnudo** falla abierto si el `PATH` no lo tiene | README de dcg | Las rutas se toman de la raíz del plugin. En Windows se usa el lanzador `run-hook.cmd`, que busca `python3`, `python` y `py -3`, y emite el bloqueo del host si no encuentra intérprete ([02 §8](./02-synapse.md#8-lanzador-e-intérprete-windows-y-linux)) |
| H-05 | Script políglota bash/cmd para lanzar hooks en Windows | [superpowers `hooks/`](https://github.com/obra/superpowers/tree/main/hooks) | Se adopta `hooks/run-hook.cmd` en Synapse. session-handoff no lo necesita: `node` se llama igual en ambos SO y allí un fallo no es un riesgo de seguridad |
| H-06 | El estándar de facto es **un directorio `.<host>-plugin/` por host** en la raíz, apuntando a los mismos `skills/` y `hooks/` | superpowers, ECC, compound-engineering, vercel-plugin | Es el layout de cada espejo ([01 §2](./01-repos-y-publicacion.md#2-layout-de-cada-plugin-y-de-su-espejo)) |
| H-07 | **Manifiestos escritos a mano y versión sincronizada por script** con `--check` (detecta drift) y `--audit` (busca la versión vieja) | [superpowers `.version-bump.json`](https://github.com/obra/superpowers/blob/main/.version-bump.json) | `scripts/bump.py` con `.version-bump.json` por plugin ([01 §5](./01-repos-y-publicacion.md#5-versionado)) |
| H-08 | En OpenCode, un archivo TS con `Plugin.define({id, setup})` y `ctx.tool.hook("execute.before")` lanza el hook real como subprocess con un stdin con forma de Claude, y **falla cerrado si no recibe veredicto** | dcg, rulesync, aidlc | Así es el shim de Synapse para OpenCode ([02 §7.3](./02-synapse.md#73-opencode-v2)) |
| H-09 | En OpenCode, Stop pasa a `session.idle` con un prompt reinyectado y PreCompact a la compactación | aidlc, oh-my-openagent | Así se cablea session-handoff en OpenCode ([03 §6.3](./03-session-handoff.md#63-opencode-v2-en-proceso)) |
| H-10 | Pruebas de protocolo de caja negra: el stdin exacto del host, más decisión, exit code y stdout/stderr, en un `HOME` hermético (`env -i`) | [dcg e2e_harness_matrix.sh](https://github.com/Dicklesworthstone/destructive_command_guard/blob/main/scripts/e2e_harness_matrix.sh) | Matriz de protocolo ([04 §4](./04-pruebas-y-verificacion.md#4-pruebas-de-protocolo-caja-negra)) |
| H-11 | CI con versiones de CLI fijadas y carriles "live" por host en Linux, macOS y Windows | [aidlc full-suite.yml](https://github.com/awslabs/aidlc-workflows/blob/main/.github/workflows/full-suite.yml) | Carriles E2E fijados por versión, opcionales porque requieren credenciales ([04 §7](./04-pruebas-y-verificacion.md#7-ci)) |
| H-12 | Instalación nativa por host en vez de un instalador propio: marketplace en Claude y Codex, `agy plugin install <url>`, `"plugins": ["x@git+https://…"]` en OpenCode | superpowers, compound-engineering | No se escribe instalador. Se documenta un comando por host ([01 §7](./01-repos-y-publicacion.md#7-instalación-por-host)) |
| H-13 | **La forma del `hooks.json` de un plugin de Antigravity no es uniforme** entre referencias: indexado por nombre (ECC) o `{hooks:{…}}` (compound-engineering) | ECC, compound-engineering | Se sigue la documentación oficial (indexado por nombre) y lo confirma la verificación V-05 con `agy plugin validate --strict` y E2E |

---

## 3. Estándar Adoptado

1. **Un directorio de manifiesto por host** en la raíz del plugin: `.claude-plugin/`, `.codex-plugin/` y `.antigravity-plugin/`, más un `hooks.json` raíz para Antigravity y `package.json` para OpenCode. No se pone un `plugin.json` raíz de Agent Plugins 1.0, porque en Codex tiene prioridad y no carga hooks.
2. **Payload de Claude como forma canónica de prueba** y un **núcleo neutral** con normalización y emisión por host. En Synapse el formato interno es `HookEvent` y no el payload de Claude, porque `apply_patch` toca varios archivos a la vez.
3. **El host se declara** en el archivo de hooks de cada host (D-09). La detección por forma del payload solo se usa para **diagnóstico**: `synapse doctor` avisa si el payload no coincide con el `--host` declarado.
4. **Emisión mínima y estricta** con tests de contrato. En los hosts sin `ask`, el `ask` se vuelve `deny` (fail-closed) más la aprobación de un solo uso (D-04).
5. **Versión sincronizada por script** con `--check` en CI y sin generadores externos de manifiestos.
6. **Shim de OpenCode en TS** que lanza el núcleo real y falla cerrado.
7. **Pruebas de protocolo de caja negra** con fixtures reales, más E2E opcionales con binarios fijados por versión.
8. **Distribución nativa por host.** El monorepo publica espejos con el plugin en la raíz, que es el layout que esperan `agy plugin install <url>` y OpenCode por Git.

**No adoptado:**
- Instaladores que mezclan configuración en la de cada host (dcg). Los hosts ya tienen formato de plugin.
- release-please. Con dos plugins alcanza un script de bump.
- Generar manifiestos desde una fuente única (compound-engineering). Agrega una herramienta para pocos archivos y rulesync lo evita a propósito.
- Cuerpos de hooks embebidos en el manifiesto (ECC).
