---
name: reparar-plugin
description: Repara o mejora un plugin del monorepo (synapse, session-handoff, spanish-latam-style) a partir de un hallazgo con evidencia de una sesión real. Test que lo reproduce en rojo, arreglo, versión con bump.py, entrada en la bitácora, PR a dev, merge a dev y main, release y actualización de todos los CLI. Usar tras un hallazgo de clase bug o mejora de vigilar-plugins, o cuando el usuario diga "arregla el plugin", "esto lo rompió synapse/handoff", "que no vuelva a pasar".
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

## 8. Cerrar el ciclo (sin preguntar)

El usuario autorizó (2026-11-21) que toda reparación termine publicada e instalada. Con la CI del PR en verde:

```bash
gh pr checks <n> --watch                                     # CI verde; si falla, se arregla antes de seguir
gh pr merge <n> --merge                                      # a dev
gh pr create --base main --head dev --title "..." --body "..."   # dev → main
gh pr checks <m> --watch && gh pr merge <m> --merge
git fetch origin && git tag <plugin>-v<X.Y.Z> origin/main && git push origin <plugin>-v<X.Y.Z>   # uno por plugin
gh run watch "$(gh run list --workflow release.yml -L 1 --json databaseId -q '.[0].databaseId')"
python scripts/actualizar_instalaciones.py                   # plan
python scripts/actualizar_instalaciones.py --apply           # todos los perfiles y CLI, Windows y WSL
python scripts/vigilancia.py --since 1h                      # todo en la versión nueva
```

- Un tag solo para los plugins cuya versión cambió. El job de release falla si el espejo no es fast-forward: no se fuerza.
- Al usuario, al final: qué versión quedó publicada e instalada, y lo que solo puede hacer él: `/hooks` en cada Codex
  (Codex no corre un hook cambiado hasta volver a confiar en él), `/reload-plugins` en las sesiones abiertas de
  Claude y el `.claude/settings.json` de un proyecto consumidor que cambió sin commit.
- Si un paso falla, el ciclo se detiene ahí y se informa con la salida. Nunca `--force`, nunca saltar la CI.

La siguiente revisión de `vigilar-plugins` comprueba que el síntoma no volvió.
