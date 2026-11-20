#!/usr/bin/env bash
# Corre los escenarios de SCENARIOS.md con la sonda instalada en un repo de prueba (spec 001 · 04 §2).
# Uso: tools/probe/run.sh <codex|antigravity|opencode> [escenario...]   (por defecto: tools question)
# Las capturas quedan en tmp/probe-repos/<host>/tmp/probe/<host>/.
set -euo pipefail

HOST="${1:?host}"; shift
SCENARIOS=("${@:-tools question}")
[ "${#SCENARIOS[@]}" -eq 1 ] && read -r -a SCENARIOS <<<"${SCENARIOS[0]}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROBE="$ROOT/tools/probe"
REPO="${PROBE_REPO:-$ROOT/tmp/probe-repos/$HOST}"

prompt() {
  case "$1" in
    tools) echo "Do these steps in order, one tool call each, without asking me anything: 1) run the shell command 'ls -la'. 2) read the file README.md with your file-reading tool. 3) create the file a.txt containing 'hola'. 4) edit a.txt replacing 'hola' with 'chau'. 5) in ONE single edit operation create b.txt and c.txt (any content). 6) run the shell command 'git add -A && git commit -q -m probe && git log -1 --format=%h'. 7) run the shell command 'sleep 1 && echo listo' in the background if your tools allow it. Then reply DONE." ;;
    question) echo "Before doing anything else, ask me which color I prefer using your tool for asking the user a question (do not just write the question as text). Then stop." ;;
    *) echo "escenario desconocido: $1" >&2; exit 2 ;;
  esac
}

rm -rf "$REPO" && mkdir -p "$REPO"
git -C "$REPO" init -q
printf '# Repo de prueba\n\nContenido de ejemplo.\n' >"$REPO/README.md"
git -C "$REPO" add README.md && git -C "$REPO" -c user.name=probe -c user.email=probe@example.invalid commit -q -m init

case "$HOST" in
  codex)
    export CODEX_HOME="$ROOT/tmp/probe-home/codex"
    rm -rf "$CODEX_HOME" && mkdir -p "$CODEX_HOME"
    cp "$HOME/.codex/auth.json" "$CODEX_HOME/auth.json"
    codex plugin marketplace add "$PROBE" >/dev/null
    codex plugin add probe@probe-market >/dev/null
    for s in "${SCENARIOS[@]}"; do
      (cd "$REPO" && codex exec --json --skip-git-repo-check --dangerously-bypass-hook-trust \
        -s workspace-write "$(prompt "$s")" >"$REPO/tmp-$s.jsonl" 2>&1) || true
    done ;;
  antigravity)
    mkdir -p "$REPO/.agents/plugins"
    cp -r "$PROBE/plugin" "$REPO/.agents/plugins/probe"
    for s in "${SCENARIOS[@]}"; do
      (cd "$REPO" && agy -p "$(prompt "$s")" --dangerously-skip-permissions --output-format json \
        >"$REPO/tmp-$s.json" 2>&1) || true
    done ;;
  opencode)
    # Sin saldo de modelo real: modelo falso con guion (tools/fake-llm) y OpenCode aislado de la config global
    # (la del usuario niega todo proveedor salvo anthropic, y las políticas de V2 solo pueden negar).
    OC_HOME="$ROOT/tmp/probe-home/opencode"
    rm -rf "$OC_HOME" && mkdir -p "$OC_HOME"/{config,data,state,cache}
    export XDG_CONFIG_HOME="$OC_HOME/config" XDG_DATA_HOME="$OC_HOME/data" XDG_STATE_HOME="$OC_HOME/state"
    export XDG_CACHE_HOME="$OC_HOME/cache" FAKE_LLM_KEY=x
    PLUGINS_JSON="${OPENCODE_PLUGINS_JSON:-[\"$PROBE/plugin\"]}"
    sed -e "s#@PLUGINS@#$PLUGINS_JSON#" "$ROOT/tools/fake-llm/opencode.template.json" >"$REPO/opencode.json"
    python3 "$ROOT/tools/fake-llm/server.py" --port 18080 --script "${FAKE_SCRIPT:-$ROOT/tools/fake-llm/probe-tools.json}" \
      --log "$REPO/fake-llm.jsonl" & FAKE_PID=$!
    trap 'kill $FAKE_PID 2>/dev/null' EXIT
    sleep 1
    (cd "$REPO" && opencode run --standalone --auto --format json "go" >"$REPO/tmp-tools.json" 2>&1) || true ;;
  *) echo "host desconocido: $HOST" >&2; exit 2 ;;
esac

echo "capturas: $(find "$REPO/tmp/probe" -type f 2>/dev/null | wc -l) en $REPO/tmp/probe"
