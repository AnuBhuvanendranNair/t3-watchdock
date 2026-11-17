// Gingco Patchday plugin: OpenProject link per project (Settings) and a link to the protocol on the project page.
(() => {
  const {api, esc, toast} = window.watchdock, R = "/api/plugins/gingco_patchday/";

  async function projectPage(p, view) {
    const actions = view.querySelector(".head .actions");
    if (!actions) return;
    let list; try { list = await api(R + "projects"); } catch { return; }
    const op = (list.find(x => x.id === p.id) || {}).op;
    if (view.dataset.project !== p.id || actions.querySelector(".patchday")) return;   // page changed meanwhile
    actions.insertAdjacentHTML("afterbegin", op
      ? `<a class="btn sec patchday" href="${esc(op)}" target="_blank" rel="noopener" title="Patchday protocol in OpenProject. Fill it: click the Patchday extension icon on this page.">Patchday ↗</a>`
      : `<a class="btn sec patchday" href="#/settings" title="No OpenProject link for this project yet">Patchday: set link</a>`);
  }

  async function settingsPage(stack) {
    if (!stack) return;
    let list; try { list = await api(R + "projects"); } catch (e) { return toast(e.message, true); }
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<h2>Patchday (OpenProject)</h2>
      <p class="sub" style="margin:0 0 12px">Link to the Patchday protocol of each project. The Patchday Chrome extension
        writes the update history (production) into it: open the project page here and click the extension icon.</p>
      <form class="stack">
        ${list.map(x => `<div><label>${esc(x.name)}</label><input type="url" name="${esc(x.id)}" value="${esc(x.op)}"
          placeholder="https://op.hub.gingco.de/projects/…/wiki/…"></div>`).join("")}
        <div class="actions"><button class="btn" type="submit">Save links</button></div>
      </form>`;
    card.querySelector("form").onsubmit = async ev => {
      ev.preventDefault();
      const links = Object.fromEntries([...ev.target.querySelectorAll("input")].map(i => [i.name, i.value.trim()]));
      try { await api(R + "links", {links}); toast("Patchday links saved"); } catch (e) { toast(e.message, true); }
    };
    stack.append(card);
  }

  window.watchdock.register({projectPage, settingsPage});
})();
