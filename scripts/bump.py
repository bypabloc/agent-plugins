#!/usr/bin/env python3
"""Versiones de cada plugin del monorepo: una sola versión escrita en todos sus manifiestos.

Cada plugin declara en `plugins/<x>/.version-bump.json` los archivos donde vive su versión:
  {"path": "...", "key": "version"}   clave `"version"` de un JSON (la primera, con su formato intacto)
  {"path": "...", "regex": "..."}     el primer grupo de la regex es la versión
La entrada del plugin en `.claude-plugin/marketplace.json` de la raíz se suma sola.

Uso:
  scripts/bump.py <plugin> <versión>   escribe la versión en todos los archivos
  scripts/bump.py --check              falla si algún plugin tiene versiones distintas
  scripts/bump.py --audit <plugin> <versión-anterior>   lista dónde sigue apareciendo la versión anterior
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
JSON_VERSION = re.compile(r'"version"\s*:\s*"([^"]*)"')
AUDIT_SKIP = {".git", "node_modules", "models", "tmp", ".test_repos", "__pycache__", ".venv"}


@dataclass(frozen=True)
class Spot:
    path: Path
    pattern: re.Pattern[str]
    label: str
    start: int = 0  # posición desde la que se busca (entrada del plugin en el marketplace)


def plugin_names() -> list[str]:
    return sorted(p.name for p in PLUGINS.iterdir() if (p / ".version-bump.json").is_file())


def _marketplace_spot(plugin: str) -> Spot | None:
    if not MARKETPLACE.is_file():
        return None
    text = MARKETPLACE.read_text(encoding="utf-8")
    entry = re.search(r'"name"\s*:\s*"' + re.escape(plugin) + '"', text)
    if entry is None:
        return None
    return Spot(MARKETPLACE, JSON_VERSION, f"{MARKETPLACE.relative_to(ROOT)} [{plugin}]", entry.end())


def spots(plugin: str) -> list[Spot]:
    base = PLUGINS / plugin
    config = json.loads((base / ".version-bump.json").read_text(encoding="utf-8"))
    found: list[Spot] = []
    for item in config["files"]:
        path = base / item["path"]
        if "regex" in item:
            pattern = re.compile(item["regex"])
            if pattern.groups != 1:
                raise ValueError(f"La regex debe tener exactamente un grupo: {item['regex']}")
            found.append(Spot(path, pattern, str(path.relative_to(ROOT))))
        elif item.get("key") == "version":
            found.append(Spot(path, JSON_VERSION, str(path.relative_to(ROOT))))
        else:
            raise ValueError(f"Entrada inválida en {base / '.version-bump.json'}: {item}")
    market = _marketplace_spot(plugin)
    if market is not None:
        found.append(market)
    return found


def read_version(spot: Spot) -> str | None:
    match = spot.pattern.search(spot.path.read_text(encoding="utf-8"), spot.start)
    return match.group(1) if match else None


def write_version(spot: Spot, version: str) -> None:
    text = spot.path.read_text(encoding="utf-8")
    match = spot.pattern.search(text, spot.start)
    if match is None:
        raise ValueError(f"No se encontró la versión en {spot.label}")
    new = text[: match.start(1)] + version + text[match.end(1) :]
    spot.path.write_text(new, encoding="utf-8")


def check() -> list[str]:
    problems: list[str] = []
    for plugin in plugin_names():
        versions = {spot.label: read_version(spot) for spot in spots(plugin)}
        missing = [label for label, v in versions.items() if v is None]
        problems += [f"{plugin}: sin versión en {label}" for label in missing]
        distinct = {v for v in versions.values() if v is not None}
        if len(distinct) > 1:
            detail = ", ".join(f"{label}={v}" for label, v in versions.items())
            problems.append(f"{plugin}: versiones distintas ({detail})")
    return problems


def audit(plugin: str, old: str) -> list[str]:
    hits: list[str] = []
    needle = re.compile(r"(?<![\d.])" + re.escape(old) + r"(?![\d.])")
    for path in sorted((PLUGINS / plugin).rglob("*")):
        # Lo omitido se descarta antes de tocar el disco: en Windows, tmp/ puede tener archivos que dejó WSL sin acceso
        if AUDIT_SKIP & set(path.relative_to(ROOT).parts) or path.name.endswith(".lock"):
            continue
        try:
            if not path.is_file():
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        hits += [f"{path.relative_to(ROOT)}:{n}: {line.strip()}" for n, line in enumerate(lines, 1) if needle.search(line)]
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="falla si un plugin tiene versiones distintas")
    parser.add_argument("--audit", action="store_true", help="lista apariciones de la versión anterior")
    parser.add_argument("plugin", nargs="?")
    parser.add_argument("version", nargs="?")
    args = parser.parse_args(argv)

    if args.check:
        problems = check()
        for problem in problems:
            print(f"✗ {problem}", file=sys.stderr)
        if not problems:
            print("✓ versiones sincronizadas: " + ", ".join(f"{p} {read_version(spots(p)[0])}" for p in plugin_names()))
        return 1 if problems else 0

    if args.plugin not in plugin_names():
        parser.error(f"plugin desconocido: {args.plugin!r} (disponibles: {', '.join(plugin_names())})")
    if not args.version:
        parser.error("falta la versión")

    if args.audit:
        for hit in audit(args.plugin, args.version):
            print(hit)
        return 0

    if not SEMVER.match(args.version):
        parser.error(f"versión inválida (SemVer): {args.version!r}")
    for spot in spots(args.plugin):
        before = read_version(spot)
        write_version(spot, args.version)
        print(f"{spot.label}: {before} → {args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
