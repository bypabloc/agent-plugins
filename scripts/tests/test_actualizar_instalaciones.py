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
        "plugin install session-handoff@bypabloc-agents --scope user",
        "plugin install spanish-latam-style@bypabloc-agents --scope user",
        "plugin install synapse@bypabloc-agents --scope user",
        "plugin uninstall spanish-latam-style@bypabloc --scope user",
        "plugin marketplace remove bypabloc",
    ]


def test_user_level_steps_run_from_home_not_from_the_repo(tmp_path, monkeypatch) -> None:
    # Visto el 2026-11-21: desde un worktree en /mnt/d, el git de WSL no lee su .git (ruta de Windows) y
    # `codex plugin marketplace upgrade` fallaba con "not a git repository"
    make_profile(tmp_path)
    monkeypatch.setattr(ai.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(ai.shutil, "which", lambda name: name if name == "claude" else None)
    steps, _ = ai.claude_steps({"spanish-latam-style"})
    assert steps and all(step.cwd == tmp_path for step in steps)


def test_project_copies_leave_once_the_user_one_is_enabled(tmp_path, monkeypatch) -> None:
    # Visto el 2026-11-21: session-handoff en user y dos veces en project; synapse solo en project y deshabilitado
    plugins = tmp_path / ".claude" / "work" / "plugins"
    plugins.mkdir(parents=True)
    project = tmp_path / "proyecto"
    project.mkdir()
    (plugins / "installed_plugins.json").write_text(json.dumps({"plugins": {
        "session-handoff@bypabloc-agents": [{"scope": "user"}, {"scope": "project", "projectPath": str(project)}],
        "synapse@bypabloc-agents": [{"scope": "project", "projectPath": str(project)}],
        "spanish-latam-style@bypabloc-agents": [{"scope": "user"}],
    }}), encoding="utf-8")
    (plugins / "known_marketplaces.json").write_text(json.dumps({"bypabloc-agents": {}}), encoding="utf-8")
    (plugins.parent / "settings.json").write_text(json.dumps({"enabledPlugins": {
        "spanish-latam-style@bypabloc-agents": False}}), encoding="utf-8")
    monkeypatch.setattr(ai.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(ai.shutil, "which", lambda name: name if name == "claude" else None)
    run, calls = fake_run("nada falla")
    monkeypatch.setattr(ai, "run", run)

    assert ai.local(apply=True) == 0
    assert calls == [
        "plugin marketplace update bypabloc-agents",
        "plugin update session-handoff@bypabloc-agents --scope user",
        "plugin update spanish-latam-style@bypabloc-agents --scope user",
        "plugin enable spanish-latam-style@bypabloc-agents --scope user",
        "plugin install synapse@bypabloc-agents --scope user",
        "plugin uninstall session-handoff@bypabloc-agents --scope project",
        "plugin uninstall synapse@bypabloc-agents --scope project",
    ]


def make_codex(home: Path, version: str = "0.5.0") -> Path:
    codex = home / ".codex"
    codex.mkdir(parents=True)
    (codex / "config.toml").write_text(
        '[marketplaces.bypabloc-agents]\n\n[plugins."session-handoff@bypabloc-agents"]\nenabled = true\n',
        encoding="utf-8")
    old = codex / "plugins" / "cache" / "bypabloc-agents" / "session-handoff" / version
    (old / "dist").mkdir(parents=True)
    (old / "dist" / "hook.mjs").write_text("// viejo", encoding="utf-8")
    return old


def test_codex_upgrade_keeps_the_previous_cache_for_open_sessions(tmp_path, monkeypatch, capsys) -> None:
    # Visto el 2026-11-21: `codex plugin marketplace upgrade` borró session-handoff/0.5.0 y synapse/1.7.0 de la
    # caché; las sesiones de Codex abiertas siguieron apuntando ahí y cada hook terminó en
    # "Hook failed: No such file or directory (os error 2)". En WSL, Synapse dejó de revisar los comandos.
    old = make_codex(tmp_path)
    monkeypatch.setattr(ai.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(ai.shutil, "which", lambda name: name if name == "codex" else None)

    def run(step: ai.Step) -> tuple[bool, str]:
        if "upgrade" in step.cmd:  # lo que hace Codex: la caché queda solo con la versión nueva
            ai.shutil.rmtree(old)
            (old.parent / "0.5.2" / "dist").mkdir(parents=True)
        return True, ""
    monkeypatch.setattr(ai, "run", run)

    assert ai.local(apply=True) == 0
    assert (old / "dist" / "hook.mjs").read_text(encoding="utf-8") == "// viejo"
    assert (old.parent / "0.5.2").is_dir()
    assert "session-handoff/0.5.0" in capsys.readouterr().out


def test_retained_cache_is_pruned_after_a_week(tmp_path, monkeypatch) -> None:
    old = make_codex(tmp_path, "0.4.0")
    (old / ai.KEEP_MARK).write_text("2026-11-01T00:00:00+00:00", encoding="utf-8")
    recent = old.parent / "0.5.0"
    recent.mkdir()
    (recent / ai.KEEP_MARK).write_text("2026-11-20T00:00:00+00:00", encoding="utf-8")
    current = old.parent / "0.5.2"
    current.mkdir()
    monkeypatch.setattr(ai.Path, "home", classmethod(lambda cls: tmp_path))

    ai.codex_prune(now=ai.datetime(2026, 11, 21, tzinfo=ai.timezone.utc))
    assert not old.exists() and recent.is_dir() and current.is_dir()
