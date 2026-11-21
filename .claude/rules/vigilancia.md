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

## Qué requiere un "sí" del usuario

- Cualquier escritura en un proyecto vigilado (klinikae, content-studio, …) o en `~/.codex`, `~/.claude` o la
  configuración de WSL: hooks huérfanos, marketplaces viejos, reinstalaciones. Propón el cambio exacto, con respaldo.
- Fusionar a `main`, etiquetar o publicar un espejo.
- Aprobar un `ask` de Synapse: nunca lo hace el agente, ni siquiera con permiso.

## Proyectos y rutas

El registro vigente está en [`docs/vigilancia/proyectos.json`](../../docs/vigilancia/proyectos.json). Al agregar
un proyecto nuevo, súmalo ahí y no en esta regla.
