# Sondas de Payload (spec 001 · F1)

Plugin "sonda" que registra el stdin de cada hook (Codex, Antigravity) o cada evento en proceso (OpenCode) y responde neutro. Con las capturas se arman los fixtures de los tests de cada plugin.

| Archivo | Qué es |
| :--- | :--- |
| `plugin/` | La sonda: `probe.mjs` (hooks por subprocess), `codex-hooks.json`, `hooks.json` (Antigravity), `opencode.ts` |
| `.claude-plugin/marketplace.json` | Marketplace `probe-market` para instalarla en Codex |
| `run.sh` / `run.ps1` | Repo de prueba, instalación de la sonda y escenarios en WSL o Windows |
| `sanitize.py` | Capturas → `plugins/<x>/tests/fixtures/<host>/<os>/<versión>/`, sin rutas ni nombres personales |
| `../fake-llm/` | Modelo falso compatible con OpenAI (OpenCode sin costo y sin depender de la config global) |

```bash
tools/probe/run.sh codex|antigravity|opencode          # WSL
powershell -ExecutionPolicy Bypass -File tools\probe\run.ps1 -HostName codex -Sandbox danger-full-access   # Windows
tools/probe/sanitize.py <capturas> <host> <linux|windows> <versión>
```

- Codex usa un `CODEX_HOME` temporal con una copia de `auth.json`. `codex exec` corre por defecto con sandbox de solo lectura, así que para capturar escrituras usa `-s workspace-write` (WSL) o `danger-full-access` (Windows, donde `workspace-write` rechaza los comandos).
- La sonda solo guarda el **valor** de las variables de rutas del plugin. Del resto guarda el nombre, para que nunca se cuelen tokens heredados.
- Las respuestas que dieron las capturas están en [04 §10 del spec](https://github.com/bypabloc/agent-plugins/blob/synapse-v1.7.0/docs/specs/001-plugins-multi-agente/04-pruebas-y-verificacion.md#10-respuestas-de-f1-sondas-del-2026-11-20).
