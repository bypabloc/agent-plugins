"""El registro de proyectos vigilados es local: no se versiona porque tiene rutas y nombres privados.

Sin `docs/vigilancia/proyectos.json`, el colector no debe caer con un traceback: dice cómo crearlo desde la
plantilla versionada `proyectos.example.json`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import vigilancia  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def test_sin_registro_explica_como_crearlo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vigilancia, "REGISTRY", tmp_path / "proyectos.json")
    assert vigilancia.main(["--env", "local"]) == 2
    err = capsys.readouterr().err
    assert "proyectos.example.json" in err
    assert "proyectos.json" in err


def test_el_registro_no_esta_versionado():
    ignored = subprocess.run(["git", "check-ignore", "-q", "docs/vigilancia/proyectos.json"], cwd=ROOT)
    assert ignored.returncode == 0
    report = subprocess.run(["git", "check-ignore", "-q", "docs/vigilancia/reportes/2099-01-01.md"], cwd=ROOT)
    assert report.returncode == 0


def test_la_plantilla_es_valida_y_generica():
    example = ROOT / "docs" / "vigilancia" / "proyectos.example.json"
    config = json.loads(example.read_text(encoding="utf-8"))
    assert config["projects"] and config["discover"]
    assert "bypabloc" not in example.read_text(encoding="utf-8")
