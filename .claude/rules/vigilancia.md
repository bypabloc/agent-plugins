# Vigilancia de los plugins en proyectos reales (siempre activa)

Este repo también **observa** cómo se comportan sus plugins en los proyectos que los usan, y los **repara o mejora**
con esa evidencia. Detalle: [`docs/vigilancia/README.md`](../../docs/vigilancia/README.md).

## Cuándo vigilar

- Cuando el usuario pega la salida de un agente (Codex, Claude Code) que se detuvo, se confundió o mostró un error
  de un plugin. Ese texto es el primer hallazgo: ubícalo en la traza antes de opinar.
- Cuando pide revisar los plugins, o cuando un `/loop` lo dispara (por ejemplo `/loop 30m revisa cómo van los plugins`).
- Antes de un release: confirma que el síntoma que corrige la versión no volvió a aparecer en la ventana reciente.

Se usa la skill `vigilar-plugins`, que corre `scripts/vigilancia.py`. Para arreglar, la skill `reparar-plugin`.

## Qué se hace sin preguntar

- Leer las trazas, los transcripts y la configuración de Windows y WSL (solo lectura).
- Escribir reportes en `docs/vigilancia/reportes/` y actualizar `docs/vigilancia/proyectos.json`.
- Reparar o mejorar un plugin **en este repo**: rama, test, arreglo, versión, bitácora y PR a `dev`.
- **Cerrar el ciclo de cada reparación** (autorizado por el usuario el 2026-11-21). Con la CI en verde, sin esperar:
  1. Fusionar el PR a `dev`, abrir el PR de `dev` a `main` y fusionarlo (`gh pr merge --merge`).
  2. Publicar: `git tag <plugin>-v<versión>` sobre el `main` fusionado y `git push origin <tag>`, una por plugin con
     versión nueva. Esperar a que `release.yml` publique el espejo (`gh run watch`).
  3. Actualizar todos los CLI y perfiles de la máquina: `python scripts/actualizar_instalaciones.py` (plan) y luego
     `--apply`. Cubre Claude Code (cada perfil y scope, Windows y WSL) y Codex (Windows y WSL).
  4. Comprobar con `python scripts/vigilancia.py --since 1h` que todo quedó en la versión nueva.
  5. Avisar al usuario de lo que no se puede automatizar: `/hooks` en cada Codex abierto, `/reload-plugins` en las
     sesiones de Claude abiertas y el `.claude/settings.json` que cambió en un proyecto consumidor (sin commit).
- Quitar hooks huérfanos o duplicados en `~/.codex/hooks.json` que la vigilancia confirme, siempre con respaldo.

Si un paso falla (CI en rojo, merge con conflicto, release fallido), el ciclo se detiene ahí: se arregla en el repo
o se informa. Nunca se fuerza un push ni se salta la CI.

## Qué requiere un "sí" del usuario

- Escribir en el código o la configuración versionada de un proyecto vigilado (klinikae, content-studio, …), salvo
  el `.claude/settings.json` que cambie `actualizar_instalaciones.py`, y nunca hacer commits en esos repos.
- Cambios en `~/.codex` o `~/.claude` distintos de los de arriba.
- Aprobar un `ask` de Synapse o confiar hooks de Codex (`/hooks`): nunca lo hace el agente, ni siquiera con permiso.

## Proyectos y rutas

El registro vigente está en [`docs/vigilancia/proyectos.json`](../../docs/vigilancia/proyectos.json). Al agregar
un proyecto nuevo, súmalo ahí y no en esta regla.
