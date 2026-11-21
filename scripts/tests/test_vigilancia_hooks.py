"""vigilancia.py detecta los hooks que fallan en silencio (2026-11-21).

- Claude Code en Windows: `python3` era el acceso directo de Microsoft Store y cada tool registraba un
  `hook_non_blocking_error` en el transcript, sin que nadie lo informara.
- Codex: la sesión seguía en session-handoff 0.5.0 después de que la caché quedó solo con 0.5.2.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import vigilancia as vg  # noqa: E402

NOW = datetime.now(timezone.utc)


def test_claude_transcript_hook_failures_become_findings(tmp_path, monkeypatch) -> None:
    project = tmp_path / ".claude" / "work" / "projects" / "D--repo"
    project.mkdir(parents=True)
    row = {"type": "attachment", "timestamp": NOW.isoformat().replace("+00:00", "Z"), "cwd": "D:\\repo",
           "sessionId": "9c99b602-bf35", "attachment": {
               "type": "hook_non_blocking_error", "hookName": "PreToolUse:Edit", "exitCode": 49,
               "stderr": "Failed with non-blocking status code: no se encontró Python; ejecutar sin argumentos"}}
    (project / "s.jsonl").write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(vg.Path, "home", classmethod(lambda cls: tmp_path))

    errors = vg.claude_hook_errors(NOW - timedelta(hours=1))
    assert errors and errors[0]["count"] == 2 and errors[0]["profile"] == "work"
    env = {"env": "windows", "installs": [], "codex": {"orphans": [], "marketplaces": {}, "handoff_hooks": 0,
           "synapse_hooks": 0}, "synapse": {"decisions": [], "pending_approvals": 0}, "handoff": [],
           "hook_errors": errors, "codex_cache": {}}
    out = vg.findings([env], {})
    assert any("hook fallido en Claude Code ×2" in f and "no se encontró Python" in f for f in out)


def test_codex_session_on_a_version_missing_from_the_cache(tmp_path, monkeypatch) -> None:
    (tmp_path / ".codex" / "plugins" / "cache" / "bypabloc-agents" / "session-handoff" / "0.5.2").mkdir(parents=True)
    monkeypatch.setattr(vg.Path, "home", classmethod(lambda cls: tmp_path))
    env = {"env": "wsl", "installs": [], "codex": {"orphans": [], "marketplaces": {}, "handoff_hooks": 0,
           "synapse_hooks": 0}, "synapse": {"decisions": [], "pending_approvals": 0},
           "handoff": [{"project": "proyecto A", "versions": ["0.5.0"], "codex_versions": ["0.5.0"],
                        "foreign_writer": 0, "stop_cap": 0, "max_inject_chars": 0}],
           "hook_errors": [], "codex_cache": vg.codex_cache_versions()}
    out = vg.findings([env], {"session-handoff": "0.5.2"})
    assert any("ya no está en la caché" in f and "0.5.0" in f for f in out)
