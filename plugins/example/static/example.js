// Example plugin, browser part. Every *.js / *.css file in static/ is loaded on page load while the plugin is on.
// window.watchdock gives: register(hooks), api(path, body?), esc(text), toast(msg, isError?), ic(iconName), proj(id), state()
(() => {
  const {api, esc, toast} = window.watchdock;

  // Called after a project page is drawn: p = project, view = the page element
  async function projectPage(p, view) {
    if (view.querySelector(".example-card")) return;
    let d;
    try { d = await api(`/api/plugins/example/info?project=${encodeURIComponent(p.id)}`); }
    catch (e) { return toast(`Example plugin: ${e.message}`, true); }
    if (view.dataset.project !== p.id) return;                 // user moved on to another page meanwhile
    const card = document.createElement("div");
    card.className = "card example-card";
    card.innerHTML = `<h2>Example plugin</h2><p class="sub">${esc(d.greeting)}, ${esc(d.project)}!</p>
      <button type="button" class="btn sec sm">Ping</button>`;
    card.querySelector("button").onclick = async () => {
      try { await api("/api/plugins/example/ping", {project: p.id}); toast("Ping logged (see Activity)"); }
      catch (e) { toast(e.message, true); }
    };
    const danger = view.querySelector(".danger-zone");
    if (danger) danger.before(card); else view.append(card);
  }

  // Called after the Settings page is drawn: stack = the column of setting cards (append your own card)
  function settingsPage(stack) {}

  window.watchdock.register({projectPage, settingsPage});
})();
