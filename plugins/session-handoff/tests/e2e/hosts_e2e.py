#!/usr/bin/env python3
"""E2E de session-handoff con los binarios reales (spec 001 · 04 §6: E-05 y E-06).

  python3 tests/e2e/hosts_e2e.py [codex] [antigravity] [opencode]     (por defecto los tres)

Siembra un trabajo 012-x con Next step pendiente en la rama feature/012-x, corre el host con un prompt que intenta
cerrar el turno y verifica en tmp/handoff/.log/events.jsonl que el handoff se inyectó (inject) y que el fin de turno
no se dejó cerrar (stop.block). OpenCode usa el modelo falso (sin costo); Codex y Antigravity, las cuentas del usuario.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
MONOREPO = PLUGIN.parents[1]
WORK = MONOREPO / "tmp" / "e2e-handoff"
PROGRESS = ("Status: in-progress\nPhase: implementation\nDone: nada\nCurrent: probar\nRemaining: crear LISTO.txt\n"
            "ETA: ~1 min\nNext step: crear el archivo LISTO.txt con el texto ok\n")


def seed() -> Path:
    shutil.rmtree(WORK, ignore_errors=True)
    folder = WORK / "seed" / "tmp" / "handoff" / "012-x"
    folder.mkdir(parents=True)
    (folder / "PROGRESS.md").write_text(PROGRESS)
    (WORK / "seed" / ".gitignore").write_text("tmp/\n")
    script = WORK / "script.json"
    script.write_text(json.dumps([{"text": "Me detengo aquí."}, {"text": "Sigo."}, {"text": "Sigo."}, {"text": "Sigo."},
                                  {"text": "Sigo."}]))
    return WORK / "seed"


def events(repo: Path) -> list[str]:
    log = repo / "tmp" / "handoff" / ".log" / "events.jsonl"
    return [json.loads(line).get("event", "") for line in log.read_text().splitlines()] if log.exists() else []


def run(host: str) -> bool:
    seed_dir = seed()
    repo = WORK / f"repo-{host}"
    env = {**os.environ, "PROBE_REPO": str(repo), "PROBE_BRANCH": "feature/012-x", "PROBE_SEED": str(seed_dir),
           # Un prompt que no pide parar: "no hagas nada más" lo anota el agente como blocked — user-stop (válido)
           "PROBE_PROMPT": "Saluda con un hola.", "FAKE_SCRIPT": str(WORK / "script.json"),
           "OPENCODE_PLUGINS_JSON": json.dumps([str(PLUGIN)]), "CODEX_MARKET": str(MONOREPO),
           "CODEX_PLUGIN_REF": "session-handoff@bypabloc-agents", "AGY_PLUGIN_DIR": str(PLUGIN)}
    env.pop("CLAUDE_PROJECT_DIR", None)
    subprocess.run(["bash", str(MONOREPO / "tools" / "probe" / "run.sh"), host, "tools"], env=env, capture_output=True,
                   stdin=subprocess.DEVNULL, timeout=900, start_new_session=True)
    seen = events(repo)
    # E-05: el turno no cierra con el Next step pendiente: o el Stop se bloqueó, o el agente lo hizo (LISTO.txt)
    finished = (repo / "LISTO.txt").exists()
    ok = any(e.startswith("inject") for e in seen) and ("stop.block" in seen or finished)
    if finished:
        seen.append("LISTO.txt creado")
    print(f"{'✓' if ok else '✗'} {host}: {', '.join(seen) or 'sin eventos'}")
    if host == "opencode":
        calls = (repo / "fake-llm.jsonl").read_text().splitlines() if (repo / "fake-llm.jsonl").exists() else []
        mentions = [json.loads(c).get("handoff_mentions", 0) for c in calls]
        print(f"  requests al modelo: {len(calls)} · menciones del handoff por request: {mentions}")
    return ok


def main() -> int:
    hosts = sys.argv[1:] or ["codex", "antigravity", "opencode"]
    results = [run(h) for h in hosts if shutil.which("agy" if h == "antigravity" else h)]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
