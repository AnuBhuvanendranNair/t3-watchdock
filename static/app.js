const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ACTIVE = ["created","waiting_for_resource","preparing","pending","running","manual","scheduled"];
let S = null, pollT = null;

async function api(path, body) {
  const r = await fetch(path, body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {});
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || r.status);
  return d;
}
// Flash message top right: success 6 s, error 12 s; click closes it
const closeAfter = ev => ev.submitter?.dataset.close ? (location.hash = "#/", true) : false;  // "Save & close" -> Projects
function toast(msg, err) {
  const t = $("#toast");
  t.innerHTML = `<span class="ico">${err ? "⚠" : "✓"}</span><span class="tmsg">${esc(msg)}</span><span class="x">✕</span>`;
  t.className = "show" + (err ? " err" : ""); t.onclick = () => t.className = t.className.replace("show", "").trim();
  clearTimeout(toast.t); toast.t = setTimeout(() => t.className = "", err ? 12000 : 6000);
}
const varsStr = o => Object.entries(o || {}).map(([k, v]) => `${k}=${v}`).join(", ");
const parseVars = s => Object.fromEntries((s || "").split(",").map(x => x.trim()).filter(x => x.includes("="))
  .map(x => { const i = x.indexOf("="); return [x.slice(0, i).trim(), x.slice(i + 1).trim()]; }).filter(([k]) => k));
const proj = id => S.projects.find(p => p.id === id);
const pUrl = p => `#/p/${encodeURIComponent(p.id)}`;
const glUrl = p => `${p.gitlab_url}/${p.path}/-/pipelines`;
const hasCI = p => p.ci !== false;                 // projects without GitLab CI/CD: monitoring only
// "11.5.2-MariaDB-ubu2404" -> "MariaDB 11.5.2", "8.0.36" -> "MySQL 8.0.36" (full value stays in the tooltip)
const dbShort = v => { const m = String(v || "").match(/(\d+\.\d+(?:\.\d+)?)/); if (!m) return v || "";
  return (/mariadb/i.test(v) ? "MariaDB " : "MySQL ") + m[1]; };
const fmt = t => t ? t.replace("T", " ") : "–";

// Theme switch in the header: Auto (system) → Light → Dark; saved per browser
const THEMES = [{id:"auto", label:"◐ Auto", hint:"follows the system setting"},
  {id:"light", label:"☀ Light", hint:"always light"}, {id:"dark", label:"☾ Dark", hint:"always dark"}];
function setTheme(id, save) {
  const root = document.documentElement, t = THEMES.find(x => x.id === id) || THEMES[0];
  if (t.id === "auto") delete root.dataset.theme; else root.dataset.theme = t.id;
  if (save) try { t.id === "auto" ? localStorage.removeItem("theme") : localStorage.setItem("theme", t.id); } catch (e) {}
  const b = $("#themeBtn"), next = THEMES[(THEMES.indexOf(t) + 1) % THEMES.length];
  b.textContent = t.label; b.title = `Theme: ${t.id} (${t.hint}). Click for ${next.id}.`;
  b.setAttribute("aria-label", b.title);
}
setTheme(document.documentElement.dataset.theme || "auto");
$("#themeBtn").onclick = () => {
  const cur = document.documentElement.dataset.theme || "auto";
  setTheme(THEMES[(THEMES.findIndex(x => x.id === cur) + 1) % THEMES.length].id, true);
};

// Style selector next to the theme switch; saved per browser
const STYLES = ["default", "focus", "terminal", "turbo"];
const focusAvatars = new Map();
function setStyle(id, save) {
  const root = document.documentElement, st = STYLES.includes(id) ? id : "default";
  if (st === "default") delete root.dataset.style; else root.dataset.style = st;
  if (save) try { st === "default" ? localStorage.removeItem("style") : localStorage.setItem("style", st); } catch (e) {}
  $("#styleSel").value = root.dataset.style || "default";
  updateOverviewOrder();
  if (st === "focus") loadFocusAvatars();
}
setStyle(document.documentElement.dataset.style || "default");
$("#styleSel").onchange = ev => setStyle(ev.target.value, true);

// GitHub-style confirmation for destructive actions: the button is enabled only once the exact name is typed.
// Resolves true (confirmed) or false (cancelled / Escape).
function confirmByName(title, bodyHtml, name, action) {
  return new Promise(resolve => {
    const d = document.createElement("dialog");
    d.className = "confirm-dlg";
    d.innerHTML = `<form method="dialog"><h2>${esc(title)}</h2>${bodyHtml}
      <label>To confirm, type <b>${esc(name)}</b> below:</label>
      <input autocomplete="off" spellcheck="false" aria-label="Project name">
      <div class="actions"><button type="button" class="btn sec">Cancel</button>
        <button class="btn danger" value="ok" disabled>${esc(action)}</button></div></form>`;
    const inp = d.querySelector("input"), ok = d.querySelector('[value="ok"]');
    inp.oninput = () => ok.disabled = inp.value.trim() !== name;
    d.querySelector(".btn.sec").onclick = () => d.close();
    d.onclose = () => { resolve(d.returnValue === "ok" && inp.value.trim() === name); d.remove(); };
    document.body.append(d); d.showModal(); inp.focus();
  });
}

async function refresh() {
  S = await api("/api/state");
  const pill = $("#tokenPill");
  pill.textContent = S.token_source ? "Token ✓" : "No token";
  pill.className = "pill" + (S.token_source ? "" : " bad");
}

/* ---------------- router ---------------- */
async function render() {
  clearTimeout(pollT);
  if (!S) await refresh();
  const [a, b, c, d] = (location.hash.slice(1) || "/").split("/").filter(Boolean);
  const navKey = !a || a === "p" || a === "new" ? "projects" : a;
  document.querySelectorAll("[data-nav]").forEach(n => n.classList.toggle("on", n.dataset.nav === navKey));
  if (!a) return viewProjects();
  if (a === "new") return viewForm();
  if (a === "activity") return viewActivity();
  if (a === "settings") return viewSettings();
  if (a === "scheduler") return viewScheduler();
  if (a === "p" && b) {
    const p = proj(decodeURIComponent(b));
    if (!p) return $("#view").innerHTML = `<p class="empty">Project not found. <a href="#/">Back</a></p>`;
    return c === "edit" ? viewForm(p) : viewProject(p, c === "pl" ? Number(d) : null);
  }
  $("#view").innerHTML = `<p class="empty">Page not found. <a href="#/">Back</a></p>`;
}

/* ---------------- views ---------------- */
function loadFocusAvatars() {
  document.querySelectorAll(".focus-avatar").forEach(badge => {
    const {project, gitlab} = badge.dataset;
    if (badge.querySelector("img")) return;
    if (!focusAvatars.has(project)) {
      focusAvatars.set(project, api(`/api/project-avatar?project=${encodeURIComponent(project)}`)
        .then(({url}) => {
          if (!url) return null;
          const base = new URL(gitlab), avatar = new URL(url, base);
          return avatar.protocol === "https:" && avatar.origin === base.origin && !avatar.username && !avatar.password
            ? avatar.href : null;
        }).catch(() => null));
    }
    focusAvatars.get(project).then(url => {
      if (!url || !badge.isConnected || badge.querySelector("img")) return;
      const image = new Image();
      image.alt = "";
      image.referrerPolicy = "no-referrer";
      image.onload = () => { if (!badge.querySelector("img")) badge.append(image); };
      image.src = url;
    });
  });
}

// Status of each project's last pipeline on the project cards; refreshed every 8 s while one is busy
// (manual / scheduled = waiting for a person or a time: shown, but refreshed only with the normal 30 s poll)
let RUNST = {};
const BUSY = ACTIVE.filter(s => s !== "manual" && s !== "scheduled");
const RUN_LABEL = {created:"Created", waiting_for_resource:"Waiting for runner", preparing:"Preparing", pending:"Pending",
  running:"Running", manual:"Waiting for manual job", scheduled:"Scheduled", success:"Passed", failed:"Failed",
  canceled:"Canceled", skipped:"Skipped"};
const since = t => { const m = Math.max(0, Math.round((Date.now() - Date.parse(t)) / 60000));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`; };
function runStatusHtml(pid) {
  const r = RUNST[pid];
  if (!r) return "";
  if (!r.status) return `<span class="runst" title="${esc(r.error || "")}">status unknown</span>`;
  const active = BUSY.includes(r.status);
  const job = r.job ? ` · ${r.job_status === "manual" ? "▶ " : ""}${esc(r.job)}` : "";
  return `<span class="runst st s-${esc(r.status)}${active ? " active" : ""}">${active ? `<span class="dot" aria-hidden="true"></span>` : ""}${esc(RUN_LABEL[r.status] || r.status)}${job}${active && r.started ? ` · ${esc(since(r.started))}` : ""}</span>`;
}
function paintRunStatus() {
  document.querySelectorAll("[data-runst]").forEach(el => {
    const r = RUNST[el.dataset.runst];
    el.innerHTML = runStatusHtml(el.dataset.runst);
    const card = el.closest(".pcard");
    if (card) card.classList.toggle("run-active", !!r && BUSY.includes(r.status));
  });
}
async function loadRunStatus() {
  clearTimeout(loadRunStatus.t);
  try { RUNST = await api("/api/runs/status"); } catch { return; }
  if ((location.hash.slice(1) || "/") !== "/") return;
  paintRunStatus();
  if (Object.values(RUNST).some(r => BUSY.includes(r.status))) loadRunStatus.t = setTimeout(loadRunStatus, 8000);
}

function viewProjects(fresh) {   // fresh = T3SUM was just fetched, no reload needed
  const projectsWithRuns = new Set(S.projects_with_runs || []);
  const cards = S.projects.map(p => {
    const last = S.runs.find(r => r.project === p.id);
    const a = p.auto_typo3 || {};
    const monitoring = T3M_ENVS.filter(e => p[e.cfg]?.url).map(e => {
      const ready = t3mOn(p, e);
      return `<span class="focus-monitor ${ready ? "is-configured" : "is-pending"}">
        ${esc(e.label)}${ready ? "" : " · Key missing"}
      </span>`;
    }).join("");
    return `<a class="pcard" href="${pUrl(p)}">
      <div class="name">${esc(p.name)}</div>
      <div class="sub">${esc(p.path || "–")}</div>
      <div class="chips">
        ${!hasCI(p) ? `<span class="chip" title="No GitLab CI/CD: TYPO3 monitoring only">no CI/CD</span>` : ""}
        ${p.ref ? `<span class="chip ref">${esc(p.ref)}</span>` : ""}
        ${p.production?.ref ? `<span class="chip ref" title="Production branch">→ ${esc(p.production.ref)}</span>` : ""}
        ${(p.auto_play || []).length ? `<span class="chip">auto-play: ${esc(p.auto_play.join(", "))}</span>` : ""}
        ${a.enabled ? `<span class="chip">TYPO3 ${esc(a.major)} auto-update</span>` : ""}
      </div>
      <div class="srvline" data-srv="${esc(p.id)}"></div>
      <div class="last">${!hasCI(p) ? "Monitoring only" : last ? `<span data-runst="${esc(p.id)}">${runStatusHtml(p.id)}</span> Last run: #${esc(last.pipeline)} · ${esc(fmt(last.t))} · ${esc(last.trigger)}` : "No runs yet"}</div>
    </a>
    <article class="pcard focus-project">
      <a class="focus-project-link name" href="${pUrl(p)}">
        ${projectsWithRuns.has(p.id) ? `<span class="focus-avatar" data-project="${esc(p.id)}" data-gitlab="${esc(p.gitlab_url)}" aria-hidden="true">${esc(p.name.trim().split(/\s+/u, 2).map(word => Array.from(word)[0] || "").join("").toLocaleUpperCase())}</span>` : ""}
        <span class="focus-project-name">${esc(p.name)}</span><span class="focus-project-arrow" aria-hidden="true">›</span>
      </a>
      <div class="focus-monitoring" role="group" aria-label="TYPO3 monitoring">
        ${monitoring || `<span class="focus-monitor">Monitoring not configured</span>`}
      </div>
      <div class="focus-project-run" role="group" aria-label="GitLab CI/CD">
        ${!hasCI(p) ? `<span class="focus-monitor focus-ci is-disabled">CI/CD · Disabled</span>` : last
          ? `<a class="focus-monitor focus-ci is-configured" href="${pUrl(p)}/pl/${Number(last.pipeline)}" aria-label="Open latest CI/CD run #${esc(last.pipeline)}">CI/CD · #${esc(last.pipeline)}</a> <span data-runst="${esc(p.id)}">${runStatusHtml(p.id)}</span>`
          : `<span class="focus-monitor focus-ci is-pending">CI/CD · No runs yet</span>`}
      </div>
    </article>`;
  }).join("");
  $("#view").innerHTML = `
    <div class="head"><div><h1>Projects</h1><div class="sub" data-secondary-copy>${S.projects.length} project(s) · <span class="srvlegend"><span class="upd">↑</span> TYPO3 update available · <span class="diff">≠</span> staging differs from production</span></div></div>
      <div class="actions">
        ${S.projects.some(hasCI) ? `<button class="btn" data-act="runall">▶ Run all</button>` : ""}
        <a class="btn sec" href="#/new">+ New project</a></div></div>
    ${cards ? `<div class="grid">${cards}</div>` : `<div class="card empty">No projects yet. <a href="#/new">Create one</a>.</div>`}
    ${S.projects.length ? `<div class="card full" id="t3sum" style="margin-top:18px"><h2>TYPO3 status – Production &amp; Staging</h2><p class="empty">Loading…</p></div>` : ""}`;
  if (document.documentElement.dataset.style === "focus") loadFocusAvatars();
  paintRunStatus();
  if (S.runs.length) loadRunStatus();          // server caches it (8 s active, 5 min finished)
  if (!S.projects.length) return;
  if (!T3SUM) return loadT3mSummary();               // first visit: fetch once
  loadT3mSummary(T3SUM);                             // cached data at once (synchronous, no flash) ...
  if (!fresh) loadT3mSummary();                      // ... then update in the background
}

// Instance with pending extension updates: tinted background (accent = updates, orange = at least one major update)
const extUpdCls = x => x?.ext_updates ? (x.ext_major ? "extupd major" : "extupd") : "";
const extUpdTitle = x => x?.ext_updates ? `${x.ext_updates} extension update${x.ext_updates === 1 ? "" : "s"} pending${x.ext_major ? ` (${x.ext_major} major)` : ""}` : "";

// Overview table on the home page: TYPO3 version + errors/warnings per instance (data from the last t3monitor check)
let T3SUM = null;                  // last /api/t3monitor/summary response (reused on re-render: no "Loading…" flash)
const overviewOptions = {sort:"original"};
async function loadT3mSummary(pre) {
  let d;
  try { d = pre ?? await api("/api/t3monitor/summary"); T3SUM = d; }
  catch (err) { if ($("#t3sum")) $("#t3sum").innerHTML = `<h2>TYPO3 status</h2><p class="empty">Error: ${esc(err.message)}</p>`; return; }
  const box = $("#t3sum"); if (!box) return;
  // server grid in each project card: TYPO3 / PHP / DB per instance; ↑ = TYPO3 update, ≠ = staging differs from production
  document.querySelectorAll(".srvline[data-srv]").forEach(el => {
    const s = d[el.dataset.srv] || {}, a = s.production?.has_data ? s.production : null;
    const envs = [["PROD", "prod", s.production], ["STG", "stg", s.staging]].filter(([, , x]) => x?.has_data);
    if (!envs.length) return;
    const cell = (x, k, txt, full, suffix = "") => {
      const diff = a && x !== a && a[k] && x[k] && a[k] !== x[k];
      return `<span class="${diff ? "diff" : ""}" title="${esc(full || x[k] || "")}${diff ? ` (production: ${esc(a[k])})` : ""}">${diff ? "≠ " : ""}${esc(txt || "–")}${suffix}</span>`;
    };
    const t3 = x => { const latest = S.typo3_latest[String(x.typo3 || "").split(".")[0]];
      return cell(x, "typo3", x.typo3, "", latest && x.typo3 && verCmp(latest, x.typo3) > 0 ? ` <span class="upd" title="Update available: ${esc(latest)}">↑</span>` : ""); };
    el.innerHTML = `<span></span><span class="h">TYPO3</span><span class="h">PHP</span><span class="h">DB</span>` + envs.map(([lbl, cls, x]) =>
      `<span class="env ${cls}">${lbl}</span>${t3(x)}${cell(x, "php", x.php)}${cell(x, "db", dbShort(x.db), x.db)}`).join("");
  });
  // labelled server values; ref = production instance: staging values that differ get ≠ (orange)
  const srvTags = (x, ref) => [["PHP", "php", x.php, x.php], ["DB", "db", dbShort(x.db), x.db], ["Web", "webserver", x.webserver, x.webserver]]
    .filter(([, , txt]) => txt).map(([lbl, k, txt, full]) => {
      const diff = ref && ref[k] && x[k] && ref[k] !== x[k];
      return `<span class="srvtag${diff ? " diff" : ""}" title="${esc(full)}${diff ? ` (production: ${esc(ref[k])})` : ""}"><span class="h">${lbl}</span> ${diff ? "≠ " : ""}${esc(txt)}</span>`;
    }).join("");
  const ver = (x, ref) => {
    if (!x) return `<span class="sub">–</span>`;
    if (!x.has_data) return x.last_error ? `<span class="sev-2" title="${esc(x.last_error)}">check failed</span>` : `<span class="sub">no data yet</span>`;
    const latest = S.typo3_latest[String(x.typo3 || "").split(".")[0]], upd = latest && x.typo3 && verCmp(latest, x.typo3) > 0;
    const srv = srvTags(x, ref?.has_data ? ref : null);
    return `<b>${esc(x.typo3 || "?")}</b>${upd ? ` <span class="sev-1" title="Latest: ${esc(latest)}">↑ ${esc(latest)}</span>` : ""}
      ${srv ? `<div class="srvtags">${srv}</div>` : ""}
      ${x.last_error ? ` <span class="sev-2" title="${esc(x.last_error)}">⚠ last check failed</span>` : ""}`;
  };
  const ew = x => !x?.has_data ? `<span class="sub">–</span>`
    : `<span class="badge ${x.errors ? "sev-2" : "sev0"}">${x.errors} E</span> <span class="badge ${x.warnings ? "sev-1" : "sev0"}">${x.warnings} W</span>`
      + (x.advisories ? ` <span class="badge sev-2" title="${x.advisories} security advisor${x.advisories === 1 ? "y" : "ies"} affect this instance">${x.advisories} SA</span>` : "")
      + (x.php_check?.severity ? ` <span class="badge sev-${x.php_check.severity}" title="${esc(x.php_check.text)}">PHP</span>` : "");
  const projects = S.projects.map(p => {
    const s = d[p.id] || {}, a = s.production, b = s.staging;
    const checked = [a?.last_check, b?.last_check].filter(Boolean).sort()[0];
    return {p, a, b, checked};
  });
  const focusProjects = [...projects];
  if (overviewOptions.sort === "name") focusProjects.sort((a, b) => a.p.name.localeCompare(b.p.name));
  if (overviewOptions.sort === "checked") focusProjects.sort((a, b) => (b.checked || "").localeCompare(a.checked || ""));
  const ranks = new Map(focusProjects.map(({p}, index) => [p.id, index + 1]));
  const rows = projects.map(({p, a, b, checked}, index) => {
    const diff = a?.typo3 && b?.typo3 && a.typo3 !== b.typo3;
    const pdiff = a?.php && b?.php && a.php !== b.php;
    return `<tr data-rank="${ranks.get(p.id)}" data-original-order="${index}"><td class="focus-row-number">${ranks.get(p.id)}</td><td><a href="${pUrl(p)}">${esc(p.name)}</a>${diff ? ` <span class="chip sev-1" title="Production and staging run different TYPO3 versions">versions differ</span>` : ""}${pdiff ? ` <span class="chip sev-1" title="Production and staging run different PHP versions">PHP differs</span>` : ""}</td>
      ${[[a, ver(a)], [b, ver(b, a)]].map(([x, version]) => `<td class="${extUpdCls(x)}" title="${esc(extUpdTitle(x))}">${version}
        ${x?.has_data ? `<div class="focus-env-health">${ew(x)}</div>` : ""}</td>
        <td class="overview-health ${extUpdCls(x)}" title="${esc(extUpdTitle(x))}">${ew(x)}</td>`).join("")}
      <td class="sub">${checked ? esc(fmt(checked)) : "–"}</td></tr>`;
  }).join("");
  box.innerHTML = `<div class="head" style="margin-bottom:8px"><div><h2 style="margin:0">TYPO3 status – Production &amp; Staging</h2>
      <div class="sub" data-secondary-copy>From the last t3monitor check · <a href="#/scheduler">Scheduler</a> · “–” = not configured</div></div>
      <div class="overview-options">
        <select name="overview-sort" aria-label="Sort projects">
          ${[["original", "Project order"], ["name", "Project name"], ["checked", "Newest check"]].map(([value, label]) =>
            `<option value="${value}" ${overviewOptions.sort === value ? "selected" : ""}>${label}</option>`).join("")}
        </select>
      </div></div>
    <div class="wrap"><table class="typo3-overview"><thead><tr><th scope="col" class="focus-row-number" aria-label="Row number">#</th><th scope="col">Project</th>
      <th scope="col"><span class="overview-label">Prod TYPO3</span><span class="focus-env-label">Production</span></th>
      <th scope="col" class="overview-health">Prod E/W</th>
      <th scope="col"><span class="overview-label">Stg TYPO3</span><span class="focus-env-label">Staging</span></th>
      <th scope="col" class="overview-health">Stg E/W</th>
      <th title="Oldest check of the configured instances">Last check</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  updateOverviewOrder();
  box.querySelector(".overview-options").onchange = ({target}) => {
    overviewOptions.sort = target.value;
    loadT3mSummary(d);
    box.querySelector(`[name="${target.name}"]`).focus();
  };
}

function updateOverviewOrder() {
  const body = $("#t3sum tbody");
  if (!body) return;
  const key = document.documentElement.dataset.style === "focus" ? "rank" : "originalOrder";
  body.append(...[...body.rows].sort((a, b) => Number(a.dataset[key]) - Number(b.dataset[key])));
}

// "System overview" card (Production / Staging tiles); filled by loadT3m via #system-<env>
const systemOverviewCard = () => `
    <section class="card system-overview">
      <div class="system-overview-heading">
        <h2>System overview</h2>
        <button type="button" class="btn sec sm scroll-bottom" data-act="scrollbottom"
          aria-label="Scroll to bottom" title="Scroll to bottom"><span aria-hidden="true">↓</span></button>
      </div>
      <div class="system-environments">
        ${T3M_ENVS.map(e => `<section>
          <h3>${esc(e.label)}</h3>
          <div class="system-details" id="system-${e.env}" aria-live="polite">Loading…</div>
        </section>`).join("")}
      </div>
    </section>`;

function viewProject(p, pipelineId) {
  if (!hasCI(p)) return viewProjectNoCI(p);
  const a = p.auto_typo3 || {};
  const runs = S.runs.filter(r => r.project === p.id);
  const pid = pipelineId || (runs[0] && runs[0].pipeline);
  $("#view").innerHTML = `
    <div class="crumb"><a href="#/">Projects</a> / ${esc(p.name)}</div>
    <div class="head">
      <div><h1>${esc(p.name)}</h1>
        <div class="sub">${esc(p.path)} · <code>${esc(p.ref)}</code> · <a href="${esc(glUrl(p))}" target="_blank" rel="noopener">Open in GitLab ↗</a></div></div>
      <div class="actions">
        <button class="btn" data-act="run" data-mode="normal">▶ Run pipeline</button>
        ${a.enabled ? `<button class="btn sec" data-act="run" data-mode="update">Run TYPO3 update</button>` : ""}
        <button class="btn sec" data-act="updsend" title="Send ready-to-run commands for pending extension updates via Teams / email">Send update commands</button>
        <a class="btn sec" href="${pUrl(p)}/edit">Edit</a>
      </div>
    </div>
    ${systemOverviewCard()}
    <div class="two">
      <div class="stack">
        <div class="card"><h2 id="pipeTitle">${pid ? "Pipeline #" + esc(pid) : "Pipeline"}</h2>
          <div id="pipe">${pid ? `<p class="empty">Loading…</p>` : `<p class="empty">No pipeline started from the launcher yet. Click “Run pipeline”.</p>`}</div></div>
        <div class="card"><h2>Recent runs</h2><div class="runs">
          ${runs.map(r => `<a href="${pUrl(p)}/pl/${Number(r.pipeline)}" class="${r.pipeline === pid ? "on" : ""}">
            <span>#${esc(r.pipeline)} · ${esc(r.trigger)}</span><span class="sub">${esc(fmt(r.t))}</span></a>`).join("")
            || `<p class="empty">No runs yet.</p>`}
        </div></div>
      </div>
      <div class="stack">
        <div class="card project-config"><h2>Configuration</h2>
          <section>
            <h3>Pipeline <code>${esc(p.ref)}</code></h3>
            ${pipelineConfigDetails(p)}
          </section>
          ${p.production?.ref ? `<section>
            <h3>Production <code>${esc(p.production.ref)}</code></h3>
            ${pipelineConfigDetails(p.production)}
          </section>` : ""}
          <section>
            <h3>Automatic TYPO3 updates <span class="config-status ${a.enabled ? "sev0" : "sub"}">${a.enabled ? "On" : "Off"}</span></h3>
            ${a.enabled ? `<dl>
              <dt>Major version</dt><dd>${esc(a.major)}</dd>
              ${S.typo3_seen[p.id] ? `<dt>Last seen</dt><dd>${esc(S.typo3_seen[p.id])}</dd>` : ""}
              ${varsStr(a.variables) ? `<dt>Variables</dt><dd><code>${esc(varsStr(a.variables))}</code></dd>` : ""}
            </dl>` : ""}
          </section>
        </div>
        <div class="card danger-zone"><h2>Danger zone</h2>
          <p class="sub" style="margin:0 0 10px">Removes the project from the launcher only. Nothing changes in GitLab.</p>
          <button class="btn danger sm" data-act="del">Remove project</button></div>
      </div>
    </div>
    ${T3M_ENVS.map(e => `<details class="card full t3env" id="t3m-${e.env}"><summary>TYPO3 status – ${esc(e.label)}
      <span class="t3meta sub">Loading…</span></summary></details>`).join("")}`;
  $("#view").dataset.project = p.id;
  if (pid) loadPipeline(p, pid);
  T3M_ENVS.forEach(e => loadT3m(p, e));
}

function pipelineConfigDetails(config) {
  const variables = varsStr(config.variables), jobs = (config.auto_play || []).join(", ");
  if (!variables && !jobs) return "";
  return `<dl>
    ${variables ? `<dt>Variables</dt><dd><code>${esc(variables)}</code></dd>` : ""}
    ${jobs ? `<dt>Auto-play</dt><dd><code>${esc(jobs)}</code></dd>` : ""}
  </dl>`;
}

// Project without GitLab CI/CD: no pipelines, only TYPO3 status (t3monitor) and extension update messages
function viewProjectNoCI(p) {
  $("#view").innerHTML = `
    <div class="crumb"><a href="#/">Projects</a> / ${esc(p.name)}</div>
    <div class="head">
      <div><h1>${esc(p.name)}</h1>
        <div class="sub"><span class="chip">no CI/CD</span>${p.path ? ` · ${esc(p.path)}` : ""}${p.ref ? ` · <code>${esc(p.ref)}</code>` : ""}</div></div>
      <div class="actions">
        <button class="btn sec" data-act="updsend" title="Send pending extension updates via Teams / email${p.ref ? " (with ready-to-run commands)" : ""}">Send update list</button>
        <a class="btn sec" href="${pUrl(p)}/edit">Edit</a>
      </div>
    </div>
    ${systemOverviewCard()}
    ${T3M_ENVS.map(e => `<details class="card full t3env" id="t3m-${e.env}"><summary>TYPO3 status – ${esc(e.label)}
      <span class="t3meta sub">Loading…</span></summary></details>`).join("")}
    <div class="card danger-zone" style="margin-top:18px"><h2>Danger zone</h2>
      <p class="sub" style="margin:0 0 10px">Removes the project from the launcher only.</p>
      <button class="btn danger sm" data-act="del">Remove project</button></div>`;
  $("#view").dataset.project = p.id;
  T3M_ENVS.forEach(e => loadT3m(p, e));
}

const SEV = {"-2":"notice", "-1":"info", "0":"ok", "1":"warning", "2":"error"};
const sevBadge = n => `<span class="badge ${Number(n) === 0 ? "sev0" : "sev-" + Number(n)}">${esc(SEV[n] || n)}</span>`;  // CSS: sev-2 error, sev-1 warning, sev0 ok, sev--1/--2 info
const verCmp = (a, b) => { const x = String(a).split("."), y = String(b).split(".");
  for (let i = 0; i < 3; i++) { const d = (parseInt(x[i]) || 0) - (parseInt(y[i]) || 0); if (d) return d; } return 0; };

// Security section of an instance (result of the scheduled "PHP version & security advisories" task)
function secBlock(sec) {
  const task = S.scheduler.find(t => t.id === "security");
  if (!sec) return `<details><summary>Security · not checked yet</summary><p class="empty">Runs with the
    <a href="#/scheduler">${esc(task?.name || "security")}</a> task (${esc(task?.cfg.enabled === false ? "off" : task?.schedule || "–")}).</p></details>`;
  const adv = sec.advisories || [], php = sec.php;
  const meta = [adv.length ? `<span class="sev-2">${adv.length} advisor${adv.length === 1 ? "y" : "ies"}</span>` : "no advisories",
    php?.severity ? `<span class="sev-${php.severity}">${esc(php.text)}</span>` : ""].filter(Boolean).join(" · ");
  return `<details${adv.length || php?.severity ? " open" : ""}><summary>Security · ${meta}</summary>
    <p class="sub" style="margin:0 0 8px">${php ? esc(php.text) : "PHP version unknown"} · checked ${esc(fmt(sec.checked))}</p>
    ${adv.length ? `<div class="wrap"><table class="checks"><thead><tr><th>Severity</th><th>Package</th><th>Installed</th><th>Advisory</th><th>Affected</th></tr></thead><tbody>
      ${adv.map(a => `<tr><td><span class="badge ${a.severity === "low" ? "sev-1" : "sev-2"}">${esc(a.severity || "?")}</span></td><td><code>${esc(a.package)}</code></td>
        <td>${esc(a.version)}</td><td>${/^https?:\/\//.test(a.link || "") ? `<a href="${esc(a.link)}" target="_blank" rel="noopener">${esc(a.title)} ↗</a>` : esc(a.title)}${a.cve ? ` <span class="sub">${esc(a.cve)}</span>` : ""}</td>
        <td class="sub">${esc(a.affected)}</td></tr>`).join("")}</tbody></table></div>`
      : `<p class="empty">No known security advisories for TYPO3 core and the public extensions.</p>`}</details>`;
}

async function loadT3m(p, e, refreshNow) {
  const id = "#t3m-" + e.env, box = $(id); if (!box) return;
  const overview = $("#system-" + e.env);
  const url = p[e.cfg]?.url;
  // Collapsible section: heading + compact status in the summary, details in the body (open state is kept on re-render)
  const set = (meta, body) => box.innerHTML = `<summary>TYPO3 status – ${esc(e.label)} <span class="t3meta">${meta}</span></summary>
    <div class="t3body">${body}</div>`;
  if (!t3mOn(p, e)) {
    if (overview) overview.textContent = "Monitoring not configured";
    set(`<span class="sub">not configured</span>`, `<p class="empty">Add the ${esc(e.label)} t3monitor URL and key under
      <a href="${pUrl(p)}/edit">Edit</a> to see TYPO3 version, extensions, status checks and their history.</p>`);
    return;
  }
  let d;
  try { d = refreshNow ? await api("/api/t3monitor/refresh", {project:p.id, env:e.env})
                       : await api(`/api/t3monitor?project=${encodeURIComponent(p.id)}&env=${e.env}`); }
  catch (err) {
    if (overview) overview.textContent = "System status unavailable";
    set(`<span class="sev-2">error</span>`, `<p class="empty">Error: ${esc(err.message)}</p>`);
    return;
  }
  if ($(id) !== box || $("#view").dataset.project !== p.id) return;
  const c = d.current, head = `<div class="head" style="margin-bottom:12px"><div>
      <div class="sub">${c ? esc(c.site_name) + " · " : ""}<a href="${esc(url)}" target="_blank" rel="noopener">${esc(url)} ↗</a>
      · last check ${esc(fmt(d.last_check))} · <a href="#/scheduler">schedule: ${esc(S.scheduler.find(t => t.id === "t3monitor")?.cfg.enabled === false ? "off" : S.scheduler.find(t => t.id === "t3monitor")?.schedule)}</a></div></div>
      <button class="btn sec sm" data-act="t3mrefresh" data-env="${e.env}">↻ Refresh now</button></div>
    ${d.last_error ? `<p class="sev-2" style="margin:0 0 12px;font-size:13px">Last check failed: ${esc(d.last_error)}</p>` : ""}`;
  const failed = d.last_error ? `<span class="sev-2" title="${esc(d.last_error)}">⚠ last check failed</span>` : "";
  if (overview) overview.innerHTML = systemOverview(d);
  if (!c) { set(`<span class="sub">no data yet</span>${failed}`, head + `<p class="empty">No data yet. Click “Refresh now”.</p>`); return; }
  const counts = {}; c.status.forEach(x => counts[x.severity] = (counts[x.severity] || 0) + 1);
  const major = String(c.typo3 || "").split(".")[0], latest = S.typo3_latest[major];
  const upd = latest && c.typo3 && verCmp(latest, c.typo3) > 0;
  const problems = c.status.filter(x => x.severity >= 1).sort((a, b) => b.severity - a.severity);
  const exts = Object.entries(c.extensions).filter(([, e]) => !e.local), local = Object.entries(c.extensions).filter(([, e]) => e.local);
  // Extension updates (Packagist, newest stable release compatible with this site's TYPO3 version)
  const updExt = exts.filter(([, x]) => x.update), majExt = updExt.filter(([, x]) => x.major);
  const updTxt = updExt.length ? `${updExt.length} update${updExt.length === 1 ? "" : "s"}${majExt.length ? ` (${majExt.length} major)` : ""}` : "";
  const latestCell = x => x.local ? `<span class="sub">–</span>`
    : x.update ? `<span class="upd-v">↑ ${esc(x.latest)}</span>${x.major ? ` <span class="chip major" title="Major update: may contain breaking changes">major</span>` : ""}`
    : x.latest_error ? `<span class="sub" title="${esc(x.latest_error)}">unknown</span>`
    : !("latest" in x) ? `<span class="sub">not checked yet</span>`
    : x.latest === null ? `<span class="sub" title="Package not found on Packagist">not on Packagist</span>`
    : x.latest === "" ? `<span class="sub">no compatible release</span>` : `<span class="sub">up to date</span>`;
  const row = x => `<tr><td>${sevBadge(x.severity)}</td><td>${esc(x.group)}</td><td><b>${esc(x.title)}</b>
      ${x.message ? `<div class="msg">${esc(x.message)}</div>` : ""}</td><td>${esc(x.value)}</td></tr>`;
  set(`<b>${esc(c.typo3 || "?")}</b>${upd ? `<span class="sev-1">↑ ${esc(latest)}</span>` : ""}
      ${c.php ? `<span class="sub">PHP ${esc(c.php)}</span>` : ""}
      <span class="badge ${counts[2] ? "sev-2" : "sev0"}">${counts[2] || 0} error${counts[2] === 1 ? "" : "s"}</span>
      <span class="badge ${counts[1] ? "sev-1" : "sev0"}">${counts[1] || 0} warning${counts[1] === 1 ? "" : "s"}</span>
      ${updExt.length ? `<span class="badge" style="color:var(${majExt.length ? "--run" : "--acc"})">${esc(updTxt.replace("update", "ext update"))}</span>` : ""}
      <span class="sub">checked ${esc(fmt(d.last_check))}</span>${failed}`, head + `
    <div class="kpis">
      <div class="kpi"><div class="sub">TYPO3</div><div class="v">${esc(c.typo3 || "?")}</div>
        <div class="sub ${upd ? "sev-1" : "sev0"}">${latest ? (upd ? `update available: ${esc(latest)}` : `latest (${esc(latest)})`) : "latest unknown"}</div></div>
      <div class="kpi"><div class="sub">Errors</div><div class="v sev-2">${counts[2] || 0}</div></div>
      <div class="kpi"><div class="sub">Warnings</div><div class="v sev-1">${counts[1] || 0}</div></div>
      <div class="kpi"><div class="sub">OK checks</div><div class="v sev0">${counts[0] || 0}</div></div>
      <div class="kpi"><div class="sub">Extensions</div><div class="v">${exts.length}</div>${local.length ? `<div class="sub">+ ${local.length} local (hidden)</div>` : ""}
        ${updExt.length ? `<div class="sub ${majExt.length ? "sev-1" : ""}" style="${majExt.length ? "" : "color:var(--acc)"}">${esc(updTxt)}</div>` : ""}</div>
      <div class="kpi"><div class="sub">Unchanged since</div><div class="v" style="font-size:14px">${esc(fmt(d.since))}</div></div>
    </div>
    <div class="srv">${[["PHP", c.php], ["Database", c.db], ["Web server", c.webserver], ["OS", c.os]]
      .map(([k, val]) => `<div><div class="sub">${k}</div><div class="srv-v">${esc(val || "–")}</div></div>`).join("")}</div>
    <details><summary>Extensions (${exts.length})${updTxt ? ` · ${esc(updTxt)}` : ""}</summary>
      ${local.length ? `<label class="check" style="margin-bottom:8px"><input type="checkbox" class="showLocal"> Show local extensions (${local.length}): ${esc(local.map(([k]) => k).join(", "))}</label>` : ""}
      <div class="wrap"><table>
      <thead><tr><th>Extension</th><th>Title</th><th>Version</th><th>Latest</th><th>Composer package</th></tr></thead><tbody>
      ${[...exts, ...local].map(([k, e]) => `<tr class="${e.local ? "local" : ""} ${e.update ? "upd" + (e.major ? " major" : "") : ""}" ${e.local ? "hidden" : ""}
        ${!e.local && e.composer ? `data-ext="${esc(k)}" data-composer="${esc(e.composer)}" data-version="${esc(e.update ? e.latest : e.version)}"
          data-installed="${esc(e.version)}" data-major="${e.update && e.major ? 1 : ""}" title="Click to show the changelog${e.update ? " of " + esc(e.latest) : ""}"` : ""}>
        <td>${!e.local && e.composer ? `<span class="tw">▸</span>` : ""}<code>${esc(k)}</code>${e.local ? ` <span class="chip">local</span>` : ""}</td>
        <td>${esc(e.title)}</td><td>${esc(e.version)}</td><td>${latestCell(e)}</td><td>${esc(e.composer)}</td></tr>`).join("")}
      </tbody></table></div></details>
    ${secBlock(d.security)}
    <details><summary>Problems (${problems.length ? `${counts[2] || 0} error${counts[2] === 1 ? "" : "s"}, ${counts[1] || 0} warning${counts[1] === 1 ? "" : "s"}` : "none"})</summary>
      ${problems.length ? `<div class="wrap"><table class="checks"><thead><tr><th>Severity</th><th>Area</th><th>Check</th><th>Value</th></tr></thead>
      <tbody>${problems.map(row).join("")}</tbody></table></div>` : `<p class="empty">No errors or warnings.</p>`}</details>
    <details><summary>All status checks (${c.status.length})</summary><div class="wrap"><table class="checks">
      <thead><tr><th>Severity</th><th>Area</th><th>Check</th><th>Value</th></tr></thead>
      <tbody>${c.status.slice().sort((a, b) => b.severity - a.severity).map(row).join("")}</tbody></table></div></details>
    ${updHistory(d.updates || [])}
    <details><summary>History (${d.history.length} change${d.history.length === 1 ? "" : "s"})</summary><ul class="tl">
      ${d.history.map(h => `<li><div class="when">${esc(fmt(h.t))}${h.last !== h.t ? ` – seen until ${esc(fmt(h.last))}` : ""} · TYPO3 ${esc(h.typo3 || "?")}</div>
        <ul>${h.changes.map(x => `<li>${esc(x)}</li>`).join("")}</ul></li>`).join("")}
    </ul></details>`);
  box.querySelectorAll("tr[data-ext]").forEach(tr => tr.onclick = () => toggleChangelog(tr));
  const uh = box.querySelector("details.upd-hist");
  if (uh) uh.ontoggle = () => uh.open && loadReleaseInfo(uh);
  const sl = box.querySelector(".showLocal");
  if (sl) sl.onchange = () => box.querySelectorAll("tr.local").forEach(r => r.hidden = !sl.checked);
}

function systemOverview({current, last_check, last_error}) {
  const check = last_error ? `<span class="sev-2" title="${esc(last_error)}">Last check failed</span>`
    : last_check ? `Checked ${esc(fmt(last_check))}` : "";
  if (!current) return check || "No checks yet";
  const versions = [["TYPO3", current.typo3], ["PHP", current.php],
    ["Database", dbShort(current.db)], ["Web server", current.webserver]];
  const errors = current.status.filter(item => item.severity === 2).length;
  const warnings = current.status.filter(item => item.severity === 1).length;
  return `<dl>${versions.map(([label, value]) => `<div><dt>${label}</dt><dd>${esc(value || "–")}</dd></div>`).join("")}</dl>
    <div class="system-health">
      <span class="${errors ? "sev-2" : "sub"}">${errors} errors</span>
      <span class="${warnings ? "sev-1" : "sub"}">${warnings} warnings</span>
    </div>
    ${check ? `<div class="system-check sub">${check}</div>` : ""}`;
}

// Minimal Markdown -> HTML (everything escaped; only http(s) links, relative ones resolved against the file)
function mdRender(md, base) {
  const txt = s => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  const link = (t, u) => { let h; try { h = new URL(u, base || undefined).href; } catch { return txt(t); }
    return /^https?:/.test(h) ? `<a href="${esc(h)}" target="_blank" rel="noopener">${txt(t)}</a>` : txt(t); };
  const inline = raw => { let out = "", last = 0, m; const re = /\[([^\]]+)\]\(([^)\s]+)\)/g;
    while ((m = re.exec(raw))) { out += txt(raw.slice(last, m.index)) + link(m[1], m[2]); last = re.lastIndex; }
    return out + txt(raw.slice(last)); };
  let html = "", list = null, code = null;
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const ln of md.replace(/\r/g, "").split("\n")) {
    if (/^\s*```/.test(ln)) { if (code === null) { close(); code = []; } else { html += `<pre>${esc(code.join("\n"))}</pre>`; code = null; } continue; }
    if (code !== null) { code.push(ln); continue; }
    let m;
    if ((m = ln.match(/^#{1,6}\s+(.*)/))) { close(); html += `<div class="md-h">${inline(m[1].replace(/#+\s*$/, ""))}</div>`; }
    else if ((m = ln.match(/^\s*([-*+]|\d+[.)])\s+(.*)/))) { const t = /\d/.test(m[1]) ? "ol" : "ul";
      if (list !== t) { close(); html += `<${t}>`; list = t; } html += `<li>${inline(m[2])}</li>`; }
    else if (!ln.trim()) close();
    else { close(); html += `<p>${inline(ln)}</p>`; }
  }
  if (code !== null) html += `<pre>${esc(code.join("\n"))}</pre>`;
  close(); return html;
}

// Update history: TYPO3 / extension version changes between t3monitor snapshots (newest first)
const dmy = s => s ? s.slice(0, 10).split("-").reverse().join(".") : "";
const UPD_ICON = {updated: ["↻", "updated"], added: ["+", "added"], removed: ["✖", "removed"]};
function updHistory(rows) {
  if (!rows.length) return `<details class="upd-hist"><summary>Update history (none yet)</summary><p class="empty">No version changes recorded since the first check.</p></details>`;
  return `<details class="upd-hist"><summary>Update history (${rows.length})</summary><div class="wrap"><table class="upd-table">
    <thead><tr><th>Last change</th><th>Old version</th><th></th><th>Inst. version</th><th>Extension key</th><th>Name</th><th>Available since</th><th>Description</th></tr></thead><tbody>
    ${rows.map(r => { const [ic, lbl] = UPD_ICON[r.action]; const ver = r.new || r.old;
      return `<tr class="${r.core ? "core" : ""} ${r.action}" ${r.composer && ver ? `data-composer="${esc(r.composer)}" data-version="${esc(ver)}" data-core="${r.core ? 1 : ""}"` : ""}>
      <td>${esc(dmy(r.t))}</td><td>${esc(r.old || "–")}</td><td class="act" title="${lbl}">${ic}</td><td>${esc(r.new || "–")}</td>
      <td><code>${esc(r.key)}</code></td><td>${esc(r.title)}</td><td class="rel-time"></td><td class="rel-sum"></td></tr>`; }).join("")}
    </tbody></table></div><p class="sub" style="margin:6px 0 0">Recorded from t3monitor checks. Available since = release date of the installed version (removed: of the old version) on Packagist; description = first changelog line (GitHub/GitLab).</p></details>`;
}
async function loadReleaseInfo(det) {
  if (det.dataset.loaded) return;
  det.dataset.loaded = "1";
  const cache = {};
  for (const tr of det.querySelectorAll("tr[data-composer]")) {      // one at a time: Packagist/GitHub rate limits
    const x = tr.dataset, k = x.composer + "@" + x.version;
    tr.querySelector(".rel-time").textContent = "…";
    try {
      cache[k] = cache[k] || await api(`/api/ext/release?composer=${encodeURIComponent(x.composer)}&version=${encodeURIComponent(x.version)}&summary=${x.core ? 0 : 1}`);
      tr.querySelector(".rel-time").textContent = dmy(cache[k].time) || "–";
      const s = tr.querySelector(".rel-sum"); s.textContent = cache[k].summary; s.title = cache[k].summary;
    } catch { tr.querySelector(".rel-time").textContent = "–"; }
  }
}

// Extension row click: show/hide the changelog of the latest version (update) or of the installed version
async function toggleChangelog(tr) {
  const open = tr.nextElementSibling?.classList.contains("cl-row");
  tr.querySelector(".tw").textContent = open ? "▸" : "▾";
  if (open) return tr.nextElementSibling.remove();
  const x = tr.dataset, row = document.createElement("tr");
  row.className = "cl-row";
  const upd = x.version !== x.installed;
  row.innerHTML = `<td colspan="5"><div class="cl-box ${x.major ? "major" : ""}"><p class="empty">Loading changelog…</p></div></td>`;
  tr.after(row);
  const box = row.querySelector(".cl-box");
  try {
    const d = await api(`/api/ext/changelog?composer=${encodeURIComponent(x.composer)}&version=${encodeURIComponent(x.version)}&installed=${encodeURIComponent(x.installed)}`);
    const links = [d.url && `<a href="${esc(d.url)}" target="_blank" rel="noopener">Open source ↗</a>`,
      d.compare && `<a href="${esc(d.compare)}" target="_blank" rel="noopener">Full list of changes ${esc(x.installed)} → ${esc(d.version)} ↗</a>`,
      d.repo && `<a href="${esc(d.repo)}" target="_blank" rel="noopener">Repository ↗</a>`].filter(Boolean).join(" · ");
    box.innerHTML = `<div class="cl-head"><b>Changelog ${esc(x.ext)} ${esc(d.version)}</b>
        ${upd ? `<span class="${x.major ? "chip major" : "upd-v"}">${x.major ? "major update" : "update"} from ${esc(x.installed)}</span>` : `<span class="sub">installed version</span>`}
        ${d.found_in ? `<span class="sub">from ${esc(d.found_in)}</span>` : ""}<span class="sub">${links}</span></div>
      ${d.text ? `<div class="cl-body">${mdRender(d.text, d.base)}</div>`
        : `<p class="empty">No changelog found for ${esc(d.version)} (no release notes, no CHANGELOG.md entry). Use the links above.</p>`}`;
  } catch (e) { box.innerHTML = `<p class="empty">Changelog not available: ${esc(e.message)}</p>`; }
}

async function loadPipeline(p, pid) {
  clearTimeout(pollT);
  try {
    const d = await api(`/api/pipeline?project=${encodeURIComponent(p.id)}&id=${pid}`);
    if (!$("#pipe") || $("#view").dataset.project !== p.id) return;
    $("#pipeTitle").innerHTML = `Pipeline #${esc(pid)} · <span class="st s-${esc(d.pipeline.status)}">${esc(d.pipeline.status)}</span>
      · <a href="${esc(d.pipeline.web_url)}" target="_blank" rel="noopener" style="font-weight:400;font-size:13px">GitLab ↗</a>`;
    $("#pipe").innerHTML = `<div class="wrap"><table><thead><tr><th>Stage</th><th>Job</th><th>Status</th><th></th></tr></thead><tbody>
      ${d.jobs.slice().reverse().map(j => `<tr><td>${esc(j.stage)}</td><td>${esc(j.name)}</td>
        <td><span class="st s-${esc(j.status)}">${esc(j.status)}</span></td>
        <td>${j.status === "manual" ? `<button class="btn sm" data-act="play" data-job="${Number(j.id)}" data-name="${esc(j.name)}">▶ Play</button>` : ""}</td></tr>`).join("")
        || `<tr><td colspan="4" class="empty">No jobs.</td></tr>`}
      </tbody></table></div>
      ${p.production?.ref && d.pipeline.ref === p.ref && d.pipeline.status === "success"
        ? `<div class="actions" style="margin-top:12px"><button class="btn" data-act="promote" data-from="${Number(pid)}">🚀 Promote to production (${esc(p.production.ref)})</button></div>` : ""}`;
    if (ACTIVE.includes(d.pipeline.status)) pollT = setTimeout(() => loadPipeline(p, pid), 5000);
  } catch (e) { if ($("#pipe")) $("#pipe").innerHTML = `<p class="empty">Error: ${esc(e.message)}</p>`; }
}

// Branch select options: staging/production + GitLab branches + current value
function branchOpts(list, cur, allowNone, noneLabel = "– none (no promote) –") {
  const names = [...new Set(["staging", "production", ...list, ...(cur ? [cur] : [])])];
  return (allowNone ? `<option value="" ${cur ? "" : "selected"}>${esc(noneLabel)}</option>` : "")
    + names.map(b => `<option value="${esc(b)}" ${b === cur ? "selected" : ""}>${esc(b)}</option>`).join("");
}

// Defaults for a new project (work without GitLab; GitLab lookup may refine them)
const DEFAULTS = {gitlab_url:"https://gitlab.gingco.de", ref:"staging", variables:{}, auto_play:["build:main"],
  auto_typo3:{enabled:true, major:13, variables:{TARGET_TASK_NAME:"shup01"}, auto_play:[]},
  production:{ref:"production", variables:{}, auto_play:["build:main"]}};

// t3monitor instances per project (cfg = config key, f = form field prefix, keys/auth = lists in /api/state)
const T3M_ENVS = [
  {env:"production", label:"Production", cfg:"t3monitor", f:"t3m_", keys:"t3monitor_keys", auth:"t3monitor_auth",
   ph:"https://www.example.com/", hint:"Live TYPO3 site with the t3monitor extension installed."},
  {env:"staging", label:"Staging", cfg:"t3monitor_staging", f:"t3ms_", keys:"t3monitor_staging_keys", auth:"t3monitor_staging_auth",
   ph:"https://staging.example.com/", hint:"Staging instance with the t3monitor extension installed (own key)."}];
const t3mOn = (p, e) => !!(p[e.cfg]?.url && S[e.keys]?.includes(p.id));

function t3mFields(e, p) {
  const c = (p || {})[e.cfg] || {}, hasKey = p && S[e.keys]?.includes(p.id), hasAuth = p && S[e.auth]?.includes(p.id);
  return `<section class="card monitor-form"><div class="monitor-form-heading"><h3 class="sec-title">${esc(e.label)}</h3><span class="focus-monitor ${hasKey ? "is-configured" : "is-pending"}">${hasKey ? "Key saved" : "Key missing"}</span></div><div class="monitor-fields">
        <div><label for="${e.f}url">Site URL</label><input id="${e.f}url" name="${e.f}url" value="${esc(c.url)}" placeholder="${esc(e.ph)}">
          <div class="hint">${esc(e.hint)}</div></div>
        ${hasKey ? `<div class="monitor-saved-key">
          <div class="actions">
            <button type="button" class="btn sec sm" data-reveal="${e.f}key" data-saved-env="${esc(e.env)}" aria-controls="${e.f}saved-key" aria-expanded="false">Reveal saved key</button>
            <button type="button" class="btn sec sm" data-copy="${e.f}key" data-saved-copy hidden>Copy saved key</button>
          </div>
          <input id="${e.f}saved-key" type="text" aria-label="Saved ${esc(e.label)} key" readonly hidden spellcheck="false" autocomplete="off">
        </div>` : ""}
        <details class="monitor-key-field"${hasKey ? "" : " open"}>
          <summary>${hasKey ? "Replace key" : "Set up key"}</summary>
          <label for="${e.f}key">t3monitor key (64 characters)</label><input id="${e.f}key" name="${e.f}key" type="password" autocomplete="new-password" spellcheck="false" minlength="64" maxlength="64" pattern="[^\\s]{64}"
          title="Enter 64 characters without spaces" placeholder="64 characters">
          <div class="hint">Extension configuration → t3monitor → encryption_key.</div>
          <div class="actions monitor-key-actions">
            <button type="button" class="btn sec sm" data-gen="${e.f}key">Generate key</button>
            <button type="button" class="btn sec sm" data-reveal="${e.f}key" aria-controls="${e.f}key">Reveal</button>
            <button type="button" class="btn sec sm" data-copy="${e.f}key">Copy</button>
          </div>
          <p class="hint" data-key-draft="${e.f}key" hidden>Unsaved key. Set the same key on the ${esc(e.label.toLowerCase())} site before saving.</p>
          ${hasKey ? `<label class="check" style="margin-top:6px"><input type="checkbox" name="${e.f}key_clear"> Remove stored key</label>` : ""}</details>
        <details class="monitor-auth"${hasAuth || c.auth_user ? " open" : ""}><summary>Site authentication</summary>
        <div><label>Basic auth user (optional)</label><input name="${e.f}auth_user" value="${esc(c.auth_user)}" autocomplete="off" placeholder="only if the site is password-protected">
          <div class="hint" data-secondary-copy>Empty = no basic auth.</div></div>
        <div><label>Basic auth password</label><input name="${e.f}auth_password" type="password" autocomplete="new-password"
          placeholder="${hasAuth ? "stored – leave empty to keep" : "not stored"}">
          ${hasAuth ? `<label class="check" style="margin-top:6px"><input type="checkbox" name="${e.f}auth_clear"> Remove stored password</label>` : ""}</div>
        </details>
      </div></section>`;
}

function viewForm(p) {
  const v = p || DEFAULTS, a = v.auto_typo3 || DEFAULTS.auto_typo3;
  $("#view").innerHTML = `
    <div class="crumb"><a href="#/">Projects</a> / ${p ? `<a href="${pUrl(p)}">${esc(p.name)}</a> / Edit` : "New project"}</div>
    <div class="head"><h1>${p ? "Edit " + esc(p.name) : "New project"}</h1></div>
    <form id="pform" class="stack">
      <div class="card"><div class="sec-title">Basics</div>
        <div class="fields">
        <div><label>Name<span data-noci> *</span></label><input name="name" value="${esc(p?.name)}" placeholder="WVG Online"></div>
        <div><label>GitLab URL</label><input name="gitlab_url" value="${esc(v.gitlab_url || DEFAULTS.gitlab_url)}"></div>
        <div><label>Project path<span data-ci> *</span></label><input name="path" value="${esc(p?.path)}" placeholder="type to search GitLab…" list="projlist" autocomplete="off" required>
          <div class="hint" id="pinfo"></div></div>
        <datalist id="projlist"></datalist>
        <div><label>Branch<span data-ci> *</span></label><select name="ref" required>${branchOpts([], v.ref, true, "– none –")}</select></div>
      </div></div>
      <section class="project-monitoring" aria-labelledby="project-monitoring-title">
        <h2 id="project-monitoring-title">TYPO3 monitoring</h2>
        <div class="project-monitoring-grid">${T3M_ENVS.map(e => t3mFields(e, p)).join("")}</div>
      </section>
      <div class="card"><h2 class="sec-title">GitLab pipelines</h2>
        <label class="check" style="margin-bottom:12px"><input type="checkbox" name="ci" ${v.ci !== false ? "checked" : ""}> Uses GitLab CI/CD (pipelines)</label>
        <div class="hint" data-noci style="margin:-6px 0 12px">Off = TYPO3 monitoring only: no pipelines, no TYPO3 auto-update. Path and branch are optional
          (with a branch, extension update messages contain ready-to-run git/composer commands).</div>
      </div>
      <div class="card" data-ci><div class="sec-title">Run pipeline</div><div class="fields">
        <div><label>Variables</label><input name="variables" value="${esc(varsStr(v.variables))}" placeholder="KEY=VALUE, KEY2=VALUE2"></div>
        <div><label>Auto-play manual jobs</label><input name="auto_play" value="${esc((v.auto_play || []).join(", "))}" placeholder="build:main">
          <div class="hint" data-secondary-copy>These manual jobs are started automatically when ready.</div></div>
      </div></div>
      <div class="card" data-ci><div class="sec-title">TYPO3 auto-update</div>
        <label class="check"><input type="checkbox" name="auto_enabled" ${a.enabled ? "checked" : ""}> Start update pipeline when a new TYPO3 release appears</label>
        <div class="fields" style="margin-top:12px">
          <div><label>TYPO3 major</label><select name="major">${[...new Set([12, 13, 14, Number(a.major)])].filter(Boolean).sort((x, y) => x - y)
            .map(m => `<option value="${m}" ${m === Number(a.major) ? "selected" : ""}>${m}</option>`).join("")}</select></div>
          <div><label>Update variables</label><input name="auto_variables" value="${esc(varsStr(a.variables))}"></div>
          <div><label>Auto-play jobs (update)</label><input name="auto_typo3_play" value="${esc((a.auto_play || []).join(", "))}"></div>
        </div></div>
      <div class="card" data-ci><div class="sec-title">Production (promote)</div><div class="fields">
        <div><label>Production branch</label><select name="prod_ref">${branchOpts([], v.production?.ref || "", true)}</select>
          <div class="hint">Empty = no promote. Button appears after a successful pipeline on the branch above.</div></div>
        <div><label>Variables</label><input name="prod_variables" value="${esc(varsStr(v.production?.variables))}" placeholder="KEY=VALUE"></div>
        <div><label>Auto-play manual jobs</label><input name="prod_play" value="${esc((v.production ? v.production.auto_play || [] : v.auto_play || []).join(", "))}">
          <div class="hint" data-secondary-copy>Pre-filled from the jobs above; edit to differ.</div></div>
      </div></div>
      <div class="actions project-form-actions"><span class="sub" role="status" data-form-dirty hidden>Unsaved changes</span><button class="btn" type="submit">${p ? "Save changes" : "Create project"}</button>
        <a class="btn sec" href="${p ? pUrl(p) : "#/"}">Cancel</a></div>
    </form>`;
  const fm = $("#pform"), E = fm.elements, sp = E.auto_play, pp = E.prod_play;
  const syncCI = () => {                         // show/hide CI-only parts; path, branch required only with CI
    const on = E.ci.checked;
    fm.querySelectorAll("[data-ci]").forEach(el => el.hidden = !on);
    fm.querySelectorAll("[data-noci]").forEach(el => el.hidden = on);
    E.path.required = E.ref.required = on; E.name.required = !on;
  };
  E.ci.addEventListener("change", syncCI); syncCI();
  fm.addEventListener("invalid", ({target}) => {
    const details = target.closest("details");
    if (details) details.open = true;
  }, true);
  // Generate a 64-char t3monitor key locally (32 random bytes → hex).
  // Non-destructive: nothing is stored until "Save changes"; the SAME value must be set as the site's encryption_key.
  fm.addEventListener("click", async ev => {
    const b = ev.target.closest("[data-gen], [data-reveal]"); if (!b) return;
    const name = b.dataset.gen || b.dataset.reveal, inp = E[name];
    if (b.dataset.savedEnv) {
      const saved = fm.querySelector(`#${name.replace(/key$/, "saved-key")}`);
      const copy = fm.querySelector(`[data-saved-copy][data-copy="${name}"]`);
      if (!saved.hidden) {
        saved.hidden = copy.hidden = true;
        saved.value = "";
        b.textContent = "Reveal saved key";
        b.setAttribute("aria-expanded", "false");
        return;
      }
      b.disabled = true;
      try {
        const {key} = await api("/api/t3monitor/reveal-key", {project:p.id, env:b.dataset.savedEnv});
        if (!fm.isConnected) return;
        saved.value = key;
        saved.hidden = copy.hidden = false;
        b.textContent = "Hide saved key";
        b.setAttribute("aria-expanded", "true");
      } catch (e) { toast(e.message, true); }
      finally { b.disabled = false; }
      return;
    }
    if (b.dataset.reveal) {
      if (!inp.value) { toast("Generate or enter a key first", true); return; }
      inp.type = inp.type === "password" ? "text" : "password";
      b.textContent = inp.type === "text" ? "Hide" : "Reveal";
      return;
    }
    inp.value = [...crypto.getRandomValues(new Uint8Array(32))].map(x => x.toString(16).padStart(2, "0")).join("");
    inp.type = "password";
    fm.querySelector(`[data-reveal="${name}"]:not([data-saved-env])`).textContent = "Reveal";
    inp.dispatchEvent(new Event("input", {bubbles:true}));
  });
  // Copy the current key field value to the clipboard (clipboard API, with a legacy fallback for insecure contexts).
  fm.addEventListener("click", async ev => {
    const b = ev.target.closest("[data-copy]"); if (!b) return;
    ev.preventDefault();
    const saved = fm.querySelector(`#${b.dataset.copy.replace(/key$/, "saved-key")}`);
    const inp = b.hasAttribute("data-saved-copy") ? saved : E[b.dataset.copy], val = inp.value.trim();
    if (!val) { toast("Nothing to copy — generate or enter a key first", true); return; }
    try {
      if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(val);
      else {
        inp.focus(); inp.select();
        if (!document.execCommand("copy")) throw new Error("Clipboard unavailable");
      }
      toast("Key copied to clipboard");
    } catch (e) { toast("Copy failed. Reveal the key to copy it manually.", true); }
  });
  // Pre-fill from GitLab: only fields the user has not typed in; when editing, only empty ones.
  const touched = new Set();
  fm.addEventListener("input", ({target}) => {
    touched.add(target.name);
    fm.querySelector("[data-form-dirty]").hidden = false;
    const draft = fm.querySelector(`[data-key-draft="${target.name}"]`);
    if (draft) draft.hidden = !target.value;
  });
  const fill = (name, val) => {
    const el = E[name];
    if (val == null || val === "" || touched.has(name) || (p && el.value.trim())) return;
    if (el.tagName === "SELECT" && ![...el.options].some(o => o.value === String(val))) el.add(new Option(val, val));
    el.value = Array.isArray(val) ? val.join(", ") : val;
  };
  let searchT;
  E.path.addEventListener("input", () => {        // project search suggestions
    clearTimeout(searchT);
    const q = E.path.value.trim();
    if (q.length < 2) return;
    searchT = setTimeout(async () => {
      try {
        const r = await api(`/api/search?gitlab_url=${encodeURIComponent(E.gitlab_url.value.trim())}&q=${encodeURIComponent(q)}`);
        $("#projlist").innerHTML = r.map(x => `<option value="${esc(x.path)}">${esc(x.name)}</option>`).join("");
      } catch (e) { /* suggestions are optional */ }
    }, 300);
  });
  async function loadInfo() {
    const url = E.gitlab_url.value.trim(), path = E.path.value.trim();
    if (!url || !path.includes("/")) return;
    $("#pinfo").textContent = "Reading project from GitLab…";
    try {
      const d = await api(`/api/project-info?gitlab_url=${encodeURIComponent(url)}&path=${encodeURIComponent(path)}&ref=${encodeURIComponent(E.ref.value.trim())}`);
      E.ref.innerHTML = branchOpts(d.branches, E.ref.value, true, "– none –");
      E.prod_ref.innerHTML = branchOpts(d.branches, E.prod_ref.value, true);
      fill("name", d.name); fill("ref", d.ref); fill("auto_play", d.auto_play);
      fill("prod_ref", d.prod_ref); fill("prod_play", d.prod_play); fill("major", d.major);
      synced = pp.value === sp.value;
      $("#pinfo").textContent = `Pre-filled from GitLab (default branch: ${d.default}${d.major ? `, TYPO3 ${d.major}` : ""})`;
    } catch (e) { $("#pinfo").textContent = `GitLab lookup failed: ${e.message}`; }
  }
  E.path.addEventListener("change", loadInfo);
  E.ref.addEventListener("change", loadInfo);
  E.gitlab_url.addEventListener("change", loadInfo);
  let synced = pp.value === sp.value;            // mirror staging jobs until prod field is edited by hand
  sp.addEventListener("input", () => { if (synced) pp.value = sp.value; });
  pp.addEventListener("input", () => { synced = pp.value === sp.value; });
  loadInfo();
  $("#pform").onsubmit = async ev => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    const body = {ci:f.get("ci") === "on", name:f.get("name"), gitlab_url:f.get("gitlab_url"), path:f.get("path"), ref:f.get("ref"),
      variables:parseVars(f.get("variables")), auto_play:f.get("auto_play"),
      auto_enabled:f.get("auto_enabled") === "on", major:f.get("major"),
      auto_variables:parseVars(f.get("auto_variables")), auto_typo3_play:f.get("auto_typo3_play"),
      prod_ref:f.get("prod_ref"), prod_variables:parseVars(f.get("prod_variables")), prod_play:f.get("prod_play"),
      ...Object.fromEntries(T3M_ENVS.flatMap(e => [["url", f.get(e.f + "url")], ["key", f.get(e.f + "key")],
        ["key_clear", f.get(e.f + "key_clear") === "on"], ["auth_user", f.get(e.f + "auth_user")],
        ["auth_password", f.get(e.f + "auth_password")], ["auth_clear", f.get(e.f + "auth_clear") === "on"]]
        .map(([k, val]) => [e.f + k, val])))};
    try {
      const saved = p ? await api("/api/projects/update", {...body, id:p.id}) : await api("/api/projects", body);
      await refresh(); toast(p ? "Project saved" : "Project created"); location.hash = pUrl(saved);
    } catch (e) { toast(e.message, true); }
  };
}

function viewActivity() {
  const sec = S.typo3_security || {};
  $("#view").innerHTML = `
    <div class="head"><h1>Activity</h1></div>
    <div class="stack">
      <div class="card"><h2>TYPO3 security announcements</h2>
        <p class="sub" style="margin:0 0 12px">Source: news.typo3.com · last check: ${esc(fmt(sec.checked))} · <a href="#/scheduler">Scheduler</a></p>
        <div class="wrap"><table><tbody>
        ${(sec.items || []).slice(0, 15).map(i => `<tr><td class="sub" style="white-space:nowrap">${esc(i.date || "–")}</td>
          <td>${i.psa ? `<span class="badge sev-2">PSA</span> ` : ""}<a
            href="${/^https:\/\//.test(i.link) ? esc(i.link) : "#"}" target="_blank" rel="noopener noreferrer">${esc(i.title)}</a></td></tr>`).join("")
          || `<tr><td class="empty">Not checked yet.</td></tr>`}
        </tbody></table></div></div>
      <div class="card"><h2>Pipeline runs</h2><div class="wrap"><table>
        <thead><tr><th>Time</th><th>Project</th><th>Pipeline</th><th>Trigger</th></tr></thead><tbody>
        ${S.runs.map(r => { const p = proj(r.project); return `<tr><td>${esc(fmt(r.t))}</td>
          <td>${p ? `<a href="${pUrl(p)}">${esc(p.name)}</a>` : esc(r.project)}</td>
          <td>${p ? `<a href="${pUrl(p)}/pl/${Number(r.pipeline)}">#${esc(r.pipeline)}</a>` : "#" + esc(r.pipeline)}</td>
          <td>${esc(r.trigger)}</td></tr>`; }).join("") || `<tr><td colspan="4" class="empty">No runs yet.</td></tr>`}
        </tbody></table></div></div>
      <div class="card"><h2>Log</h2><div class="wrap"><table><tbody>
        ${S.log.map(l => `<tr><td class="sub" style="white-space:nowrap">${esc(fmt(l.t))}</td><td>${esc(l.msg)}</td></tr>`).join("")
          || `<tr><td class="empty">Empty.</td></tr>`}
      </tbody></table></div></div>
    </div>`;
}

function viewSettings() {
  const src = {app:"Stored in the app folder (.gitlab-token, chmod 600). It is never shown again.",
    home:"Using ~/.gitlab-token (fallback). Save a token here to store it in the app folder."}[S.token_source] || "No token stored.";
  const m = S.email;
  $("#view").innerHTML = `
    <div class="head"><h1>Settings</h1></div>
    <div class="stack">
      <div class="card"><h2>GitLab token</h2><p class="sub" style="margin:0 0 12px">${esc(src)}</p>
        <form id="tform" class="fields">
          <div><label>Personal access token (scope: api)</label><input name="token" type="password" autocomplete="off" placeholder="glpat-…" required></div>
          <div class="actions" style="align-items:end"><button class="btn" type="submit">Save token</button><button class="btn sec" type="submit" data-close="1">Save &amp; close</button>
            <button class="btn sec" type="button" data-act="tokentest">Test</button>
            <button class="btn danger" type="button" data-act="tokendel">Remove</button></div>
        </form></div>
      <div class="card"><h2>Microsoft Teams notifications</h2>
        <p class="sub" style="margin:0 0 12px" data-secondary-copy>Posts a message to a Teams channel when a pipeline started automatically by the TYPO3 watcher has finished (or could not be started).</p>
        ${!S.teams_url_set ? `<p class="sub">Create the webhook in Teams: channel → ⋯ → Workflows → "Post to a channel when a webhook request is received".</p>` : ""}
        <form id="msform" class="stack">
          <label class="check"><input type="checkbox" name="enabled" ${S.teams.enabled ? "checked" : ""}> Send Teams messages</label>
          <div class="fields">
            <div><label>Webhook URL</label><input name="url" type="password" autocomplete="off"
              placeholder="${S.teams_url_set ? "stored – leave empty to keep" : "https://…"}"></div>
          </div>
          <div class="actions"><button class="btn" type="submit">Save</button><button class="btn sec" type="submit" data-close="1">Save &amp; close</button>
            <button class="btn sec" type="button" data-act="teamstest">Save &amp; send test message</button>
            ${S.teams_url_set ? `<button class="btn danger" type="button" data-act="teamsdel">Remove URL</button>` : ""}</div>
        </form></div>
      <div class="card"><h2>Email notifications</h2>
        <p class="sub" style="margin:0 0 12px" data-secondary-copy>Sends an email when a pipeline started automatically by the TYPO3 watcher has finished (or could not be started).</p>
        <form id="eform" class="stack">
          <label class="check"><input type="checkbox" name="enabled" ${m.enabled ? "checked" : ""}> Send email notifications</label>
          <div class="fields">
            <div><label>SMTP host</label><input name="host" value="${esc(m.host)}" placeholder="smtp.example.com"></div>
            <div><label>Port</label><input name="port" type="number" min="1" max="65535" value="${esc(m.port)}"></div>
            <div><label>Security</label><select name="security">${[["starttls", "STARTTLS"], ["ssl", "SSL/TLS"], ["none", "None"]]
              .map(([k, l]) => `<option value="${k}" ${m.security === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
            <div><label>SMTP user (empty = no login)</label><input name="user" value="${esc(m.user)}" autocomplete="off"></div>
            <div><label>SMTP password</label><input name="password" type="password" autocomplete="new-password"
              placeholder="${S.email_password_set ? "stored – leave empty to keep" : "not stored"}"></div>
            <div><label>Sender</label><input name="from" value="${esc(m.from)}" placeholder="launcher@example.com"></div>
            <div><label>Recipients (comma-separated)</label><input name="to" value="${esc(m.to.join(", "))}" placeholder="a@example.com, b@example.com"></div>
          </div>
          <div class="actions"><button class="btn" type="submit">Save</button><button class="btn sec" type="submit" data-close="1">Save &amp; close</button>
            <button class="btn sec" type="button" data-act="mailtest">Save &amp; send test email</button>
            ${S.email_password_set ? `<button class="btn danger" type="button" data-act="mailpwdel">Remove password</button>` : ""}</div>
        </form></div>
      <div class="card"><h2>Export / import projects</h2>
        <p class="sub" style="margin:0 0 12px" data-secondary-copy>The export file contains all projects with their t3monitor keys and Basic auth passwords in plain text – pass it on over a trusted channel only. The GitLab token, Teams webhook and SMTP password are never exported.</p>
        <div class="stack">
          <div class="actions"><button class="btn sec" type="button" data-act="projexport">Export projects</button></div>
          <div class="fields"><div><label>Export file</label><input id="impFile" type="file" accept=".json,application/json"></div></div>
          <label class="check"><input type="checkbox" id="impOverwrite"> Overwrite projects that already exist (otherwise they are skipped)</label>
          <div class="actions"><button class="btn sec" type="button" data-act="projimport">Import projects</button></div>
        </div></div>
      <div class="card"><h2>TYPO3 release check</h2><dl>
        <dt>Schedule</dt><dd>${esc(S.scheduler.find(t => t.id === "typo3_release").schedule)} · <a href="#/scheduler">change in Scheduler</a></dd>
        <dt>Last check</dt><dd>${esc(fmt(S.last_check))}</dd>
        <dt>Latest</dt><dd>${Object.entries(S.typo3_latest).map(([m, v]) => `TYPO3 ${esc(m)}: ${esc(v)}`).join(", ") || "–"}</dd>
      </dl><div style="margin-top:12px"><button class="btn sec" data-act="check">Check now</button></div></div>
    </div>`;
  $("#tform").onsubmit = async ev => {
    ev.preventDefault();
    try { const d = await api("/api/token", {token:ev.target.token.value}); ev.target.reset(); await refresh(); toast(d.msg); if (!closeAfter(ev)) viewSettings(); }
    catch (e) { toast(e.message, true); }
  };
  $("#msform").onsubmit = async ev => {
    ev.preventDefault();
    try { await saveTeams(); toast("Teams settings saved"); closeAfter(ev); } catch (e) { toast(e.message, true); }
  };
  $("#eform").onsubmit = async ev => {
    ev.preventDefault();
    try { await saveEmail(); toast("Email settings saved"); closeAfter(ev); } catch (e) { toast(e.message, true); }
  };
}
async function saveTeams(extra) {
  const f = $("#msform");
  await api("/api/teams", {enabled:f.enabled.checked, url:f.url.value, ...extra});
  await refresh(); viewSettings();
}
async function saveEmail(extra) {
  const f = $("#eform");
  await api("/api/email", {enabled:f.enabled.checked, host:f.host.value, port:f.port.value, security:f.security.value,
    user:f.user.value, password:f.password.value, from:f.from.value, to:f.to.value, ...extra});
  await refresh(); viewSettings();
}

function viewScheduler() {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  $("#view").innerHTML = `
    <div class="head"><div><h1>Scheduler</h1><div class="sub" data-secondary-copy>Automatic tasks; they run while the launcher runs. A run missed while it was off starts right after the next start.</div></div></div>
    <div class="stack scheduler-tasks">${S.scheduler.map(t => { const c = t.cfg; return `
      <form class="card scheduler-task" data-task="${esc(t.id)}">
        <div class="head scheduler-task-heading" style="margin-bottom:8px"><div><h2 style="margin:0">${esc(t.name)}</h2><div class="sub" data-secondary-copy>${esc(t.description)}</div></div>
          <button class="btn sec sm" type="button" data-act="schedrun" data-id="${esc(t.id)}" ${t.running ? "disabled" : ""}>${t.running ? "Running…" : "▶ Run now"}</button></div>
        <dl class="scheduler-status" style="margin-bottom:14px">
          <dt>Status</dt><dd>${t.blocked ? `<span class="sev-1">paused (launcher started with --no-watch)</span>` : c.enabled ? `<span class="sev0">active</span> · ${esc(t.schedule)}` : `<span class="sev--1">off</span>`}</dd>
          <dt>Last run</dt><dd>${t.last_run ? `${esc(fmt(t.last_run))} · <span class="${t.ok ? "sev0" : "sev-2"}">${t.ok ? "OK" : "failed"}</span>` : "never"}</dd>
          ${t.result ? `<dt>Result</dt><dd>${esc(t.result)}</dd>` : ""}
          <dt>Next run</dt><dd>${t.next_run && !t.blocked ? esc(fmt(t.next_run)) : "–"}</dd>
        </dl>
        <label class="check scheduler-enabled"><input type="checkbox" name="enabled" ${c.enabled ? "checked" : ""}> Enabled</label>
        <div class="fields scheduler-fields" style="margin-top:12px">
          <div><label for="mode-${esc(t.id)}">Schedule</label><select id="mode-${esc(t.id)}" name="mode">
            <option value="interval" ${c.mode === "interval" ? "selected" : ""}>Every N hours</option>
            <option value="daily" ${c.mode === "daily" ? "selected" : ""}>Daily at a fixed time</option></select></div>
          <div data-for="interval"><label for="hours-${esc(t.id)}">Every (hours)</label><input id="hours-${esc(t.id)}" name="hours" type="number" min="0.25" max="168" step="0.25" value="${esc(c.hours)}"></div>
          <div data-for="daily"><label for="time-${esc(t.id)}">Time</label><input id="time-${esc(t.id)}" name="time" type="time" value="${esc(c.time)}"></div>
        </div>
        <div class="scheduler-days" data-for="daily" style="margin-top:12px" role="group" aria-labelledby="days-${esc(t.id)}"><div class="scheduler-days-label" id="days-${esc(t.id)}">Weekdays</div><div class="actions">
          ${days.map((d, i) => `<label class="check"><input type="checkbox" name="day" value="${i}" ${c.days.includes(i) ? "checked" : ""}> ${d}</label>`).join("")}</div></div>
        <div class="actions scheduler-save" style="margin-top:14px"><button class="btn" type="submit">Save</button><button class="btn sec" type="submit" data-close="1">Save &amp; close</button></div>
      </form>`; }).join("")}
    </div>`;
  viewScheduler.dirty = false;
  document.querySelectorAll("form[data-task]").forEach(f => {
    f.oninput = () => viewScheduler.dirty = true;
    const sync = () => f.querySelectorAll("[data-for]").forEach(el => el.hidden = el.dataset.for !== f.mode.value);
    f.mode.onchange = sync; sync();
    f.onsubmit = async ev => {
      ev.preventDefault();
      try {
        await api("/api/scheduler", {id:f.dataset.task, enabled:f.enabled.checked, mode:f.mode.value, hours:f.hours.value,
          time:f.time.value, days:[...f.querySelectorAll("[name=day]:checked")].map(x => Number(x.value))});
        await refresh(); toast("Schedule saved"); if (!closeAfter(ev)) viewScheduler();
      } catch (e) { toast(e.message, true); }
    };
  });
}

/* ---------------- actions ---------------- */
const actions = {
  scrollbottom() {
    window.scrollTo({top: document.documentElement.scrollHeight,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"});
  },
  async run(el) {
    const p = proj($("#view").dataset.project), upd = el.dataset.mode === "update";
    if (!confirm(`Start ${upd ? "TYPO3 update pipeline" : "pipeline"} for ${p.name} (${p.ref})?`)) return;
    el.disabled = true;
    try { const r = await api("/api/run", {project:p.id, mode:el.dataset.mode}); await refresh();
      toast(`Pipeline #${r.id} started`); location.hash = `${pUrl(p)}/pl/${r.id}`; }
    catch (e) { toast(e.message, true); el.disabled = false; }
  },
  async runall(el) {
    const ps = S.projects.filter(hasCI);
    if (!confirm(`Start pipelines for all ${ps.length} project(s) at once?\n\n` + ps.map(p => `• ${p.name} (${p.ref})`).join("\n"))) return;
    el.disabled = true;
    const res = await Promise.allSettled(ps.map(p => api("/api/run", {project:p.id, mode:"normal"})));
    const failed = res.map((r, i) => r.status === "rejected" ? `${ps[i].name}: ${r.reason.message}` : null).filter(Boolean);
    await refresh(); viewProjects();
    if (failed.length) toast(`${ps.length - failed.length}/${ps.length} started. Failed: ${failed.join(" | ")}`, true);
    else toast(`${ps.length} pipeline(s) started`);
  },
  async promote(el) {
    const p = proj($("#view").dataset.project), from = Number(el.dataset.from), ref = p.production.ref;
    if (!confirm(`PRODUCTION: start pipeline for ${p.name} on "${ref}"?\n\nStaging pipeline #${from} succeeded.\nMake sure "${ref}" already contains the staging changes (merged in GitLab) — the launcher does not merge.`)) return;
    el.disabled = true;
    try { const r = await api("/api/run", {project:p.id, mode:"promote", from}); await refresh();
      toast(`Production pipeline #${r.id} started`); location.hash = `${pUrl(p)}/pl/${r.id}`; }
    catch (e) { toast(e.message, true); el.disabled = false; }
  },
  async play(el) {
    const p = proj($("#view").dataset.project);
    if (!confirm(`Start manual job "${el.dataset.name}"?`)) return;
    el.disabled = true;
    try { await api("/api/play", {project:p.id, job:Number(el.dataset.job)}); toast(`${el.dataset.name} started`); render(); }
    catch (e) { toast(e.message, true); el.disabled = false; }
  },
  async del() {
    const p = proj($("#view").dataset.project);
    const name = p.name || p.id;
    if (!await confirmByName(`Remove ${name}?`,
      `<p>This removes the project from the launcher, including its stored t3monitor keys and Basic-auth passwords
       (production and staging). <b>This cannot be undone.</b> GitLab and the website itself are not touched.</p>`,
      name, "Remove this project")) return;
    try { await api("/api/projects/delete", {id:p.id, confirm:name}); await refresh(); toast("Project removed"); location.hash = "#/"; }
    catch (e) { toast(e.message, true); }
  },
  async check(el) {
    el.disabled = true;
    try { await api("/api/check-now", {}); await refresh(); viewSettings(); toast("TYPO3 check done"); }
    catch (e) { toast(e.message, true); el.disabled = false; }
  },
  async teamstest(el) {
    el.disabled = true;
    try { await saveTeams(); toast((await api("/api/teams/test", {})).msg); }
    catch (e) { toast(e.message, true); el.disabled = false; }
  },
  async teamsdel() {
    if (!confirm("Remove the stored Teams webhook URL? Teams messages are switched off.")) return;
    try { await saveTeams({enabled:false, url:"", clear_url:true}); toast("Webhook URL removed"); } catch (e) { toast(e.message, true); }
  },
  async mailtest(el) {
    el.disabled = true;
    try { await saveEmail(); toast((await api("/api/email/test", {})).msg); }
    catch (e) { toast(e.message, true); el.disabled = false; }
  },
  async mailpwdel() {
    if (!confirm("Remove the stored SMTP password?")) return;
    try { await saveEmail({password:"", clear_password:true}); toast("SMTP password removed"); } catch (e) { toast(e.message, true); }
  },
  async schedrun(el) {
    el.disabled = true; el.textContent = "Running…";
    try { const r = await api("/api/scheduler/run", {id:el.dataset.id}); await refresh(); viewScheduler(); toast(r.result, !r.ok); }
    catch (e) { toast(e.message, true); el.disabled = false; el.textContent = "▶ Run now"; }
  },
  async updsend(el) {
    el.disabled = true;
    try { toast((await api("/api/updates/send", {project:$("#view").dataset.project})).msg); }
    catch (e) { toast(e.message, true); }
    el.disabled = false;
  },
  async t3mrefresh(el) {
    el.disabled = true; el.textContent = "Checking…";
    await loadT3m(proj($("#view").dataset.project), T3M_ENVS.find(e => e.env === el.dataset.env), true);
  },
  async projexport(el) {
    el.disabled = true;
    try {
      const d = await api("/api/projects/export", {}), n = new Date(), z = x => String(x).padStart(2, "0");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], {type:"application/json"}));
      a.download = `t3-watchdock-projects-${n.getFullYear()}${z(n.getMonth() + 1)}${z(n.getDate())}.json`;
      a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      toast(`${d.projects.length} projects exported (file contains keys and passwords)`);
    } catch (e) { toast(e.message, true); }
    el.disabled = false;
  },
  async projimport(el) {
    const file = $("#impFile").files[0], overwrite = $("#impOverwrite").checked;
    if (!file) return toast("Choose an export file first", true);
    let data;
    try { data = JSON.parse(await file.text()); } catch { return toast("The file is not valid JSON", true); }
    const list = Array.isArray(data?.projects) ? data.projects : [];
    const hosts = [...new Set(list.map(x => x?.project?.gitlab_url).filter(Boolean))];   // the GitLab token is sent to these hosts
    if (!confirm(`Import ${list.length} projects${overwrite ? " and overwrite existing ones" : ""}?\n\nGitLab hosts in this file (your GitLab token is sent to them):\n${hosts.join("\n") || "–"}`)) return;
    el.disabled = true;
    try {
      const r = await api("/api/projects/import", {data, overwrite});
      await refresh(); viewSettings();
      toast(`Import: ${r.added.length} added, ${r.updated.length} updated, ${r.skipped.length} skipped`);
    } catch (e) { toast(e.message, true); el.disabled = false; }
  },
  async tokentest() { try { toast((await api("/api/token/test", {})).msg); } catch (e) { toast(e.message, true); } },
  async tokendel() {
    if (!confirm("Remove the stored GitLab token?")) return;
    try { await api("/api/token/delete", {}); await refresh(); viewSettings(); toast("Token removed"); } catch (e) { toast(e.message, true); }
  },
};
document.addEventListener("click", e => {
  const el = e.target.closest("[data-act]");
  if (el && actions[el.dataset.act]) { e.preventDefault(); actions[el.dataset.act](el); }
});

window.addEventListener("hashchange", render);
render();
setInterval(async () => {          // refresh list views only when their data changed; never interrupt forms or pipeline view
  if (document.hidden) return;     // background tab: no polling
  const h = location.hash.slice(1) || "/", prevS = JSON.stringify(S), prevSum = JSON.stringify(T3SUM);
  await refresh();
  const changed = JSON.stringify(S) !== prevS;
  if (h === "/" && S.projects.length) {
    let sum; try { sum = await api("/api/t3monitor/summary"); } catch { return; }
    if (changed || JSON.stringify(sum) !== prevSum) { T3SUM = sum; viewProjects(true); }
  } else if (!changed) return;
  else if (h === "/") viewProjects();
  else if (h === "/activity") viewActivity();
  else if (h === "/scheduler" && !viewScheduler.dirty) viewScheduler();
}, 30000);
