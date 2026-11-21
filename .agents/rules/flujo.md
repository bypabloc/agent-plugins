# Flujo de todo cambio (siempre activa)

Decisión del usuario (2026-11-21). Vale para **cualquier** cambio en este repo: código de un plugin, scripts, docs,
reglas, skills o CI. Esta regla vive duplicada en `.claude/rules/flujo.md` (Claude Code) y `.agents/rules/flujo.md`
(Codex y otros agentes); `scripts/tests/test_reglas_espejo.py` exige que sean idénticas.

## 1. Siempre en un worktree

- Nunca se edita ni se hace commit en el checkout principal (`agent-plugins/`): puede tener trabajo de otra sesión.
- El checkout principal queda **siempre en `dev`**, actualizado (`git checkout dev && git pull --ff-only`).
  Si una sesión lo encuentra en otra rama ya fusionada y sin cambios, lo devuelve a `dev`.
- Cada cambio abre su propio worktree desde `dev` actualizado, en la carpeta hermana `agent-plugins-worktrees/`:

  ```bash
  git fetch origin
  git worktree add -b <rama> ../agent-plugins-worktrees/<rama-con-guiones> origin/dev
  ```

- Rama: `feature/<NNN>-<tema>`, `fix/<plugin>-<tema>` o `chore/repo-<tema>`.
- Al terminar el ciclo: `git worktree remove ../agent-plugins-worktrees/<carpeta>` y se borran la rama local y la
  remota (`git branch -D <rama>`, `git push origin --delete <rama>`). En el repo solo quedan `dev` y `main`.

## 2. Siempre hasta `main`

1. Commit (Conventional Commits, scope = plugin o `repo`), push y PR a `dev`.
2. CI en verde (`gh pr checks <n> --watch`) → `gh pr merge <n> --merge`.
3. PR de `dev` a `main`, CI en verde → `gh pr merge <m> --merge`.

Nunca `--force`, nunca saltar la CI. Si un paso falla, se arregla en el mismo worktree o se informa con la salida.

## 3. Siempre publicado e instalado, plugin por plugin

Por **cada** plugin cuyos archivos cambiaron (`plugins/<x>/`):

1. Versión nueva con `python scripts/bump.py <plugin> X.Y.Z` (patch para fix, minor para feat) y su entrada en
   `plugins/<x>/docs/bitacora/versiones/X.Y.Z.md`, dentro del mismo PR.
2. Tras el merge a `main`: `git tag <plugin>-vX.Y.Z origin/main && git push origin <plugin>-vX.Y.Z`, y esperar a
   que `release.yml` publique el espejo (`gh run watch`).

Después, una sola vez para todos los plugins publicados:

```bash
python scripts/actualizar_instalaciones.py          # plan
python scripts/actualizar_instalaciones.py --apply  # todos los CLI y perfiles, Windows y WSL
python scripts/vigilancia.py --since 1h             # todo quedó en la versión nueva
```

Un cambio que no toca `plugins/` (scripts, docs, reglas) llega igual a `main`, pero no lleva tag ni instalación.

Al usuario se le informa el resultado y lo que solo él puede hacer: `/hooks` en cada Codex abierto,
`/reload-plugins` en las sesiones de Claude abiertas y el `.claude/settings.json` que cambió en un proyecto consumidor.
