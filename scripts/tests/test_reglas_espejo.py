"""Las reglas de `.agents/rules/` son copia exacta de las de `.claude/rules/` con el mismo nombre.

Claude Code lee `.claude/rules/`; Codex y otros agentes, `.agents/rules/`. Si divergen, cada host sigue un flujo
distinto.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cada_regla_de_agents_es_identica_a_la_de_claude() -> None:
    agents = sorted((ROOT / ".agents" / "rules").glob("*.md"))
    assert agents, "falta .agents/rules/"
    for regla in agents:
        claude = ROOT / ".claude" / "rules" / regla.name
        assert claude.is_file(), f"{regla.name} existe en .agents/rules/ pero no en .claude/rules/"
        assert regla.read_bytes() == claude.read_bytes(), f"{regla.name} difiere entre .agents/ y .claude/"


def test_la_regla_de_flujo_esta_en_ambos_lados() -> None:
    assert (ROOT / ".agents" / "rules" / "flujo.md").is_file()
    assert (ROOT / ".claude" / "rules" / "flujo.md").is_file()
