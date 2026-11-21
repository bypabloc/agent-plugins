#!/usr/bin/env python3
"""Actualiza los plugins del monorepo en todos los CLI de la máquina (Windows y WSL) tras un release.

  scripts/actualizar_instalaciones.py            plan (dry-run): qué se ejecutaría en cada perfil y CLI
  scripts/actualizar_instalaciones.py --apply    lo ejecuta
  scripts/actualizar_instalaciones.py --env local --apply   solo este entorno (lo usa la llamada a WSL)

Claude Code, en cada perfil (~/.claude y ~/.claude/<perfil> con CLAUDE_CONFIG_DIR):
  - agrega o actualiza el marketplace bypabloc-agents;
  - deja cada plugin del marketplace una sola vez, en scope user y habilitado;
  - quita las demás copias (marketplace viejo, scope project o local desde la carpeta del proyecto, lo que cambia su
    .claude/settings.json), siempre después de que la de user quedó lista, y luego el marketplace viejo.
Codex (~/.codex): refresca bypabloc-agents, migra desde bypabloc, reinstala la última versión y quita el viejo.
Además retiene en la caché las versiones que Codex reemplaza (7 días), porque las sesiones abiertas siguen
ejecutando los hooks desde la carpeta de la versión con que arrancaron.

No automatiza la confianza de hooks de Codex: tras actualizar, el usuario corre /hooks en Codex (Codex ata cada
hook al hash de su contenido y un hook cambiado no corre hasta volver a confiar en él).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
NEW, OLD = "bypabloc-agents", "bypabloc"
SOURCE = "bypabloc/agent-plugins"
TIMEOUT = 600


@dataclass
class Step:
    where: str
    cmd: list[str]
    cwd: Path = field(default_factory=Path.home)  # fuera del repo: en WSL, un worktree en /mnt/d rompe git
    env: dict[str, str] = field(default_factory=dict)
    unset: tuple[str, ...] = ()
    needs: tuple[int, ...] = ()  # índices de pasos que deben salir bien antes (si no, este se omite)

    def show(self) -> str:
        prefix = " ".join(f"{k}={v}" for k, v in self.env.items())
        place = "" if self.cwd == Path.home() else f"  (en {self.cwd})"
        return f"[{self.where}] {prefix + ' ' if prefix else ''}{' '.join(self.cmd)}{place}"


def our_plugins() -> set[str]:
    data = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    return {p["name"] for p in data.get("plugins", [])}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def env_label() -> str:
    return "windows" if os.name == "nt" else "wsl"


# --- Claude Code -----------------------------------------------------------------------------------------------

def claude_profiles() -> list[tuple[str, Path]]:
    home = Path.home() / ".claude"
    profiles = []
    if (home / "plugins" / "installed_plugins.json").is_file():
        profiles.append(("(default)", home))
    for path in sorted(glob.glob(str(home / "*" / "plugins" / "installed_plugins.json"))):
        profile = Path(path).parents[1]
        profiles.append((profile.name, profile))
    return profiles


def claude_steps(ours: set[str]) -> tuple[list[Step], list[str]]:
    """Estado deseado por perfil: cada plugin del marketplace, una sola vez, en scope user y habilitado."""
    exe = shutil.which("claude")
    steps: list[Step] = []
    notes: list[str] = []
    for name, profile in claude_profiles():
        where = f"{env_label()} claude {name}"
        installed = load_json(profile / "plugins" / "installed_plugins.json").get("plugins", {})
        markets = load_json(profile / "plugins" / "known_marketplaces.json")
        mine = [(key.partition("@")[0], key.partition("@")[2], item) for key, items in installed.items()
                for item in items if key.partition("@")[0] in ours and key.partition("@")[2] in (OLD, NEW)]
        if not mine and NEW not in markets:
            continue
        if exe is None:
            notes.append(f"[{where}] sin `claude` en el PATH")
            continue
        env = {} if name == "(default)" else {"CLAUDE_CONFIG_DIR": str(profile)}
        unset = ("CLAUDE_CONFIG_DIR",) if name == "(default)" else ()
        enabled = load_json(profile / "settings.json").get("enabledPlugins", {})

        def mk(cmd: list[str], cwd: Path | None = None, needs: tuple[int, ...] = ()) -> int:
            steps.append(Step(where, [exe, *cmd], cwd or Path.home(), env, unset, needs))
            return len(steps) - 1

        # Sin el marketplace nuevo (p. ej. bloqueado por una política empresarial) no se toca nada del perfil
        market_idx = mk(["plugin", "marketplace", "update", NEW] if NEW in markets
                        else ["plugin", "marketplace", "add", SOURCE])
        at_user = {p for p, m, i in mine if m == NEW and i.get("scope", "user") == "user"}
        ready: dict[str, int] = {}
        for plugin in sorted(ours):
            key = f"{plugin}@{NEW}"
            if plugin in at_user:
                ready[plugin] = mk(["plugin", "update", key, "--scope", "user"], needs=(market_idx,))
                if enabled.get(key) is False:
                    ready[plugin] = mk(["plugin", "enable", key, "--scope", "user"], needs=(ready[plugin],))
            else:
                ready[plugin] = mk(["plugin", "install", key, "--scope", "user"], needs=(market_idx,))
        # Toda otra copia (marketplace viejo, o scope project/local) sobra: se quita solo con la de user lista
        removed: list[int] = []
        for plugin, market, item in mine:
            scope, project = item.get("scope", "user"), item.get("projectPath")
            if market == NEW and scope == "user":
                continue
            cwd = Path(project) if project else Path.home()
            if scope in ("project", "local") and not cwd.is_dir():
                notes.append(f"[{where}] {plugin}@{market} ({scope}) en {project}: la carpeta no existe, se omite")
                continue
            removed.append(mk(["plugin", "uninstall", f"{plugin}@{market}", "--scope", scope], cwd, (ready[plugin],)))
            if scope in ("project", "local"):
                notes.append(f"[{where}] {plugin} sale del scope {scope}: cambia {cwd / '.claude' / 'settings.json'}")
        others = [k for k in installed if k.endswith(f"@{OLD}") and k.partition("@")[0] not in ours]
        if OLD in markets and not others:
            mk(["plugin", "marketplace", "remove", OLD], needs=(market_idx, *removed))
    return steps, notes


# --- Codex ---------------------------------------------------------------------------------------------------

def codex_steps(ours: set[str]) -> tuple[list[Step], list[str]]:
    exe = shutil.which("codex")
    config = Path.home() / ".codex" / "config.toml"
    where = f"{env_label()} codex"
    if not config.is_file():
        return [], []
    if exe is None:
        return [], [f"[{where}] sin `codex` en el PATH"]
    text = config.read_text(encoding="utf-8")
    markets = set(re.findall(r'(?m)^\[marketplaces\.\"?([^\]"]+)\"?\]', text))
    plugins = re.findall(r'(?m)^\[plugins\."([^"@]+)@([^"]+)"\]', text)
    mine = [(p, m) for p, m in plugins if p in ours and m in (OLD, NEW)]
    if not mine:
        return [], []
    steps = [Step(where, [exe, "plugin", "marketplace", "upgrade", NEW] if NEW in markets
                  else [exe, "plugin", "marketplace", "add", SOURCE])]
    removed: list[int] = []
    for plugin in sorted(ours):  # todos los del marketplace, como en Claude Code
        steps.append(Step(where, [exe, "plugin", "add", f"{plugin}@{NEW}"], needs=(0,)))
        if (plugin, OLD) in mine:
            steps.append(Step(where, [exe, "plugin", "remove", f"{plugin}@{OLD}"], needs=(len(steps) - 1,)))
            removed.append(len(steps) - 1)
    if OLD in markets and not [p for p, m in plugins if m == OLD and p not in ours]:
        steps.append(Step(where, [exe, "plugin", "marketplace", "remove", OLD], needs=(0, *removed)))
    return steps, [f"[{where}] tras actualizar, abre Codex y ejecuta /hooks para confiar en los hooks nuevos"]


# Visto el 2026-11-21: `codex plugin marketplace upgrade` deja en la caché solo la versión nueva. Las sesiones de
# Codex abiertas conservan la ruta de la versión que cargaron al arrancar, así que cada hook terminaba en
# "Hook failed: No such file or directory (os error 2)" (y Synapse dejaba de revisar los comandos: falla abierto).
# Por eso se retienen las versiones previas, marcadas con KEEP_MARK, hasta KEEP_DAYS después de reemplazarlas.
KEEP_MARK = ".retenida-por-actualizar-instalaciones"
KEEP_DAYS = 7


def codex_cache() -> Path:
    return Path.home() / ".codex" / "plugins" / "cache" / NEW


def codex_holding() -> Path:
    return Path.home() / ".codex" / "plugins" / f".{NEW}-previas"


def _link_or_copy(src: str, dst: str) -> None:
    try:
        os.link(src, dst)  # sin duplicar los ~100 MB del modelo de Synapse
    except OSError:
        shutil.copy2(src, dst)


def codex_snapshot() -> None:
    """Guarda (con enlaces duros) cada versión que hay hoy en la caché, antes de que Codex la reemplace."""
    holding = codex_holding()
    shutil.rmtree(holding, ignore_errors=True)
    for version_dir in sorted(codex_cache().glob("*/*")):
        if version_dir.is_dir():
            target = holding / version_dir.parent.name / version_dir.name
            shutil.copytree(version_dir, target, copy_function=_link_or_copy, symlinks=True)


def codex_restore(now: datetime | None = None) -> list[str]:
    """Devuelve a la caché las versiones que Codex borró, para las sesiones que aún las usan."""
    holding = codex_holding()
    restored = []
    stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    for saved in sorted(holding.glob("*/*")):
        target = codex_cache() / saved.parent.name / saved.name
        if saved.is_dir() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(saved), str(target))
            (target / KEEP_MARK).write_text(stamp, encoding="utf-8")
            restored.append(f"{saved.parent.name}/{saved.name}")
    shutil.rmtree(holding, ignore_errors=True)
    return restored


def codex_prune(now: datetime | None = None) -> list[str]:
    """Borra las versiones retenidas hace más de KEEP_DAYS: ninguna sesión abierta debería seguir en ellas."""
    now = now or datetime.now(timezone.utc)
    pruned = []
    for mark in sorted(codex_cache().glob(f"*/*/{KEEP_MARK}")):
        try:
            kept_at = datetime.fromisoformat(mark.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if now - kept_at > timedelta(days=KEEP_DAYS):
            shutil.rmtree(mark.parent, ignore_errors=True)
            pruned.append(f"{mark.parent.parent.name}/{mark.parent.name}")
    return pruned


# --- Ejecución -----------------------------------------------------------------------------------------------

def run(step: Step) -> tuple[bool, str]:
    env = {k: v for k, v in os.environ.items() if k not in step.unset}
    env.update(step.env)
    try:
        proc = subprocess.run(step.cmd, cwd=str(step.cwd), env=env, capture_output=True, timeout=TIMEOUT,
                              stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    out = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip().splitlines()
    return proc.returncode == 0, (out[-1] if out else "")


def local(apply: bool) -> int:
    ours = our_plugins()
    steps, notes = claude_steps(ours)
    codex, codex_notes = codex_steps(ours)
    offset = len(steps)
    steps += [Step(s.where, s.cmd, s.cwd, s.env, s.unset, tuple(i + offset for i in s.needs)) for s in codex]
    notes += codex_notes
    failed = 0
    ok_by_index: dict[int, bool] = {}
    if apply and codex:
        codex_snapshot()
    for index, step in enumerate(steps):
        if not apply:
            print(f"(plan) {step.show()}")
            continue
        if not all(ok_by_index.get(i, False) for i in step.needs):
            ok_by_index[index] = False
            print(f"- {step.show()}  → omitido: falló un paso previo (no se quita nada sin reemplazo)")
            continue
        ok, last = run(step)
        ok_by_index[index] = ok
        failed += not ok
        print(f"{'✓' if ok else '✗'} {step.show()}{'' if ok else '  → ' + last}")
    if apply and codex:
        where = f"{env_label()} codex"
        restored = codex_restore()
        if restored:
            notes.append(f"[{where}] versiones previas retenidas {KEEP_DAYS} días para las sesiones abiertas: "
                         f"{', '.join(restored)}. Reinicia esas sesiones de Codex para que usen la nueva")
        pruned = codex_prune()
        if pruned:
            notes.append(f"[{where}] versiones retenidas que vencieron y se borraron: {', '.join(pruned)}")
    for note in notes:
        print(f"· {note}")
    if not steps:
        print(f"[{env_label()}] nada que actualizar")
    return 1 if failed else 0


def wsl(apply: bool) -> int:
    drive, rest = str(Path(__file__).resolve()).split(":", 1)
    script = f"/mnt/{drive.lower()}{rest.replace(chr(92), '/')}"
    args = f"python3 '{script}' --env local" + (" --apply" if apply else "")
    try:
        proc = subprocess.run(["wsl.exe", "-e", "bash", "-lc", args], capture_output=True, timeout=TIMEOUT * 4, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[wsl] no se pudo ejecutar: {exc}")
        return 1
    print((proc.stdout + proc.stderr).decode("utf-8", errors="replace").replace("\x00", "").rstrip())
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="ejecutar (sin esto, solo muestra el plan)")
    parser.add_argument("--env", choices=("all", "local"), default="all")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    code = local(args.apply)
    if args.env == "all" and os.name == "nt":
        code |= wsl(args.apply)
    return code


if __name__ == "__main__":
    sys.exit(main())
