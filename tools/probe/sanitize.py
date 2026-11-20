#!/usr/bin/env python3
"""Convierte capturas de la sonda en fixtures versionables (spec 001 · 04 §2).

Reemplaza rutas personales por marcadores, deja solo el entorno seguro y copia a cada plugin los eventos que usa:
  synapse         → hooks previos a tools (PreToolUse / tool-before)
  session-handoff → inicio, prompt, fin de turno, post-tool, invocaciones, contexto y fin de ejecución

Uso: tools/probe/sanitize.py <dir-capturas> <host> <os> <versión>
Escribe plugins/<plugin>/tests/fixtures/<host>/<os>/<versión>/<evento>[-<tool>]-<n>.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SAFE_ENV = {"PLUGIN_ROOT", "PLUGIN_DATA", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA", "CODEX_HOME"}
# Rutas personales → marcadores estables (más largas primero)
PATHS = [
    (re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\"]+\\\\AppData\\\\Local\\\\Temp\\\\agent-plugins-probe\\\\repo-[a-z]+"), "{project}"),
    (re.compile(r"[A-Za-z]:\\Users\\[^\\\"]+\\AppData\\Local\\Temp\\agent-plugins-probe\\repo-[a-z]+"), "{project}"),
    (re.compile(r"/home/[^/\"]+/[^\"]*?/tmp/probe-repos/[a-z]+"), "{project}"),
    (re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\"]+"), "{home}"),
    (re.compile(r"[A-Za-z]:\\Users\\[^\\\"]+"), "{home}"),
    (re.compile(r"/home/[^/\"]+"), "{home}"),
]
SYNAPSE = re.compile(r"^(PreToolUse|tool-before)")
HANDOFF = re.compile(r"^(SessionStart|UserPromptSubmit|Stop|PostToolUse|PreToolUse-(request_user_input|ask_question|question)|"
                     r"PreInvocation|tool-after|tool-before-question|session-context|session-compaction|"
                     r"event-session\.execution\.succeeded)")


MONOREPO = re.compile(r"\{home\}[/\\]+projects[^\"]*?agent-plugins")


def clean(text: str) -> str:
    for pattern, marker in PATHS:
        text = pattern.sub(marker, text)
    text = MONOREPO.sub("{monorepo}", text)
    return re.sub(r"\b(bypabloc|pacg1)\b", "user", text)


def fixture(path: Path) -> dict[str, Any]:
    data = json.loads(clean(path.read_text(encoding="utf-8")))
    if "stdin" in data:  # hooks por subprocess
        env = {k: v for k, v in data.get("env", {}).items() if k in SAFE_ENV}
        return {"stdin": data["stdin"], "env": env, "platform": data.get("platform", "")}
    return {"event": data}  # OpenCode en proceso


def stem(name: str) -> str:
    return re.sub(r"-\d+-\d+\.json$", "", name)


def main() -> int:
    if len(sys.argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2
    source, host, os_name, version = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
    counts: dict[str, int] = {}
    for path in sorted(source.glob("*.json"), key=lambda p: p.name.split("-")[-2] if "-" in p.name else p.name):
        name = stem(path.name)
        for plugin, wanted in (("synapse", SYNAPSE), ("session-handoff", HANDOFF)):
            if not wanted.match(name):
                continue
            key = f"{plugin}/{name}"
            counts[key] = counts.get(key, 0) + 1
            if counts[key] > 3:  # bastan tres ejemplos por evento y tool
                continue
            out = ROOT / "plugins" / plugin / "tests" / "fixtures" / host / os_name / version / f"{name}-{counts[key]}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(fixture(path), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for key in sorted(counts):
        print(f"{key}: {min(counts[key], 3)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
