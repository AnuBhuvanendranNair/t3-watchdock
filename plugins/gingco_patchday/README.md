**Patchday Plugin – README - Gingco Communication - Version: 2.0 - 11 2026**

---

# Patchday plugin (Gingco Communication only)

Writes the update history of a project from **T3 Watchdock** into its **Patchday protocol** in **OpenProject** (`op.hub.gingco.de`).
Successor of the stand-alone Patchday extension 1.4: the data now comes from T3 Watchdock instead of T3Monitor (`t3m.hub.gingco.de`).

Two parts:

| Part | Purpose |
|---|---|
| `plugin.py`, `static/patchday.js` | T3 Watchdock plugin: update history per project, OpenProject link per project (*Settings → Patchday*), *Patchday ↗* button on the project page |
| `chrome-extension/` | Chrome extension: reads the data from the open T3 Watchdock tab and fills the OpenProject page (editor, duplicate check, time, executor, confirmation before saving — unchanged from 1.4) |

## Setup

1. `config.json` of T3 Watchdock: add `"plugins": {"gingco_patchday": {}}` and reload the page (Docker: rebuild once, `docker compose up -d --build`).
2. *Settings → Patchday (OpenProject)*: enter the link to the Patchday protocol for each project, click *Save links*.
3. Chrome: `chrome://extensions` → **Developer mode** → **Load unpacked** → select `plugins/gingco_patchday/chrome-extension`. Remove the old Patchday 1.x extension.
4. Extension options (right-click icon → **Options**): names, time option, T3 Watchdock address (default `http://127.0.0.1:8787`). **Save** asks Chrome once for access to that address (needed for *Alle ausführen*).

## Workflow

- **One project:** open the project page in T3 Watchdock (`#/p/<id>`) and click the extension icon. T3 Watchdock reads the site again (t3monitor, production), then OpenProject opens next to it and the rows are inserted as before. No link yet → the extension asks once and saves it in T3 Watchdock.
- **All projects:** right-click the extension icon → **Alle ausführen**. Runs every project that has an OpenProject link.

## Data

- Source: the update history of the **production** instance (version changes between t3monitor snapshots; own vendors from `t3monitor_local_vendors` are left out).
- Date = day on which T3 Watchdock noticed the change. Every run reads the site first, so updates made the same day get today's date.
- History starts with the first t3monitor check of the project in T3 Watchdock. Older rows already in the protocol stay; the duplicate check skips them.
- Site name = project name in T3 Watchdock. The first run on a protocol page used with 1.x shows the warning "Diese Seite wurde bisher für … verwendet" once (old name from T3Monitor); confirm it.
- Projects without t3monitor data (production) give an error instead of "Keine Updates gefunden".

## API (plugin)

| Route | Purpose |
|---|---|
| `GET /api/plugins/gingco_patchday/data?project=<id>&refresh=1` | Update history grouped by day (format of the extension); `refresh=1` reads the site first |
| `GET /api/plugins/gingco_patchday/projects` | All projects with their OpenProject link |
| `POST /api/plugins/gingco_patchday/links` | `{"links": {"<id>": "https://…"}}`; empty link removes it |

The extension calls these from inside the T3 Watchdock tab (same origin), so T3 Watchdock's Host / Origin checks stay unchanged.

## Versions

| Version | Changes |
|---|---|
| 2.0 | Data from T3 Watchdock instead of T3Monitor; OpenProject links stored in T3 Watchdock; CSV without mapping rows (1.x mapping rows are ignored on import) |
| 1.4 | Last stand-alone version (repository `patchday`) |
