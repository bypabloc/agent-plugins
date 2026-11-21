---
name: reparar-plugin
description: Repara o mejora un plugin del monorepo (synapse, session-handoff, spanish-latam-style) a partir de un hallazgo con evidencia de una sesión real. Test que lo reproduce en rojo, arreglo, versión con bump.py, entrada en la bitácora y PR a dev. Usar tras un hallazgo de clase bug o mejora de vigilar-plugins, o cuando el usuario diga "arregla el plugin", "esto lo rompió synapse/handoff", "que no vuelva a pasar".
---

# Reparar un plugin

Lee primero el manual del plugin: `plugins/synapse/AGENTS.md` o `plugins/session-handoff/AGENTS.md`
(spanish-latam-style: su `README.md`). Sus invariantes mandan sobre esta skill.

## Pasos

1. **Rama**: desde `dev` actualizado, `fix/<plugin>-<tema>` o `feat/<plugin>-<tema>`. Si ya estás en una rama de
   trabajo de este repo, sigue en ella.
2. **Reproducir**: escribe el test con los datos reales del hallazgo (ruta, comando, payload del host, texto). Debe
   fallar antes del cambio, y debes verlo fallar.
   - synapse: un caso en `tests/cases/<hook>.json` (sin código) o un test en `tests/unit/test_hosts.py` para la
     emisión por host. Un caso nuevo necesita su golden de Claude:
     `SYNAPSE_GOLDEN_WRITE=1 python -m pytest tests/unit/test_golden_claude.py -k <caso>`, generado en **Linux o WSL**
     (en Windows esos tests son `xfail`).
   - session-handoff: `hooks/*.test.ts` (se corre con `claude plugin test .`) o `tests/cli/*.spec.ts` (`bun test tests/cli`).
3. **Arreglar** con el cambio mínimo que respete los invariantes:
   - Claude Code sin regresiones: el golden no cambia salvo en los casos nuevos.
   - Ningún host falla abierto: ante la duda, `ask`/`force_ask`, nunca `allow`.
   - Autosuficiencia: si el plugin detiene o frena al agente, el texto que emite le dice cómo seguir sin rodear la regla.
4. **Verificar**:
   - synapse: `python -m pytest` en `plugins/synapse` (Windows) y los tests afectados en WSL.
   - session-handoff: `claude plugin test plugins/session-handoff`, `bun test tests/cli` y `bun run build` (el `dist/` se versiona).
   - Raíz: `python scripts/bump.py --check`, `claude plugin validate --strict plugins/<x>`.
5. **Versión**: `python scripts/bump.py <plugin> X.Y.Z` (patch para fix, minor para feat) y
   `python scripts/bump.py --audit <plugin> <anterior>`.
6. **Bitácora**: `plugins/<x>/docs/bitacora/versiones/X.Y.Z.md` con la plantilla del README de la bitácora
   (síntoma tal como se vio, causa, cambio, prueba, lección), su fila en la tabla, y si aplica, una línea en
   `aprendizajes.md` o el cierre de una fila de `mejoras-pendientes.md`.
7. **Commit y PR**: Conventional Commits con el plugin como scope, en español. PR a `dev`. En el cuerpo, el hallazgo y
   su evidencia, y los comandos con que cada host se actualiza tras el release (`AGENTS.md` §4).

## Después del merge

El release (tag `<plugin>-v<semver>` sobre `main`) lo decide el usuario. Cuando esté publicado, la siguiente
revisión de `vigilar-plugins` comprueba que los entornos se actualizaron y que el síntoma no volvió.
