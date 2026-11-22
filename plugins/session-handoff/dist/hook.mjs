// cli/cli.ts
import { readFileSync } from "node:fs";

// hooks/handoff.ts
var VERSION = "0.5.4";
var FILES = ["PROGRESS.md", "DECISIONS.md", "NOTES.md"];
var PHASES = ["implementation", "verification", "integration", "external-wait", "closing"];
var LINE_MAX = 120;
var MAX_BLOCKS = 3;
var EXCERPT_MAX = 6000;
var LABELS = {
  status: "Status",
  phase: "Phase",
  done: "Done",
  current: "Current",
  remaining: "Remaining",
  eta: "ETA",
  next_step: "Next step"
};
var DEFAULT_BLOCK_REASONS = {
  "user-data": "cambiar o borrar datos existentes del usuario o de producción",
  cost: "gastar dinero o contratar un servicio pago",
  credentials: "falta un acceso que solo tiene el usuario",
  "user-stop": "el usuario pidió parar"
};
function parseConfig(text) {
  let raw = {};
  try {
    const parsed = text ? JSON.parse(text) : {};
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed))
      raw = parsed;
  } catch {
    raw = {};
  }
  const str = (v) => typeof v === "string" && v.trim() ? v.trim() : undefined;
  const reasons = raw.blockReasons;
  const isReasons = reasons && typeof reasons === "object" && !Array.isArray(reasons) && Object.keys(reasons).length > 0 && Object.values(reasons).every((v) => typeof v === "string");
  const context = Array.isArray(raw.context) ? raw.context.filter((l) => typeof l === "string") : [];
  const phases = {};
  if (raw.phases && typeof raw.phases === "object" && !Array.isArray(raw.phases))
    for (const [k, v] of Object.entries(raw.phases)) {
      const text = str(v);
      if (text && PHASES.includes(k))
        phases[k] = text;
    }
  return {
    blockReasons: isReasons ? reasons : DEFAULT_BLOCK_REASONS,
    context,
    specsDir: (str(raw.specsDir) ?? "docs/specs").replace(/\/+$/, ""),
    decisionsDir: str(raw.decisionsDir),
    pendingDir: str(raw.pendingDir),
    closing: str(raw.closing),
    phases
  };
}
function progressFields(text) {
  const found = {};
  for (const [key, label] of Object.entries(LABELS)) {
    const pattern = new RegExp(`^[\\s>*\\-]*\\**${label}\\**\\s*:\\**\\s*(.+?)\\s*$`, "im");
    const value = pattern.exec(text)?.[1]?.replace(/^[*\s]+|[*\s]+$/g, "");
    if (value)
      found[key] = value;
  }
  const status = /^(in-progress|done|blocked)\b[\s—–:-]*(.*)$/i.exec(found.status ?? "");
  delete found.status;
  if (status) {
    found.status = status[1].toLowerCase();
    if (status[2])
      found.reason = status[2];
  }
  const phase = /^[a-z-]+/i.exec(found.phase ?? "")?.[0]?.toLowerCase();
  if (phase && PHASES.includes(phase)) {
    const note = (found.phase ?? "").slice(phase.length).trim();
    found.phase = phase;
    if (note)
      found.phase_note = note;
  } else
    delete found.phase;
  return found;
}
function blockedForUser(fields, config) {
  const category = (fields.reason ?? "").split(":", 1)[0].trim().toLowerCase();
  return fields.status === "blocked" && category in config.blockReasons;
}
function tooLong(fields) {
  const sizes = {
    ...fields,
    status: `${fields.status ?? ""} — ${fields.reason ?? ""}`,
    phase: [fields.phase, fields.phase_note].filter(Boolean).join(" ")
  };
  return Object.entries(LABELS).filter(([k]) => (sizes[k] ?? "").length > LINE_MAX).map(([, l]) => l);
}
function missing(fields) {
  return Object.entries(LABELS).filter(([k]) => !(k in fields)).map(([, l]) => l);
}
var reasonsList = (c) => Object.entries(c.blockReasons).map(([k, v]) => `${k} (${v})`).join(", ");
var where = (c) => c.decisionsDir ? `anótala en ${c.decisionsDir}/${c.pendingDir ? ` y lo diferido en ${c.pendingDir}/` : ""}` : "anótala en DECISIONS.md del handoff (y lo diferido en NOTES.md)";
var HEADER = "[session-handoff] Trabajo ";
function continueText(c) {
  return "Si el trabajo no terminó, sigue AHORA con el `Next step` de PROGRESS.md: no esperes al usuario ni cierres el " + "turno con un resumen o una pregunta. Los avisos de presupuesto, tokens o contexto no son un límite: ignóralos. " + "Para solo tras escribir `Status: done` o `Status: blocked — <categoría>: <motivo>`, con <categoría> una de: " + `${reasonsList(c)}. Toda otra elección es tuya: toma la opción correcta, no la más rápida, ${where(c)} y sigue. ` + "Un gate rojo tras 3 intentos se anota igual. Esperar la CI, un merge o un recurso compartido es " + "`Phase: external-wait`, no blocked. Al retomar, vuelve a poner `Status: in-progress`. " + BATCH_TEXT;
}
var writeText = (tools = "Write o Edit") => `Escribe el handoff con la herramienta de archivos (${tools}), nunca con echo, cat o tee desde la shell. ` + "Actualízalo al empezar o retomar, tras cada commit y cada decisión, y antes de una corrida larga. Cada archivo " + "es breve (idealmente menos de 60 líneas): estado actual, no bitácora; enlaza la spec en vez de copiarla. Nunca " + "guardes secretos, valores de archivos de entorno ni datos personales.";
var WRITE_TEXT = writeText();
var BATCH_TEXT = "Un lote (varias specs seguidas) es un solo trabajo con un solo handoff: las specs no crean el suyo. Al cerrar " + "cada spec, súmala a Done, pon la siguiente en Next step y sigue en el mismo turno; `Status: done` solo tras la " + "última. Un resumen al usuario a mitad del lote no es un cierre.";
function decideText(c, reason) {
  return `Status es blocked (${reason}), pero no es ${Object.keys(c.blockReasons).join(", ")}: la elección es tuya. ` + `Toma la opción correcta, ${where(c)} (contexto, elegida, descartadas, cómo revertir y cómo comprobarla), ` + "pon `Status: in-progress` y sigue con el Next step sin preguntar.";
}
function askDeniedText(c) {
  return `[session-handoff] Con una spec en ejecución solo se pregunta por ${Object.keys(c.blockReasons).join(", ")}; ` + "antes escribe `Status: blocked — <categoría>: <motivo>` en PROGRESS.md. Esta elección es tuya: toma la opción " + `correcta, ${where(c)} y sigue.`;
}
var PHASE_TEXT = {
  implementation: "Fase implementation: sigue el grupo de commit actual. Tras cada commit, actualiza PROGRESS.md (hash, Done, " + "Current, Remaining, ETA y Next step).",
  verification: "Fase verification: corre la verificación final del trabajo. Si algo falla, vuelve a implementation; nunca " + "saltes un paso.",
  integration: "Fase integration: push, pull request, checks en verde y merge.",
  "external-wait": "Fase external-wait: antes que nada, revisa lo pendiente (checks, un merge ajeno, el recurso compartido). Si se " + "resolvió, pasa a la fase siguiente. No rehagas trabajo terminado.",
  closing: "Fase closing: borra los crons del trabajo y cierra su worktree. En un lote con specs en Remaining, vuelve a " + "implementation con la siguiente; si no queda ninguna, pon `Status: done`."
};
var SOURCE_TEXT = {
  startup: "Sesión nueva: revisa git status, git log y git worktree list antes de seguir; el disco manda.",
  resume: "Sesión reanudada: revisa git status, git log y git worktree list antes de seguir; el disco manda.",
  compact: "Compactada: el tramo reciente está literal o resumido. Relee las instrucciones del proyecto si hace falta y no " + "rehagas pasos ya confirmados.",
  clear: "Contexto limpio: relee las instrucciones del proyecto y la spec antes de seguir.",
  fork: "Sesión bifurcada: comparte este handoff con la original; coordina antes de escribirlo."
};
var excerpt = (text, name) => text.length <= EXCERPT_MAX ? text.trim() : `${text.slice(0, EXCERPT_MAX).trim()}
… (recortado: ${text.length - EXCERPT_MAX} caracteres más; lee ${name} completo)`;
function boundMessage(b, c, writeTools) {
  const fields = progressFields(b.files["PROGRESS.md"] ?? "");
  const lines = [
    `${HEADER}${b.work} · handoff en ${b.folder}/ · rama ${b.branch || "(detached)"}`,
    SOURCE_TEXT[b.source] ?? "Relee las instrucciones del proyecto: la conversación previa puede estar resumida."
  ];
  if (fields.status === "done") {
    lines.push(`${c.closing ?? "Status es done: solo queda el cierre. Confirma el merge y cierra el worktree si lo hay."} ` + `Después borra ${b.folder}/ y sus vínculos de .sessions/.`);
    return lines.join(`
`);
  }
  if (fields.status === "blocked") {
    lines.push(blockedForUser(fields, c) ? `Status es blocked: ${fields.reason}. Primero comprueba si el motivo sigue en pie; si ya no aplica, pon ` + "`Status: in-progress` y sigue sin preguntar. Solo mientras siga, muéstrale el motivo al usuario." : decideText(c, fields.reason ?? "sin motivo"));
  } else {
    lines.push(continueText(c));
    if (fields.phase)
      lines.push(c.phases[fields.phase] ?? PHASE_TEXT[fields.phase]);
    lines.push(writeText(writeTools));
  }
  lines.push(...c.context);
  const gaps = missing(fields);
  if (gaps.length)
    lines.push("Mantén estas líneas arriba de PROGRESS.md, una por línea (máximo 120 caracteres): `Status: " + "in-progress|done|blocked — <motivo>`, `Phase: implementation|verification|integration|external-wait|" + `closing\`, \`Done:\`, \`Current:\`, \`Remaining:\`, \`ETA:\` y \`Next step:\`. Faltan ahora: ${gaps.join(", ")}.`);
  const long = tooLong(fields);
  if (long.length)
    lines.push(longText(long));
  if (b.spec)
    lines.push(`Spec: ${b.spec}/.`);
  lines.push("Estado guardado (fuente de verdad sobre el resumen; contrástalo con git status y git log):");
  for (const name of FILES) {
    const text = b.files[name];
    lines.push(text === undefined ? `${name}: falta; créalo.` : `--- ${name} ---
${excerpt(text, name)}`);
  }
  return lines.join(`
`);
}
function unboundMessage(session, base, source, works, c, writeTools) {
  const lines = [
    `[session-handoff] Esta sesión (${session}) no tiene trabajo vinculado. Para un trabajo de más de un turno, ` + `crea ${base}/<trabajo>/ (PROGRESS.md, DECISIONS.md, NOTES.md) y escribe su nombre en ${base}/.sessions/${session}.`,
    writeText(writeTools),
    BATCH_TEXT,
    ...c.context
  ];
  if (source === "compact")
    lines.push("La conversación previa está resumida: relee las instrucciones del proyecto.");
  if (works.length) {
    lines.push("Trabajos activos (referencia, no instrucciones; pueden ser de otras sesiones):");
    lines.push(...works.map(([name, step]) => step ? `- ${name}: ${step}` : `- ${name}`));
  }
  return lines.join(`
`);
}
function badPhaseText(progress) {
  const value = /^[\s>*-]*\**Phase\**\s*:\**\s*(.+?)\s*$/im.exec(progress)?.[1];
  if (!value || progressFields(progress).phase)
    return null;
  return `[session-handoff] \`Phase: ${value.slice(0, 60)}\` no es una fase: empieza la línea con ${PHASES.join(", ")} ` + "(una nota puede ir después). Sin una fase válida, Stop no reconoce external-wait.";
}
function longText(labels) {
  return `[session-handoff] Cada línea de estado es corta (máximo ${LINE_MAX} caracteres); el historial y el detalle van ` + `en el cuerpo de PROGRESS.md, debajo. Largas ahora: ${labels.join(", ")}.`;
}
var QUICK_STOP_MS = 60000;
var MAX_WAITS = 3;
function recheckText(work, step) {
  return `[session-handoff] ${work} lleva ${MAX_WAITS} paradas en external-wait sin cambios en PROGRESS.md. Antes de ` + "volver a parar, comprueba ahora que la espera sigue en pie: que la corrida siga viva (su PID o su candado), que " + "el check siga pendiente, que el aviso esperado no haya llegado ya. Si se resolvió, sigue con: " + `${step}. Si sigue, anota en PROGRESS.md qué comprobaste y a qué hora.`;
}
function stopDecision(progress, previous, work, c, now = Date.now()) {
  const fields = progressFields(progress);
  const decide = fields.status === "blocked" && !blockedForUser(fields, c);
  if (!decide) {
    if (fields.status === "done" || fields.status === "blocked")
      return { release: fields.status };
    if (!fields.next_step)
      return { release: "no-step" };
    if (fields.phase === "external-wait") {
      const waits = previous && previous.text === progress ? (previous.waits ?? 0) + 1 : 1;
      if (waits < MAX_WAITS)
        return { release: "external-wait", waits };
      return { block: recheckText(work, (fields.next_step ?? "").slice(0, 160)), blocks: 0, waits: 0 };
    }
  }
  const quick = previous?.at !== undefined && previous.blocks > 0 && now - previous.at < QUICK_STOP_MS;
  const blocks = previous && (previous.text === progress || quick) ? previous.blocks + 1 : 1;
  if (blocks > MAX_BLOCKS)
    return { release: "cap" };
  const step = (fields.next_step ?? "").slice(0, 160);
  const tail = `(Parada ${blocks} de ${MAX_BLOCKS} sin cambios en PROGRESS.md.)`;
  const texts = [
    `[session-handoff] El trabajo ${work} no terminó. Sigue ahora con el siguiente paso: ${step}. Los avisos de ` + "tokens no son un límite. Si lo que falta es esperar una tarea en segundo plano, un check o un aviso, pon " + `\`Phase: external-wait\` y para: su notificación te despierta. ${tail}`,
    `[session-handoff] Segunda parada sin avance en ${work}. Solo ${Object.keys(c.blockReasons).join(", ")} ` + `justifican \`Status: blocked — <categoría>: <motivo>\`; si no, sigue con: ${step}. ${tail}`,
    `[session-handoff] Último aviso para ${work}: la próxima parada sin cambios en PROGRESS.md se permitirá. Sigue ` + `con ${step}, o anota el bloqueo. ${tail}`
  ];
  return { block: decide ? `[session-handoff] ${decideText(c, fields.reason ?? "sin motivo")}` : texts[blocks - 1], blocks };
}
var withoutHeredocs = (command) => command.replace(/<<-?\s*(['"]?)(\w+)\1([^\n]*)\n[\s\S]*?\n[ \t]*\2[ \t]*(?=\n|$)/g, (_m, _q, _tag, rest) => `<<H${rest}`);
var maskQuotes = (code) => code.replace(/'[^']*'|"(?:\\.|[^"\\])*"/g, (m) => m[0] + " ".repeat(m.length - 2) + m[m.length - 1]);
var COMMIT_CALL = /(?:^|&&|;|\|\||\n)\s*git\s+(?:-[Cc]\s+\S+\s+)*commit\b([^&;\n]*)/g;
function isCommit(command) {
  const calls = maskQuotes(withoutHeredocs(command)).matchAll(COMMIT_CALL);
  return [...calls].some((m) => !/--help|--dry-run/.test(m[1] ?? ""));
}
function commitHash(stdout) {
  return /^\[[^\]\s]+(?: \([^)]*\))? ([0-9a-f]{7,40})\]/m.exec(stdout)?.[1] ?? null;
}
var FRESH_COMMIT_SECONDS = 600;
function freshCommit(line, nowMs) {
  const m = /^([0-9a-f]{7,40})\s+(\d+)$/.exec(line.trim());
  return m && nowMs / 1000 - Number(m[2]) <= FRESH_COMMIT_SECONDS ? m[1] : null;
}
function commitDir(command, cwd) {
  const quoted = String.raw`(?:"([^"]+)"|'([^']+)'|([^\s&;|]+))`;
  const code = withoutHeredocs(command);
  const mask = maskQuotes(code);
  const commit = new RegExp(COMMIT_CALL.source).exec(mask);
  const before = commit ? code.slice(0, commit.index + commit[0].length) : code;
  const pick = (m) => native(m[1] ?? m[2] ?? m[3] ?? "");
  const gitC = new RegExp(String.raw`git\s+-C\s+${quoted}\s+commit\b`).exec(before);
  if (gitC)
    return join(cwd, pick(gitC));
  let dir = cwd;
  const cd = new RegExp(String.raw`(?:^|&&|;)\s*cd\s+${quoted}(?=\s*&&)`, "g");
  for (const m of mask.slice(0, before.length).matchAll(cd)) {
    const real = new RegExp(cd.source).exec(code.slice(m.index));
    if (real)
      dir = join(dir, pick(real));
  }
  return dir;
}
var native = (dir) => dir.replace(/^\/([a-z])\//i, (_, d) => `${d.toUpperCase()}:/`);
var join = (base, dir) => !dir ? base : /^([a-z]:)?[\/]/i.test(dir) ? dir : `${base.replace(/[\/]+$/, "")}/${dir}`;
function missingHashes(hashes, progress) {
  return [...new Set(hashes.filter(Boolean))].filter((h) => !progress.includes(h));
}
function pendingText(work, hashes) {
  if (!hashes.length)
    return null;
  return `[session-handoff] PROGRESS.md de ${work} no tiene ${hashes.length === 1 ? "el commit" : "los commits"} ` + `${hashes.join(", ")}: anótalos ahora, en esta misma respuesta, en Done, y pon Current, Remaining, ETA y Next ` + "step al día. Este aviso vuelve en cada commit, mensaje y fin de turno hasta que estén. Con un Next step viejo, " + "tras compactar se repite trabajo.";
}

// hooks/store.ts
var SAFE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
var SPEC_NUMBER = /(?:^|\/)(\d{2,3}(?:\.\d+)?)-/;
var clean = (p) => p.replace(/\\/g, "/").replace(/\/+$/, "");
async function placeOf(io, cwd) {
  const root = clean(await io.git(cwd, ["rev-parse", "--show-toplevel"]) || cwd);
  const common = clean(await io.git(cwd, ["rev-parse", "--path-format=absolute", "--git-common-dir"]));
  const store = common.endsWith("/.git") ? common.slice(0, -"/.git".length) : root;
  return { root, store, branch: await io.git(root, ["branch", "--show-current"]) };
}
var handoffDir = (store) => `${store}/tmp/handoff`;
async function configOf(io, root) {
  return parseConfig(await io.read(`${root}/.claude/session-handoff.json`));
}
var dirs = async (io, path) => (await io.list(path).catch(() => [])).filter((e) => e.kind === "dir").map((e) => e.name).sort();
async function currentWork(io, place, session) {
  const base = handoffDir(place.store);
  const works = await dirs(io, base);
  if (SAFE.test(session)) {
    const linked = (await io.read(`${base}/.sessions/${session}`))?.trim();
    if (linked && SAFE.test(linked) && works.includes(linked))
      return linked;
  }
  const number = SPEC_NUMBER.exec(place.branch)?.[1];
  return number && works.find((w) => w.startsWith(`${number}-`)) || null;
}
async function takenOverBy(io, place, session, work) {
  const dir = `${handoffDir(place.store)}/.sessions`;
  const links = await io.list(dir).catch(() => []);
  const mine = links.find((l) => l.name === session)?.mtimeMs;
  if (mine === undefined)
    return null;
  for (const link of links) {
    if (link.name === session || link.kind !== "file" || (link.mtimeMs ?? 0) <= mine)
      continue;
    if ((await io.read(`${dir}/${link.name}`))?.trim() === work)
      return link.name;
  }
  return null;
}
async function specOf(io, place, work, config) {
  const number = SPEC_NUMBER.exec(work)?.[1] ?? SPEC_NUMBER.exec(place.branch)?.[1];
  if (!number)
    return null;
  const specs = `${place.root}/${config.specsDir}`;
  for (const name of await dirs(io, specs)) {
    if (name.startsWith(`${number}-`))
      return `${config.specsDir}/${name}`;
    for (const inner of await dirs(io, `${specs}/${name}`))
      if (inner.startsWith(`${number}-`))
        return `${config.specsDir}/${name}/${inner}`;
  }
  return null;
}
var progressOf = async (io, place, work) => await io.read(`${handoffDir(place.store)}/${work}/PROGRESS.md`) ?? "";
async function boundOf(io, place, work, source, config) {
  const folder = `${handoffDir(place.store)}/${work}`;
  const files = {};
  for (const name of FILES) {
    const text = await io.read(`${folder}/${name}`);
    if (text !== null)
      files[name] = text;
  }
  return { work, folder, branch: place.branch, source, spec: await specOf(io, place, work, config), files };
}
async function activeWorks(io, place) {
  const out = [];
  for (const name of await dirs(io, handoffDir(place.store))) {
    if (name.startsWith("."))
      continue;
    out.push([name, (progressFields(await progressOf(io, place, name)).next_step ?? "").slice(0, 160)]);
  }
  return out;
}
async function logEvent(io, store, event) {
  try {
    const path = `${handoffDir(store)}/.log/events.jsonl`;
    const before = await io.read(path) ?? "";
    const line = `${JSON.stringify({ ts: new Date().toISOString().slice(0, 19) + "Z", v: VERSION, ...event })}
`;
    const kept = before.length > 512000 ? before.slice(before.indexOf(`
`, before.length - 256000) + 1) : before;
    await io.write(path, kept + line);
  } catch {}
}

// hooks/state.ts
var SAFE2 = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
var stateDir = (store) => `${handoffDir(store)}/.state`;
var emptyState = (session, host) => ({
  v: 1,
  session,
  host,
  headAtStart: null,
  lastStop: null,
  lastStopTurn: null,
  lastStopOutcome: null,
  lastStopAt: null,
  pendingCommits: [],
  compacted: false,
  updatedAt: 0
});
async function loadState(io, store, session, host) {
  if (!SAFE2.test(session))
    return emptyState(session, host);
  const text = await io.read(`${stateDir(store)}/${session}.json`);
  if (!text)
    return emptyState(session, host);
  try {
    const data = JSON.parse(text);
    return data.v === 1 ? { ...emptyState(session, host), ...data } : emptyState(session, host);
  } catch {
    return emptyState(session, host);
  }
}
async function saveState(io, store, state, now = Date.now()) {
  if (!SAFE2.test(state.session))
    return;
  try {
    const current = await loadState(io, store, state.session, state.host);
    await io.write(`${stateDir(store)}/${state.session}.json`, JSON.stringify({ ...current, ...state, updatedAt: now }));
  } catch {}
}

// hooks/terms.ts
var TERMS = {
  claude: { writeTools: "Write o Edit", askTool: "AskUserQuestion" },
  codex: { writeTools: "apply_patch", askTool: "request_user_input" },
  antigravity: { writeTools: "write_file o edit_file", askTool: "ask_question" },
  opencode: { writeTools: "write, edit o patch", askTool: "question" }
};

// hooks/actions.ts
var PROGRESS_PATH = /(?:^|\/)tmp\/handoff\/[^/]+\/PROGRESS\.md$/;
var CODEX_BUDGET = 8000;
var REMINDER_MAX = 600;
async function here(c) {
  const place = await placeOf(c.io, c.cwd);
  return { place, state: await loadState(c.io, place.store, c.session, c.host) };
}
var writeTools = (host) => TERMS[host].writeTools;
async function sessionStart(c) {
  const { place, state } = await here(c);
  if (c.source === "startup" || state.headAtStart === null) {
    state.headAtStart = await c.io.git(place.root, ["rev-parse", "HEAD"]) || null;
  }
  if (c.source === "startup" || c.source === "clear")
    state.lastStop = null;
  await saveState(c.io, place.store, state, c.now);
  const text = await messageFor(c, place, c.source);
  if (!text)
    return null;
  const compact = c.host === "codex" && text.length > CODEX_BUDGET;
  const out = compact ? await compactMessage(c, place) : text;
  await logEvent(c.io, place.store, {
    event: compact ? "inject.compact" : "inject",
    host: c.host,
    session: c.session,
    source: c.source,
    chars: out.length
  });
  return out;
}
async function messageFor(c, place, source) {
  const config = await configOf(c.io, place.root);
  const work = await currentWork(c.io, place, c.session);
  if (work)
    return boundMessage(await boundOf(c.io, place, work, source, config), config, writeTools(c.host));
  return c.session ? unboundMessage(c.session, handoffDir(place.store), source, await activeWorks(c.io, place), config, writeTools(c.host)) : "";
}
async function compactMessage(c, place) {
  const work = await currentWork(c.io, place, c.session) ?? "";
  const folder = `${handoffDir(place.store)}/${work}`;
  const progress = await progressOf(c.io, place, work);
  const status = progress.split(`
`).filter((l) => /^(Status|Phase|Done|Current|Remaining|ETA|Next step):/.test(l));
  return [
    `[session-handoff] Trabajo ${work} · handoff en ${folder}/ (resumido: el completo no cabe en el contexto de Codex).`,
    ...status,
    `Lee ahora ${folder}/PROGRESS.md, DECISIONS.md y NOTES.md con tu herramienta de lectura antes de seguir; el disco manda.`
  ].join(`
`);
}
async function missingCommits(c, h, work, extra) {
  const missing = missingHashes([...h.state.pendingCommits, ...extra], await progressOf(c.io, h.place, work));
  h.state.pendingCommits = missing;
  await saveState(c.io, h.place.store, h.state, c.now);
  return missing;
}
async function prompt(c) {
  const h = await here(c);
  const work = await currentWork(c.io, h.place, c.session);
  if (!work)
    return null;
  return pendingText(work, await missingCommits(c, h, work, []));
}
async function postTool(c) {
  const h = await here(c);
  const work = await currentWork(c.io, h.place, c.session);
  if (c.event.tool === "shell") {
    if (!work || !isCommit(c.event.command))
      return null;
    const sha = commitHash(c.event.output) ?? freshCommit(await c.io.git(commitDir(c.event.command, c.cwd), ["log", "-1", "--format=%h %ct"]), c.now ?? Date.now());
    const text = pendingText(work, await missingCommits(c, h, work, sha ? [sha] : []));
    if (text)
      await logEvent(c.io, h.place.store, { event: "commit.remind", host: c.host, session: c.session, work });
    return text;
  }
  const progress = c.event.paths.map((p) => p.replace(/\\/g, "/")).find((p) => PROGRESS_PATH.test(p));
  if (!progress)
    return null;
  return progressNotes(await c.io.read(absolute(progress, c.cwd)) ?? "");
}
var absolute = (p, cwd) => /^([A-Za-z]:)?\//.test(p) ? p : `${cwd.replace(/\\/g, "/")}/${p}`;
function progressNotes(text) {
  const long = tooLong(progressFields(text));
  return [long.length ? longText(long) : null, badPhaseText(text)].filter(Boolean).join(`
`) || null;
}
async function askQuestion(c) {
  const { place } = await here(c);
  const work = await currentWork(c.io, place, c.session);
  if (!work)
    return null;
  const config = await configOf(c.io, place.root);
  if (!await specOf(c.io, place, work, config))
    return null;
  if (blockedForUser(progressFields(await progressOf(c.io, place, work)), config))
    return null;
  await logEvent(c.io, place.store, { event: "ask.deny", host: c.host, session: c.session, work });
  return askDeniedText(config);
}
var DUPLICATE_STOP_MS = 2000;
async function stop(c) {
  const h = await here(c);
  const now = c.now ?? Date.now();
  const duplicate = h.state.lastStopAt !== null && now - h.state.lastStopAt < DUPLICATE_STOP_MS;
  if (c.turn && h.state.lastStopTurn === c.turn && duplicate)
    return h.state.lastStopOutcome;
  const answer = await stopAnswer(c, h);
  h.state.lastStopTurn = c.turn || null;
  h.state.lastStopOutcome = answer;
  h.state.lastStopAt = now;
  await saveState(c.io, h.place.store, h.state, c.now);
  return answer;
}
async function stopAnswer(c, h) {
  const work = await currentWork(c.io, h.place, c.session);
  if (!work)
    return null;
  const progress = await progressOf(c.io, h.place, work);
  let notes = null;
  let landed = [];
  if (c.host === "antigravity") {
    notes = progressNotes(progress);
    if (h.state.headAtStart) {
      const log = await c.io.git(h.place.root, ["log", "--first-parent", "--no-merges", "--format=%h", `${h.state.headAtStart}..HEAD`]);
      landed = log.split(`
`).map((s) => s.trim()).filter(Boolean).reverse();
    }
  }
  const reminder = c.active ? null : pendingText(work, await missingCommits(c, h, work, landed));
  if (reminder || notes) {
    await logEvent(c.io, h.place.store, { event: "stop.commits", host: c.host, session: c.session, work });
    return [notes, reminder].filter(Boolean).join(`
`);
  }
  const owner = await takenOverBy(c.io, h.place, c.session, work);
  if (owner) {
    await logEvent(c.io, h.place.store, { event: "stop.release", host: c.host, session: c.session, reason: "handed-off", owner });
    return null;
  }
  const config = await configOf(c.io, h.place.root);
  const now = c.now ?? Date.now();
  const decision = stopDecision(progress, h.state.lastStop, work, config, now);
  if ("release" in decision) {
    h.state.lastStop = decision.waits ? { text: progress, blocks: 0, waits: decision.waits } : null;
    await logEvent(c.io, h.place.store, { event: "stop.release", host: c.host, session: c.session, reason: decision.release });
    return null;
  }
  h.state.lastStop = { text: progress, blocks: decision.blocks, waits: decision.waits, at: now };
  const event = decision.waits === 0 ? "stop.recheck" : "stop.block";
  await logEvent(c.io, h.place.store, { event, host: c.host, session: c.session, blocks: decision.blocks, work });
  return decision.block;
}
async function reminder(c) {
  if (c.invocation <= 0)
    return null;
  const h = await here(c);
  const work = await currentWork(c.io, h.place, c.session);
  if (!work)
    return null;
  const f = progressFields(await progressOf(c.io, h.place, work));
  const pending = pendingText(work, missingHashes(h.state.pendingCommits, await progressOf(c.io, h.place, work)));
  const text = [`[session-handoff] Trabajo ${work}: Status ${f.status ?? "?"} · Phase ${f.phase ?? "?"} · Next step: ` + `${f.next_step ?? "?"} (${handoffDir(h.place.store)}/${work}/PROGRESS.md).`, pending].filter(Boolean).join(" ");
  return text.slice(0, REMINDER_MAX);
}

// hooks/hosts.ts
var str = (v) => typeof v === "string" ? v : "";
function patchPaths(text) {
  return [...text.matchAll(/^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$/gm)].map((m) => m[1].trim());
}
async function handle(host, event, raw, io) {
  const base = host === "codex" ? { io, host, session: str(raw.session_id), cwd: str(raw.cwd) } : { io, host, session: str(raw.conversationId), cwd: str(raw.cwd) || str(raw.workspacePaths?.[0]) };
  const subagent = host === "codex" && Boolean(raw.agent_id);
  switch (event) {
    case "session-start": {
      const source = host === "codex" ? str(raw.source) || "startup" : "startup";
      return emit(host, event, await sessionStart({ ...base, source }));
    }
    case "prompt":
      return emit(host, event, subagent ? null : await prompt(base));
    case "post-tool": {
      const tool = str(raw.tool_name);
      const input = raw.tool_input ?? {};
      const post = tool === "Bash" ? { tool: "shell", command: str(input.command), output: str(raw.tool_response) } : tool === "apply_patch" ? { tool: "write", paths: patchPaths(str(input.command)) } : null;
      return emit(host, event, post ? await postTool({ ...base, event: post }) : null);
    }
    case "stop": {
      if (subagent)
        return emit(host, event, null);
      const active = host === "codex" ? raw.stop_hook_active === true : raw.continuationActive === true;
      const turn = host === "codex" ? str(raw.turn_id) : `${str(raw.executionNum)}`;
      return emit(host, event, await stop({ ...base, active, turn: host === "codex" ? turn : "" }));
    }
    case "ask-question":
      return emit(host, event, await askQuestion(base));
    case "pre-invocation":
      return emit(host, event, await reminder({ ...base, invocation: Number(raw.invocationNum ?? 0) }));
  }
}
var HOOK_EVENT = { "session-start": "SessionStart", prompt: "UserPromptSubmit", "post-tool": "PostToolUse" };
function emit(host, event, text) {
  if (host === "codex") {
    if (event === "stop")
      return JSON.stringify(text ? { decision: "block", reason: text } : {});
    if (event === "ask-question") {
      return text ? JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: text } }) : "";
    }
    return text ? JSON.stringify({ hookSpecificOutput: { hookEventName: HOOK_EVENT[event], additionalContext: text } }) : "";
  }
  if (event === "stop")
    return JSON.stringify(text ? { decision: "continue", reason: text } : {});
  if (event === "ask-question")
    return JSON.stringify(text ? { decision: "deny", reason: text } : { decision: "allow" });
  if (event === "session-start")
    return JSON.stringify(text ? { injectSteps: [{ systemMessage: text }] } : {});
  if (event === "pre-invocation")
    return JSON.stringify(text ? { injectSteps: [{ ephemeralMessage: text }] } : {});
  return "{}";
}
function neutral(host, event) {
  return emit(host, event, null);
}

// cli/io-node.ts
import { execFile } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
var GIT_TIMEOUT_MS = 1e4;
var nodeIo = {
  read: (file) => fs.readFile(file, "utf8").catch(() => null),
  write: async (file, text) => {
    await fs.mkdir(path.dirname(file), { recursive: true });
    const tmp = `${file}.${process.pid}.${Date.now()}.tmp`;
    await fs.writeFile(tmp, text, "utf8");
    await fs.rename(tmp, file);
  },
  list: async (dir) => {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    return Promise.all(entries.map(async (e) => ({
      name: e.name,
      kind: e.isDirectory() ? "dir" : "file",
      mtimeMs: (await fs.stat(path.join(dir, e.name)).catch(() => null))?.mtimeMs
    })));
  },
  git: (cwd, args) => new Promise((resolve) => {
    execFile("git", args, { cwd, timeout: GIT_TIMEOUT_MS, windowsHide: true }, (error, stdout) => resolve(error ? "" : String(stdout).trim()));
  })
};

// cli/cli.ts
var HOSTS = ["codex", "antigravity"];
var EVENTS = ["session-start", "prompt", "post-tool", "stop", "ask-question", "pre-invocation"];
var MIN_NODE = 20;
async function doctor() {
  const major = Number(process.versions.node.split(".")[0]);
  console.log(`${major >= MIN_NODE ? "✓" : "✗"} Node ${process.versions.node} (mínimo ${MIN_NODE})`);
  console.log(`✓ session-handoff ${VERSION}`);
  const place = await placeOf(nodeIo, process.cwd());
  const session = process.argv[3] ?? "";
  const work = session ? await currentWork(nodeIo, place, session) : null;
  console.log(`  handoff: ${handoffDir(place.store)}${session ? ` · sesión ${session}: ${work ?? "sin trabajo vinculado"}` : ""}`);
  const log = await nodeIo.read(`${handoffDir(place.store)}/.log/events.jsonl`) ?? "";
  const last = new Map;
  for (const line of log.trim().split(`
`).filter(Boolean)) {
    try {
      const e = JSON.parse(line);
      if (e.event)
        last.set(e.event, `${e.ts ?? ""} ${e.host ?? "claude"}`);
    } catch {}
  }
  for (const [event, when] of last)
    console.log(`  último ${event}: ${when}`);
}
async function main() {
  const [host, event] = process.argv.slice(2);
  if (host === "doctor") {
    await doctor();
    return 0;
  }
  if (!HOSTS.includes(host) || !EVENTS.includes(event)) {
    process.stderr.write(`uso: hook.mjs <${HOSTS.join("|")}> <${EVENTS.join("|")}>
`);
    return 0;
  }
  let out;
  try {
    if (Number(process.versions.node.split(".")[0]) < MIN_NODE)
      throw new Error(`Node ${process.versions.node}`);
    const text = readFileSync(0, "utf8");
    out = await handle(host, event, text.trim() ? JSON.parse(text) : {}, nodeIo);
  } catch {
    out = neutral(host, event);
  }
  if (out)
    process.stdout.write(out);
  return 0;
}
main().then((code) => process.exit(code), () => process.exit(0));
