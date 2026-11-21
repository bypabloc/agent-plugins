# Mejoras pendientes

Ideas detectadas al vigilar el plugin que aún no se implementaron. Cada una dice qué se vio y por qué no se hizo
todavía. Al implementarla, muévela a su archivo de [versiones/](versiones/).

| Idea | Qué se vio | Por qué espera |
| :--- | :--- | :--- |
| Aviso de arranque más corto para sesiones de una sola pregunta | Decenas de sesiones cortas en worktrees recibían el aviso «sin trabajo vinculado» (unos 1.300 a 1.800 caracteres cada una). | Al iniciar no se sabe si la sesión será de una vuelta; recortarlo para todas empeora el caso normal. |
| Detectar `external-wait` sobre una tarea ya terminada | Una sesión siguió con la fase en `external-wait` sobre una tarea que había terminado; no llegó a soltar en falso. | `stop.recheck` (0.3.1) ya lo frena tras 3 paradas; detectarlo antes exige leer las notificaciones de tareas. |
| Avisar cuando un hash anotado desaparece de `PROGRESS.md` | Al resumir `Done`, una sesión quitó hashes que ya estaban anotados. | El plugin deja de seguir un hash en cuanto aparece; recordarlos todos exige guardar el historial de la sesión. |
| Sugerir `blocked` cuando `external-wait` espera al usuario | Sesiones con `Phase: external-wait` para «el usuario prueba la app». | Distinguirlo exige entender la nota; hoy funciona igual porque la sesión para. |
| Banda en los slots TUI de OpenCode (`session.composer.top`) | Opcional en el spec 001 (T-91): estado, fase y `ctx %` como en Claude Code. | Sin pedido real todavía; OpenCode no se usa en los proyectos vigilados. |
| `antigravity statusline` | Opcional en el spec 001 (T-92). | Igual que la anterior. |
| Statusline vía MCP de Codex (`tui_extensions_statusline`) | Opcional en el spec 001 (T-93); experimental en Codex. | La API de Codex no es estable. |
| Avisar cuando un hook propio del proyecto duplica al plugin | klinikae (Codex, WSL, 2026-11-21): `~/.codex/hooks.json` corría un `session_handoff.py` propio además del plugin; cada compactación inyectaba unos 14.600 caracteres más 3.500. | Hoy lo detecta `scripts/vigilancia.py` (eventos sin `v`); el plugin podría verlo en `SessionStart` leyendo los hooks del host. |
