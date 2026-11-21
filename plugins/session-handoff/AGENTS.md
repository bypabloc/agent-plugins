# AGENTS.md — session-handoff

Manual técnico para quien mantiene el plugin. El uso está en el [README](README.md) y la historia en la
[bitácora](docs/bitacora/README.md). Espejo: `bypabloc/agent-plugin-session-handoff` (nunca recibe commits directos).

## 1. Qué Hace

El estado del trabajo vive en disco, en `tmp/handoff/<trabajo>/` del checkout principal (`PROGRESS.md`,
`DECISIONS.md`, `NOTES.md`), y el plugin lo usa así:

- **Inyecta** ese estado al iniciar, reanudar, `/clear` y compactar.
- **No deja cerrar el turno** (`Stop`) mientras haya `Next step` sin `Status: done` ni un `blocked` válido.
- **Rechaza `AskUserQuestion`** con una spec en curso.
- **Recuerda los hashes** de los commits que faltan en `PROGRESS.md`.
- **Compacta sin resumen del modelo** (solo Claude Code).

Cada decisión queda en `tmp/handoff/.log/events.jsonl`, con la versión en `v`.

## 2. Mapa del Código

| Ruta | Qué es |
| :--- | :--- |
| `hooks/register.tsx` | Mod de Claude Code (API `claude-code`): eventos, compactación, banda, spinner y métricas |
| `hooks/handoff.ts` | Lógica pura: líneas de estado, `stopDecision`, textos, hashes. `VERSION` vive aquí |
| `hooks/store.ts` | Disco: vínculos `.sessions/`, trabajos, configuración, `logEvent` |
| `hooks/actions.ts` | Acciones neutrales por evento, compartidas por los hosts que no son Claude |
| `hooks/hosts.ts` | Entrada y salida de Codex y Antigravity: solo las claves que acepta cada host |
| `hooks/tail.ts`, `status.ts`, `metrics.ts`, `terms.ts` | Tramo que se conserva al compactar, banda, métricas, vocabulario |
| `cli/cli.ts`, `cli/io-node.ts` | CLI para Codex y Antigravity. `bun run build` lo empaqueta en `dist/hook.mjs` (se versiona) |
| `adapters/codex/hooks.json` | Cableado de Codex (`node dist/hook.mjs codex <evento>`) |
| `hooks.json` (raíz) | Cableado de Antigravity |
| `adapters/opencode/index.ts` | Plugin en proceso para OpenCode V2 |

## 3. Invariantes

1. **Claude Code no cambia** cuando se toca otro host: los tests de `register.test.ts` pasan sin cambios.
2. **El host se declara** en cada cableado (`codex`, `antigravity`). Nunca se deduce del entorno, porque Codex
   hereda variables `CLAUDE_*`.
3. **Fuera de Claude Code** corre con `node` ≥ 20 sobre `dist/hook.mjs`. Un cambio en `hooks/` o `cli/` exige
   `bun run build`, y la CI falla si `dist/` no está al día.
4. **Ningún bloqueo es eterno.** `Stop` tiene tope (3 bloqueos sin cambios), `external-wait` se vuelve a comprobar,
   y una sesión cuyo trabajo tomó otra se suelta (`handed-off`). Un cambio en `Stop` debe preservar las tres salidas.
5. **El texto inyectado es corto.** Se mide en `chars` en cada `inject`. Las líneas de estado no pasan de 120
   caracteres, y por encima de ~8000 caracteres conviene revisar qué crece.
6. **Un evento por decisión** en `events.jsonl`, siempre con `v`. Una línea sin `v` es de otro escritor (un hook
   propio del proyecto) o de una versión anterior a 0.3.5.

## 4. Pruebas

```bash
claude plugin test .        # hooks/*.test.ts (importan claude-code/testing: no corren con bun test)
bun test tests/cli          # acciones y hosts (Codex, Antigravity)
bun run build && git diff --exit-code dist/
claude plugin validate --strict .
python tests/e2e/hosts_e2e.py   # E2E con los binarios reales (codex, agy, opencode), en local
```

## 5. Versión

La versión aparece en seis lugares (`.version-bump.json`), incluido `VERSION` en `hooks/handoff.ts`. Se cambia
solo con `python scripts/bump.py session-handoff X.Y.Z` desde la raíz del monorepo. Cada versión lleva su archivo en
`docs/bitacora/versiones/` y su línea en la sección Versiones del README.

## 6. Vigilancia

Las fuentes, los síntomas y cómo leerlos están en [docs/bitacora/vigilancia.md](docs/bitacora/vigilancia.md). La
revisión la corre la skill `vigilar-plugins` del monorepo, y la reparación la skill `reparar-plugin`.
