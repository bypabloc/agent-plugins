#!/usr/bin/env python3
"""Colector de vigilancia: qué hicieron los plugins en los proyectos que los usan (Windows y WSL).

  scripts/vigilancia.py [--since 6h] [--json] [--env all|local]

Lee docs/vigilancia/proyectos.json y junta, sin modificar nada:
  - versiones instaladas (Claude Code y Codex) frente a las del marketplace del monorepo;
  - hooks de Codex (~/.codex/hooks.json) que apuntan a archivos inexistentes o que duplican a un plugin;
  - decisiones ask/block de Synapse y aprobaciones pendientes;
  - eventos de session-handoff por proyecto (tmp/handoff/.log/events.jsonl).
Con --env all en Windows, también se ejecuta dentro de WSL (wsl.exe) y une ambos resultados.
Termina con una lista de hallazgos heurísticos; la skill vigilar-plugins los clasifica.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs" / "vigilancia" / "proyectos.json"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
OUR_MARKETPLACES = ("bypabloc-agents", "bypabloc")
TAIL_BYTES = 4 * 1024 * 1024
BIG_INJECT = 8000
HOOK_SCRIPT_RE = re.compile(r"""(?:"|')?((?:[A-Za-z]:)?[/\\][^"'\s]+\.(?:py|cjs|mjs|js|ts|sh|cmd))""")


def env_name() -> str:
    return "windows" if os.name == "nt" else "wsl"


def parse_since(text: str) -> timedelta:
    match = re.fullmatch(r"(\d+)([mhd])", text.strip())
    if not match:
        raise argparse.ArgumentTypeError("usa 30m, 6h o 2d")
    value, unit = int(match.group(1)), match.group(2)
    return {"m": timedelta(minutes=value), "h": timedelta(hours=value), "d": timedelta(days=value)}[unit]


def read_tail_lines(path: Path) -> list[str]:
    try:
        with path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - TAIL_BYTES))
            data = handle.read()
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[1:] if size > TAIL_BYTES else lines


def parse_json_lines(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in read_tail_lines(path):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def parse_ts(value: Any, assume_local: bool) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.astimezone() if assume_local else ts.replace(tzinfo=timezone.utc)
    return ts


def expected_versions() -> dict[str, str]:
    try:
        data = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {p["name"]: p.get("version", "") for p in data.get("plugins", [])}


# --- Proyectos -----------------------------------------------------------------------------------------------

def project_dirs(config: dict[str, Any], env: str) -> list[tuple[str, Path]]:
    found: dict[str, tuple[str, Path]] = {}
    for project in config.get("projects", []):
        if project.get("env") != env:
            continue
        pattern = os.path.expanduser(project["path"])
        paths = sorted(glob.glob(pattern)) if project.get("glob") else [pattern]
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                label = project["name"] if not project.get("glob") else f"{project['name']}/{path.name}"
                found[str(path.resolve())] = (label, path)
    for rule in config.get("discover", []):
        if rule.get("env") != env:
            continue
        root = Path(os.path.expanduser(rule["root"]))
        for depth in range(1, int(rule.get("depth", 3)) + 1):
            pattern = str(root / Path(*(["*"] * depth)) / "tmp" / "handoff" / ".log" / "events.jsonl")
            for hit in glob.glob(pattern):
                path = Path(hit).parents[3]
                found.setdefault(str(path.resolve()), (f"(descubierto) {path.name}", path))
    return sorted(found.values(), key=lambda item: item[0])


def handoff_summary(label: str, path: Path, since: datetime) -> dict[str, Any] | None:
    log = path / "tmp" / "handoff" / ".log" / "events.jsonl"
    if not log.is_file():
        return None
    events = [e for e in parse_json_lines(log) if (parse_ts(e.get("ts"), False) or since) >= since]
    counts = Counter(str(e.get("event")) for e in events)
    foreign = [e for e in events if "v" not in e]
    injects = [int(e.get("chars", 0) or 0) for e in events if str(e.get("event", "")).startswith("inject")]
    return {
        "project": label,
        "path": str(path),
        "events": len(events),
        "by_event": dict(counts.most_common()),
        "versions": sorted({str(e["v"]) for e in events if "v" in e}),
        "hosts": sorted({str(e.get("host") or e.get("agent")) for e in events}),
        "foreign_writer": len(foreign),
        "max_inject_chars": max(injects, default=0),
        "stop_cap": sum(1 for e in events if e.get("event") == "stop.block" and e.get("reason") == "cap"),
        "sessions": len({e.get("session") for e in events}),
    }


# --- Synapse -------------------------------------------------------------------------------------------------

def synapse_state_dir() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "synapse"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "synapse"


def synapse_log_dirs() -> list[Path]:
    home = Path.home()
    dirs = [synapse_state_dir() / "logs", home / ".claude" / "logs" / "synapse"]
    dirs += [Path(p) for p in glob.glob(str(home / ".claude" / "*" / "logs" / "synapse"))]
    return [d for d in dirs if d.is_dir()]


def synapse_summary(since: datetime) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    for log_dir in synapse_log_dirs():
        files = sorted(log_dir.glob("*.jsonl"))[-3:]
        for log in files:
            rows = parse_json_lines(log)
            inputs = {r.get("run"): r for r in rows if r.get("step") == "input"}
            for row in rows:
                if row.get("step") != "decision" or row.get("decision") not in ("ask", "block"):
                    continue
                ts = parse_ts(row.get("ts"), True)
                if ts is None or ts < since:
                    continue
                src = inputs.get(row.get("run"), {})
                decisions.append({
                    "ts": row.get("ts"), "log": str(log_dir), "host": src.get("host", "claude"),
                    "decision": row.get("decision"), "rule": row.get("rule"), "hook": row.get("hook"),
                    "target": str(row.get("target") or src.get("command") or "")[:160],
                    "cwd": src.get("cwd", ""), "session": row.get("session"),
                })
    pending = synapse_state_dir() / "approvals" / "pending"
    return {
        "log_dirs": [str(d) for d in synapse_log_dirs()],
        "by_rule": dict(Counter(f"{d['host']} {d['decision']} {d['rule']}" for d in decisions).most_common()),
        "decisions": decisions[-40:],
        "pending_approvals": len(list(pending.glob("*.json"))) if pending.is_dir() else 0,
    }


# --- Instalaciones y hooks -----------------------------------------------------------------------------------

def claude_installs() -> list[dict[str, Any]]:
    home = Path.home() / ".claude"
    files = [home / "plugins" / "installed_plugins.json"] + [Path(p) for p in glob.glob(str(home / "*" / "plugins" / "installed_plugins.json"))]
    rows = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        profile = path.parents[1].name if path.parents[1] != home else "(default)"
        for key, installs in data.get("plugins", {}).items():
            name, _, market = key.partition("@")
            if market not in OUR_MARKETPLACES:
                continue
            for item in installs:
                rows.append({"host": "claude", "profile": profile, "plugin": name, "marketplace": market,
                             "scope": item.get("scope"), "version": item.get("version"),
                             "project": item.get("projectPath")})
    return rows


def codex_installs() -> list[dict[str, Any]]:
    rows = []
    cache = Path.home() / ".codex" / "plugins" / "cache"
    for market in OUR_MARKETPLACES:
        for plugin_dir in sorted((cache / market).glob("*")) if (cache / market).is_dir() else []:
            versions = sorted((p.name for p in plugin_dir.iterdir() if p.is_dir()), key=_semver_key)
            if versions:
                rows.append({"host": "codex", "profile": "~/.codex", "plugin": plugin_dir.name, "marketplace": market,
                             "scope": "cache", "version": versions[-1], "project": None})
    return rows


def codex_config() -> dict[str, Any]:
    base = Path.home() / ".codex"
    result: dict[str, Any] = {"marketplaces": {}, "hooks": [], "orphans": [], "handoff_hooks": 0, "synapse_hooks": 0}
    try:
        toml = (base / "config.toml").read_text(encoding="utf-8")
    except OSError:
        toml = ""
    for name, body in re.findall(r"(?ms)^\[marketplaces\.([^\]]+)\]\s*\n(.*?)(?=^\[|\Z)", toml):
        source = re.search(r'^source\s*=\s*["\'](.+?)["\']', body, re.M)
        result["marketplaces"][name.strip('"')] = source.group(1) if source else ""
    try:
        hooks = json.loads((base / "hooks.json").read_text(encoding="utf-8")).get("hooks", {})
    except (OSError, ValueError):
        hooks = {}
    for event, groups in hooks.items():
        for group in groups or []:
            for hook in group.get("hooks", []):
                command = str(hook.get("command", ""))
                result["hooks"].append({"event": event, "command": command[:200]})
                lowered = command.lower()
                result["handoff_hooks"] += "handoff" in lowered
                result["synapse_hooks"] += "synapse" in lowered
                for script in HOOK_SCRIPT_RE.findall(command):
                    if "$" not in script and not Path(script).exists():
                        result["orphans"].append({"event": event, "script": script})
    return result


def _semver_key(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3]) or (0,)


# --- Recolección y hallazgos ---------------------------------------------------------------------------------

def collect_local(since_delta: timedelta) -> dict[str, Any]:
    config = json.loads(REGISTRY.read_text(encoding="utf-8"))
    env = env_name()
    now = datetime.now(timezone.utc)
    since = now - since_delta
    projects = [s for label, path in project_dirs(config, env) if (s := handoff_summary(label, path, since))]
    return {
        "env": env, "collected_at": now.isoformat(timespec="seconds"),
        "installs": claude_installs() + codex_installs(), "codex": codex_config(),
        "synapse": synapse_summary(since), "handoff": projects,
    }


def collect_wsl(since: str, config: dict[str, Any]) -> dict[str, Any] | None:
    drive, rest = str(Path(__file__).resolve()).split(":", 1)
    script = f"/mnt/{drive.lower()}{rest.replace(chr(92), '/')}"
    distro = ["-d", config["wsl_distro"]] if config.get("wsl_distro") else []
    try:
        proc = subprocess.run(["wsl.exe", *distro, "-e", "python3", script, "--env", "local", "--json", "--since", since],
                              capture_output=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"env": "wsl", "error": f"{type(exc).__name__}: {exc}"}
    text = proc.stdout.decode("utf-8", errors="replace").replace("\x00", "")
    try:
        return json.loads(text[text.index("{"):])
    except ValueError:
        err = proc.stderr.decode("utf-8", errors="replace").replace("\x00", "")
        return {"env": "wsl", "error": (err or text)[-400:]}


def findings(envs: list[dict[str, Any]], expected: dict[str, str]) -> list[str]:
    out: list[str] = []
    for data in envs:
        env = data.get("env", "?")
        if "error" in data:
            out.append(f"[{env}] no se pudo recolectar: {data['error']}")
            continue
        for inst in data["installs"]:
            want = expected.get(inst["plugin"])
            if want and inst["version"] and _semver_key(inst["version"]) < _semver_key(want):
                where = inst["project"] or inst["scope"]
                out.append(f"[{env}] versión atrasada: {inst['plugin']} {inst['version']} < {want} "
                           f"({inst['host']} {inst['profile']}, {where}, marketplace {inst['marketplace']})")
            if inst["marketplace"] == "bypabloc":
                out.append(f"[{env}] instalado desde el marketplace viejo 'bypabloc': {inst['plugin']} "
                           f"({inst['host']} {inst['profile']}, {inst['project'] or inst['scope']})")
        codex = data["codex"]
        for orphan in codex["orphans"]:
            out.append(f"[{env}] hook de Codex huérfano ({orphan['event']}): {orphan['script']} no existe")
        if "bypabloc" in codex["marketplaces"]:
            out.append(f"[{env}] Codex aún tiene el marketplace 'bypabloc' ({codex['marketplaces']['bypabloc']})")
        if codex["handoff_hooks"]:
            out.append(f"[{env}] ~/.codex/hooks.json tiene {codex['handoff_hooks']} hooks de handoff propios: "
                       "pueden duplicar al plugin session-handoff")
        if codex["synapse_hooks"]:
            out.append(f"[{env}] ~/.codex/hooks.json declara Synapse a mano ({codex['synapse_hooks']}): "
                       "puede duplicar al plugin o quedar huérfano")
        syn = data["synapse"]
        for d in syn["decisions"]:
            if d["host"] == "codex" and d["decision"] == "ask":
                out.append(f"[{env}] Synapse pidió aprobación en Codex ({d['rule']}, {d['ts']}): {d['target']} "
                           "— revisa en el transcript si el agente se detuvo")
        if syn["pending_approvals"]:
            out.append(f"[{env}] {syn['pending_approvals']} aprobaciones de Synapse pendientes")
        for proj in data["handoff"]:
            if proj["foreign_writer"]:
                out.append(f"[{env}] {proj['project']}: {proj['foreign_writer']} eventos de handoff sin 'v' "
                           "(otro escritor además del plugin)")
            if proj["stop_cap"]:
                out.append(f"[{env}] {proj['project']}: {proj['stop_cap']} stop.block llegaron al tope (cap)")
            if proj["max_inject_chars"] > BIG_INJECT:
                out.append(f"[{env}] {proj['project']}: inyección de {proj['max_inject_chars']} caracteres")
            stale = [v for v in proj["versions"] if expected.get("session-handoff")
                     and _semver_key(v) < _semver_key(expected["session-handoff"])]
            if stale:
                out.append(f"[{env}] {proj['project']}: eventos de session-handoff {', '.join(stale)} "
                           "(sesiones con una versión vieja; pedir /reload-plugins o reiniciar)")
    return out


def render(envs: list[dict[str, Any]], expected: dict[str, str], since: str) -> str:
    lines = [f"# Vigilancia de plugins (últimas {since})", "",
             "Esperado: " + ", ".join(f"{k} {v}" for k, v in expected.items()), "", "## Hallazgos", ""]
    lines += [f"- {f}" for f in findings(envs, expected)] or ["- Sin hallazgos."]
    for data in envs:
        if "error" in data:
            continue
        lines += ["", f"## {data['env']} ({data['collected_at']})", "", "| Host | Perfil | Plugin | Versión | Scope |",
                  "| :--- | :--- | :--- | :--- | :--- |"]
        lines += [f"| {i['host']} | {i['profile']} | {i['plugin']}@{i['marketplace']} | {i['version']} | "
                  f"{i['project'] or i['scope']} |" for i in data["installs"]]
        syn = data["synapse"]
        lines += ["", "Synapse ask/block: " + (", ".join(f"{k} ×{v}" for k, v in syn["by_rule"].items()) or "ninguno")]
        for proj in data["handoff"]:
            top = ", ".join(f"{k} {v}" for k, v in list(proj["by_event"].items())[:6])
            lines.append(f"- handoff {proj['project']}: {proj['events']} eventos en {proj['sessions']} sesiones, "
                         f"v {'/'.join(proj['versions']) or '-'}; {top or 'sin eventos'}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default="6h", help="ventana hacia atrás: 30m, 6h, 2d (por defecto 6h)")
    parser.add_argument("--json", action="store_true", help="salida JSON en vez de markdown")
    parser.add_argument("--env", choices=("all", "local"), default="all")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    delta = parse_since(args.since)
    envs = [collect_local(delta)]
    if args.env == "all" and os.name == "nt":
        wsl = collect_wsl(args.since, json.loads(REGISTRY.read_text(encoding="utf-8")))
        if wsl:
            envs.append(wsl)
    if args.json:
        print(json.dumps(envs if args.env == "all" else envs[0], ensure_ascii=False, indent=1))
        return 0
    print(render(envs, expected_versions(), args.since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
