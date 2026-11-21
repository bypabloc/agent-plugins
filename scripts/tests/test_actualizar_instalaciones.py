"""actualizar_instalaciones.py nunca quita una instalación sin que su reemplazo haya quedado instalado.

Visto el 2026-11-21: en dos perfiles con política empresarial, `marketplace add bypabloc-agents` falló y el script
igual desinstaló los plugins de `bypabloc` y quitó ese marketplace.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import actualizar_instalaciones as ai  # noqa: E402


def make_profile(home: Path) -> None:
    plugins = home / ".claude" / "work" / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "installed_plugins.json").write_text(json.dumps({"plugins": {
        "spanish-latam-style@bypabloc": [{"scope": "user", "version": "1.0.0"}],
    }}), encoding="utf-8")
    (plugins / "known_marketplaces.json").write_text(json.dumps({"bypabloc": {}}), encoding="utf-8")


def fake_run(failing: str):
    calls: list[str] = []

    def run(step: ai.Step) -> tuple[bool, str]:
        line = " ".join(step.cmd[1:])
        calls.append(line)
        return (failing not in line), "blocked by enterprise policy"
    return run, calls


def test_blocked_marketplace_removes_nothing(tmp_path, monkeypatch, capsys) -> None:
    make_profile(tmp_path)
    monkeypatch.setattr(ai.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(ai.shutil, "which", lambda name: name if name == "claude" else None)
    run, calls = fake_run("marketplace add")
    monkeypatch.setattr(ai, "run", run)

    assert ai.local(apply=True) == 1
    assert calls == ["plugin marketplace add bypabloc/agent-plugins"]
    assert "omitido" in capsys.readouterr().out


def test_failed_install_keeps_the_old_plugin(tmp_path, monkeypatch) -> None:
    make_profile(tmp_path)
    monkeypatch.setattr(ai.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(ai.shutil, "which", lambda name: name if name == "claude" else None)
    run, calls = fake_run("plugin install")
    monkeypatch.setattr(ai, "run", run)

    ai.local(apply=True)
    assert not [c for c in calls if "uninstall" in c or "marketplace remove" in c]


def test_successful_migration_removes_the_old_marketplace_last(tmp_path, monkeypatch) -> None:
    make_profile(tmp_path)
    monkeypatch.setattr(ai.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(ai.shutil, "which", lambda name: name if name == "claude" else None)
    run, calls = fake_run("nada falla")
    monkeypatch.setattr(ai, "run", run)

    assert ai.local(apply=True) == 0
    assert calls == [
        "plugin marketplace add bypabloc/agent-plugins",
        "plugin install spanish-latam-style@bypabloc-agents --scope user",
        "plugin uninstall spanish-latam-style@bypabloc --scope user",
        "plugin marketplace remove bypabloc",
    ]
