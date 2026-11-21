---
name: vigilar-plugins
description: Revisa cómo se comportan synapse, session-handoff y spanish-latam-style en los proyectos reales que los usan (Windows y WSL, Codex y Claude Code), clasifica cada hallazgo y deja un reporte. Usar cuando el usuario pida "revisa cómo van los plugins", "vigila el plugin", "qué pasó con synapse/handoff en tal proyecto", pegue la salida de un agente que se detuvo o falló por un plugin, o cuando un /loop pida la revisión periódica.
---

# Vigilar los plugins

Objetivo: que los plugins sean autosuficientes. Un hallazgo importa si hizo (o puede hacer) que un agente se
detenga, repita trabajo, pierda contexto, reciba texto roto o deje pasar algo peligroso.

## 1. Recolectar

```bash
python scripts/vigilancia.py --since <ventana>          # markdown; ventana = desde la revisión anterior (6h por defecto)
python scripts/vigilancia.py --since <ventana> --json   # cuando necesites los datos crudos
```

Si el usuario pegó la salida de un agente, ese es el primer hallazgo: ubícalo en la traza (hora, proyecto, regla).
Lee el reporte anterior en `docs/vigilancia/reportes/` para no volver a informar lo ya resuelto.

## 2. Confirmar cada hallazgo con evidencia

El colector da pistas; la evidencia está en las fuentes de cada plugin
(`plugins/synapse/docs/bitacora/vigilancia.md`, `plugins/session-handoff/docs/bitacora/vigilancia.md`):

- **Transcript de Codex**: `~/.codex/sessions/AAAA/MM/DD/rollout-*.jsonl` (en WSL, con `wsl.exe -e bash -lc '…'`).
  Busca la sesión por hora o por `session` y lee qué hizo el agente después del evento.
- **Transcript de Claude Code**: `$CLAUDE_CONFIG_DIR/projects/<cwd codificado>/<session-id>.jsonl`.
- **Traza de Synapse**: `python plugins/synapse/scripts/synapse.py log --since 2h --decision ask`.
- **Handoff**: `tmp/handoff/<trabajo>/PROGRESS.md` del proyecto y `tmp/handoff/.log/events.jsonl`.

Lee solo lo necesario (filtra con `grep`/`python`); los transcripts son grandes.

## 3. Clasificar

| Clase | Ejemplo | Acción |
| :--- | :--- | :--- |
| `entorno` | Hook huérfano en `~/.codex/hooks.json`, marketplace viejo, hook propio que duplica al plugin | Propón el cambio exacto (con respaldo). **No** lo apliques sin un "sí" del usuario |
| `version` | El síntoma ya está corregido en una versión posterior a la instalada | Propón actualizar (comando por host) o `/reload-plugins` |
| `bug` | El plugin hace algo incorrecto con la versión actual | Skill `reparar-plugin` |
| `mejora` | Funciona como se diseñó, pero frena al agente (un `ask` evitable, un texto que lo deja esperando) | Skill `reparar-plugin` si la evidencia es clara; si no, a `mejoras-pendientes.md` |
| `ruido` | Falso hallazgo del colector (sesión vieja ya cerrada) | Anótalo para afinar `scripts/vigilancia.py` |

Antes de llamar `bug` a algo, compara la versión que produjo el evento (`v` en session-handoff, la carpeta de
caché en Codex) con la del monorepo y revisa `plugins/<x>/docs/bitacora/versiones/`.

## 4. Reportar

Agrega una sección `## HH:MM` a `docs/vigilancia/reportes/AAAA-MM-DD.md` (créalo si no existe):

```markdown
## 14:30 · ventana 6h

| # | Clase | Plugin | Dónde | Hallazgo | Evidencia | Acción |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | bug | synapse | proyecto A, worktree 012 (codex, windows) | … | traza 03:32:51, rollout-…jsonl | reparar-plugin → 1.7.1 |
```

Al usuario dale solo lo accionable: qué se arregló, qué necesita su aprobación (con el comando exacto) y qué quedó
pendiente. Si no hubo hallazgos nuevos, dilo en una línea.

## Límites

- Nunca escribas en los proyectos vigilados ni en `~/.codex`, `~/.claude` o la configuración de WSL sin aprobación.
- Nunca apruebes un `ask` de Synapse por el usuario ni ejecutes `synapse.py approve`.
- No publiques releases ni etiquetes; eso lo decide el usuario (`AGENTS.md` §4).
