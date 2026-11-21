#!/usr/bin/env python3
"""Release de un plugin del monorepo y publicación de su espejo.

  scripts/release.py <plugin> <versión>
      Rama release/<plugin>-<versión> desde HEAD, bump de todos los manifiestos, commit y (con --pr) PR a dev.
      Tras el merge a main, el tag <plugin>-v<versión> dispara .github/workflows/release.yml.

  scripts/release.py --mirror <plugin> [--ref main] [--push]
      git subtree split de plugins/<plugin> y publicación en su espejo: exige fast-forward contra el main del
      espejo, empuja los objetos LFS y etiqueta v<versión>. Sin --push solo verifica (dry-run).
      MIRROR_URL reemplaza la URL del espejo (la CI la usa con su deploy key).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import bump

ROOT = Path(__file__).resolve().parent.parent
MIRRORS = {
    "synapse": "git@github.com:bypabloc/agent-plugin-synapse.git",
    "session-handoff": "git@github.com:bypabloc/agent-plugin-session-handoff.git",
    "spanish-latam-style": "git@github.com:bypabloc/claude-plugin-spanish-latam.git",
}


def git(*args: str, check: bool = True, capture: bool = True) -> str:
    out = subprocess.run(["git", "-C", str(ROOT), *args], check=check, text=True,
                         stdout=subprocess.PIPE if capture else None)
    return (out.stdout or "").strip()


def plugin_version(plugin: str) -> str:
    manifest = ROOT / "plugins" / plugin / ".claude-plugin" / "plugin.json"
    return str(json.loads(manifest.read_text(encoding="utf-8"))["version"])


def prepare(plugin: str, version: str, open_pr: bool) -> int:
    if git("status", "--porcelain"):
        print("✗ hay cambios sin confirmar: el release parte de un árbol limpio", file=sys.stderr)
        return 1
    previous = plugin_version(plugin)
    branch = f"release/{plugin}-{version}"
    git("checkout", "-b", branch, capture=False)
    if bump.main([plugin, version]) != 0:
        return 1
    leftovers = bump.audit(plugin, previous)
    if leftovers:
        print(f"\nRevisa si estas apariciones de {previous} deben cambiar:")
        print("\n".join(f"  {hit}" for hit in leftovers))
    git("commit", "-am", f"chore(release): {plugin} {version}", capture=False)
    if open_pr:
        git("push", "-u", "origin", branch, capture=False)
        subprocess.run(["gh", "pr", "create", "--base", "dev", "--head", branch,
                        "--title", f"chore(release): {plugin} {version}",
                        "--body", f"Release de `{plugin}` {previous} → {version}. Tras el merge a main: "
                                  f"`git tag {plugin}-v{version} && git push origin {plugin}-v{version}`."],
                       check=True, cwd=ROOT)
    return 0


def mirror(plugin: str, ref: str, push: bool, expect: str | None, tag_it: bool = True) -> int:
    version = plugin_version(plugin)
    if expect and expect != version:
        print(f"✗ el tag pide {expect} pero {plugin} está en {version}", file=sys.stderr)
        return 1
    url = os.environ.get("MIRROR_URL") or MIRRORS[plugin]
    split_branch = f"mirror/{plugin}"
    print(f"→ split de plugins/{plugin} en {ref}")
    subprocess.run(["git", "-C", str(ROOT), "branch", "-D", split_branch], capture_output=True)
    git("subtree", "split", "-q", f"--prefix=plugins/{plugin}", ref, "-b", split_branch)
    head = git("rev-parse", split_branch)
    remote_ref = f"refs/mirrors/{plugin}"
    fetched = subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", url, f"+main:{remote_ref}"],
                             text=True, capture_output=True)
    if fetched.returncode == 0:
        is_ancestor = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", remote_ref, head])
        if is_ancestor.returncode != 0:
            print(f"✗ el main del espejo ({git('rev-parse', '--short', remote_ref)}) no es ancestro del split "
                  f"({head[:7]}): alguien empujó al espejo por fuera del release", file=sys.stderr)
            return 1
        ahead = git("rev-list", "--count", f"{remote_ref}..{head}")
        print(f"✓ fast-forward: {ahead} commits nuevos sobre el main del espejo")
    else:
        print("✓ el espejo no tiene main: primera publicación")
    tag = f"v{version}"
    if not push:
        print(f"(dry-run) se publicaría {head[:7]} en {url} main y el tag {tag}")
        return 0
    git("lfs", "push", url, split_branch, check=False, capture=False)
    git("push", url, f"{split_branch}:refs/heads/main", capture=False)
    if not tag_it:
        print(f"✓ {plugin} publicado en {url} sin tag (--no-tag)")
        return 0
    existing = subprocess.run(["git", "-C", str(ROOT), "ls-remote", "--tags", url, tag], text=True,
                              capture_output=True).stdout.split()
    if existing and existing[0] != head:
        print(f"✗ el tag {tag} ya existe en el espejo en otro commit ({existing[0][:7]})", file=sys.stderr)
        return 1
    if not existing:
        git("push", url, f"{head}:refs/tags/{tag}", capture=False)
    print(f"✓ {plugin} {version} publicado en {url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mirror", action="store_true", help="publicar (o verificar) el espejo del plugin")
    parser.add_argument("--ref", default="main", help="rama o commit del monorepo a publicar (por defecto main)")
    parser.add_argument("--push", action="store_true", help="con --mirror: publicar de verdad (si no, dry-run)")
    parser.add_argument("--expect-version", help="con --mirror: falla si el plugin no está en esta versión")
    parser.add_argument("--no-tag", action="store_true",
                        help="con --mirror: no etiquetar (publicación sin cambio de versión)")
    parser.add_argument("--pr", action="store_true", help="sin --mirror: empujar la rama y abrir el PR a dev")
    parser.add_argument("plugin", choices=sorted(MIRRORS))
    parser.add_argument("version", nargs="?")
    args = parser.parse_args(argv)
    if args.mirror:
        return mirror(args.plugin, args.ref, args.push, args.expect_version, tag_it=not args.no_tag)
    if not args.version:
        parser.error("falta la versión")
    return prepare(args.plugin, args.version, args.pr)


if __name__ == "__main__":
    sys.exit(main())
