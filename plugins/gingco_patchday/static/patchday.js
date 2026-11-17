// Gingco Patchday plugin: "Patchday" button on the project page (config.json: "gingco_patchday": {"button": true}).
// The click is handed to the Patchday extension (its bridge script marks the page with data-patchday="1").
(() => {
  const {api, toast} = window.watchdock;
  let opts = null;

  async function projectPage(p, view) {
    opts = opts || await api("/api/plugins/gingco_patchday/settings").catch(() => ({}));
    const actions = view.querySelector(".head .actions");
    if (!opts.button || !actions || view.dataset.project !== p.id || actions.querySelector(".patchday")) return;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn sec patchday";
    b.textContent = "Patchday";
    b.title = "Write the update history (production) into the Patchday protocol in OpenProject (Patchday extension)";
    b.onclick = () => {
      if (document.documentElement.dataset.patchday !== "1")
        return toast("Patchday extension not found. Install it, save its options once (access to this address) and reload this page.", true);
      window.postMessage({type: "patchday:run", project: p.id}, location.origin);
    };
    actions.prepend(b);
  }

  window.watchdock.register({projectPage});
})();
