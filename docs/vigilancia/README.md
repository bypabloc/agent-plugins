# Vigilancia de los plugins

Este monorepo vigila cómo se comportan sus plugins en los proyectos reales que los usan, y los repara o mejora
con evidencia. El objetivo es que cada plugin sea **autosuficiente**: que un agente trabajando horas en Codex o
Claude Code no se detenga, no se confunda y no reciba texto roto por culpa del plugin.

## Piezas

| Pieza | Qué hace |
| :--- | :--- |
| `proyectos.json` | Registro **local** (ignorado por git) de los proyectos vigilados; se crea desde [`proyectos.example.json`](proyectos.example.json): entorno (`windows` o `wsl`), ruta, hosts y plugins. Más reglas `discover` para encontrar proyectos nuevos con `tmp/handoff/.log/` |
| [`scripts/vigilancia.py`](../../scripts/vigilancia.py) | Colector determinista y de solo lectura. Junta versiones instaladas, hooks de Codex, decisiones de Synapse y eventos de session-handoff de Windows y de WSL (`wsl.exe`) y lista hallazgos heurísticos |
| Skill [`vigilar-plugins`](../../.claude/skills/vigilar-plugins/SKILL.md) | Corre el colector, lee los transcripts de los hallazgos y clasifica cada uno (entorno, versión vieja, bug, mejora). Deja un reporte local en [`reportes/`](reportes/) (ignorado por git) |
| [`scripts/actualizar_instalaciones.py`](../../scripts/actualizar_instalaciones.py) | Tras un release, migra y actualiza los plugins en todos los perfiles de Claude Code y en Codex, en Windows y WSL (plan por defecto, `--apply` para ejecutar) |
| Skill [`reparar-plugin`](../../.claude/skills/reparar-plugin/SKILL.md) | Convierte un hallazgo de tipo bug o mejora en un test que falla, el arreglo, la versión y la entrada de bitácora, en una rama con PR a `dev`, y cierra el ciclo: merge a `dev` y `main`, release y actualización de los CLI |
| Rule [`vigilancia.md`](../../.claude/rules/vigilancia.md) | Cuándo vigilar, qué se corrige sin preguntar y qué requiere al usuario |
| Bitácora de cada plugin | `plugins/<x>/docs/bitacora/vigilancia.md` (fuentes y síntomas propios), `versiones/`, `aprendizajes.md`, `mejoras-pendientes.md` |

## Uso

```bash
python scripts/vigilancia.py --since 6h          # reporte markdown (Windows + WSL)
python scripts/vigilancia.py --since 2d --json   # datos crudos para la skill
```

En una sesión de Claude Code de este repo: "revisa cómo van los plugins" activa la skill. Para vigilancia continua
mientras la sesión esté abierta: `/loop 30m revisa cómo van los plugins`.

## Agregar un proyecto

Suma una entrada a `projects` en `proyectos.json` (si no existe, copia `proyectos.example.json`) (`env`, `path`, `hosts`, `plugins`; `glob: true`
para una carpeta de worktrees). Un proyecto con `tmp/handoff/.log/events.jsonl` bajo una raíz de `discover` aparece
solo, marcado como `(descubierto)`.
