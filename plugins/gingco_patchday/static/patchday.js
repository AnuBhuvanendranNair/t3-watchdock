// Gingco Patchday plugin: "Patchday" button on the project page (config.json: "gingco_patchday": {"button": true}).
// The click is handed to the Patchday extension (its bridge script marks the page with data-patchday="1").
(() => {
  const {api, toast, ic} = window.watchdock;
  let opts = null;

  async function projectPage(p, view) {
    opts = opts || await api("/api/plugins/gingco_patchday/settings").catch(() => ({}));
    const actions = view.querySelector(".head .actions");
    if (!opts.button || !actions || view.dataset.project !== p.id || actions.querySelector(".patchday")) return;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn sec icon patchday";
    b.innerHTML = ic("patchday");
    b.title = "Patchday: write the update history (production) into the Patchday protocol in OpenProject (Patchday extension)";
    b.setAttribute("aria-label", b.title);
    b.onclick = () => {
      if (document.documentElement.dataset.patchday !== "1")
        return toast("Patchday extension not found. Install it, save its options once (access to this address) and reload this page.", true);
      toast("Patchday: reading the site, then OpenProject opens…");
      window.postMessage({type: "patchday:run", project: p.id}, location.origin);
    };
    actions.prepend(b);
  }

  // result from the extension (via its bridge): show errors
  window.addEventListener("message", e => {
    if (e.source !== window || e.origin !== location.origin || e.data?.type !== "patchday:status") return;
    if (e.data.error) toast(e.data.error, true); else if (e.data.msg) toast(e.data.msg);
  });

  window.watchdock.register({projectPage});
})();
