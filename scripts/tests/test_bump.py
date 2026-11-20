from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bump  # noqa: E402

MANIFEST = '{\n  "name": "alpha",\n  "version": "1.0.0",\n  "keywords": ["a", "b"]\n}\n'
MARKET = {
    "name": "m",
    "plugins": [
        {"name": "beta", "version": "2.0.0", "source": "./plugins/beta"},
        {"name": "alpha", "version": "1.0.0", "source": "./plugins/alpha"},
    ],
}


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name, version in (("alpha", "1.0.0"), ("beta", "2.0.0")):
        base = tmp_path / "plugins" / name
        (base / ".claude-plugin").mkdir(parents=True)
        (base / ".claude-plugin" / "plugin.json").write_text(MANIFEST.replace("alpha", name).replace("1.0.0", version))
        (base / "core.ts").write_text(f"export const VERSION = '{version}'\n")
        (base / ".version-bump.json").write_text(json.dumps({"files": [
            {"path": ".claude-plugin/plugin.json", "key": "version"},
            {"path": "core.ts", "regex": "VERSION = '([^']+)'"},
        ]}))
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(json.dumps(MARKET, indent=2))
    monkeypatch.setattr(bump, "ROOT", tmp_path)
    monkeypatch.setattr(bump, "PLUGINS", tmp_path / "plugins")
    monkeypatch.setattr(bump, "MARKETPLACE", tmp_path / ".claude-plugin" / "marketplace.json")
    return tmp_path


def test_check_passes_when_versions_match(repo: Path) -> None:
    assert bump.check() == []


def test_check_reports_drift(repo: Path) -> None:
    core = repo / "plugins" / "alpha" / "core.ts"
    core.write_text("export const VERSION = '1.0.1'\n")
    problems = bump.check()
    assert len(problems) == 1 and "alpha: versiones distintas" in problems[0]


def test_bump_writes_every_spot_and_only_its_marketplace_entry(repo: Path) -> None:
    assert bump.main(["alpha", "1.1.0"]) == 0
    manifest = (repo / "plugins" / "alpha" / ".claude-plugin" / "plugin.json").read_text()
    assert manifest == MANIFEST.replace("1.0.0", "1.1.0")  # formato intacto
    assert "VERSION = '1.1.0'" in (repo / "plugins" / "alpha" / "core.ts").read_text()
    market = json.loads((repo / ".claude-plugin" / "marketplace.json").read_text())
    assert {p["name"]: p["version"] for p in market["plugins"]} == {"alpha": "1.1.0", "beta": "2.0.0"}
    assert bump.check() == []


def test_bump_rejects_invalid_semver(repo: Path) -> None:
    with pytest.raises(SystemExit):
        bump.main(["alpha", "1.1"])


def test_bump_rejects_unknown_plugin(repo: Path) -> None:
    with pytest.raises(SystemExit):
        bump.main(["gamma", "1.0.0"])


def test_audit_lists_old_version_without_partial_matches(repo: Path) -> None:
    (repo / "plugins" / "alpha" / "README.md").write_text("Versión 1.0.0\nNo es 11.0.0 ni 1.0.01\n")
    hits = bump.audit("alpha", "1.0.0")
    assert any(h.endswith("README.md:1: Versión 1.0.0") for h in hits)
    assert not any("README.md:2" in h for h in hits)


def test_regex_needs_exactly_one_group(repo: Path) -> None:
    config = repo / "plugins" / "alpha" / ".version-bump.json"
    config.write_text(json.dumps({"files": [{"path": "core.ts", "regex": "VERSION = '[^']+'"}]}))
    with pytest.raises(ValueError):
        bump.spots("alpha")
