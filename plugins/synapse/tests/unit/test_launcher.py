"""Claude Code en Windows ejecuta los hooks de Synapse a través de hooks/run-hook.cmd.

Visto el 2026-11-21 en Claude Code (Windows): hooks/hooks.json llamaba `python3 …`, que en Windows resuelve al
acceso directo de Microsoft Store ("no se encontró Python; ejecutar sin argumentos para instalar…", exit 49). Cada
Edit, Write y Bash mostraba "PreToolUse hook failed" y Synapse no revisaba nada (falla abierto).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from support import PROJECT_DIR

HOOKS_JSON = json.loads((PROJECT_DIR / "hooks" / "hooks.json").read_text(encoding="utf-8"))
LAUNCHER = PROJECT_DIR / "hooks" / "run-hook.cmd"
COMMANDS = [h["command"] for group in HOOKS_JSON["hooks"]["PreToolUse"] for h in group["hooks"]]


def test_claude_hooks_go_through_the_launcher_not_a_bare_python3() -> None:
    assert COMMANDS
    for cmd in COMMANDS:
        assert not cmd.startswith("python"), cmd
        assert cmd.startswith('"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" '), cmd
        entry = cmd.split('" ', 1)[1].split()[0]
        assert (PROJECT_DIR / "hooks" / f"{entry}.py").is_file(), cmd


def _launch(payload: dict) -> subprocess.CompletedProcess[bytes]:
    cmd = ["cmd.exe", "/d", "/c", str(LAUNCHER)] if os.name == "nt" else ["sh", str(LAUNCHER)]
    env = {**os.environ, "SYNAPSE_PYTHON": f'"{sys.executable}"' if os.name == "nt" else sys.executable}
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONIOENCODING", None)
    return subprocess.run([*cmd, "block_dangerous"], input=json.dumps(payload).encode("utf-8"),
                          capture_output=True, env=env, timeout=60, check=False)


def test_launcher_keeps_claude_block_exit_code_and_utf8(tmp_path) -> None:
    proc = _launch({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                    "tool_input": {"command": "rm -rf /"}, "cwd": str(tmp_path)})
    assert proc.returncode == 2, proc.stderr
    assert "🚫 BLOCKED · Synapse" in proc.stderr.decode("utf-8")


@pytest.mark.skipif(os.name != "nt", reason="el bloque de cmd.exe solo corre en Windows")
def test_launcher_without_python_asks_in_claude(tmp_path) -> None:
    env = {"PATH": r"C:\Windows\System32", "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")}
    proc = subprocess.run(["cmd.exe", "/d", "/c", str(LAUNCHER), "block_dangerous"], input=b"{}",
                          capture_output=True, env=env, timeout=60, check=False)
    assert proc.returncode == 0
    out = json.loads(proc.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
