**Patchday Plugin – README - Gingco Communication - Version: 2.0 - 11 2026**

---

# Patchday plugin (Gingco Communication only)

Writes the update history of a project from **T3 Watchdock** into its **Patchday protocol** in **OpenProject** (`op.hub.gingco.de`).
Successor of the stand-alone Patchday extension 1.4: the data now comes from T3 Watchdock instead of T3Monitor (`t3m.hub.gingco.de`).

Two parts:

| Part | Purpose |
|---|---|
| `plugin.py`, `static/patchday.js` | T3 Watchdock plugin (read-only): update history (production), project list, optional *Patchday* button on the project page |
| `chrome-extension/` | Chrome extension: settings incl. OpenProject link per website (domain); reads the data from the open T3 Watchdock tab and fills the OpenProject page (editor, duplicate check, time, executor, confirmation before saving — unchanged from 1.4) |

Everything that only the extension needs (names, time option, OpenProject links) is stored in the extension. T3 Watchdock only provides the data.

## Mapping

Key = **production domain** of the website: host of the production t3monitor URL in T3 Watchdock, lowercase, without `www.` (e.g. `https://www.die-region.de/` → `die-region.de`). Subdomains stay separate (`eintracht.com` ≠ `verein.eintracht.com`).

- Same in every T3 Watchdock installation → the CSV can be shared with colleagues.
- Stable when a project is renamed, re-created or moved to another GitLab group.
- Only a change of the production domain needs the row to be updated.
- Projects without a production t3monitor URL cannot be mapped (and have no data for Patchday).

## Setup

1. `config.json` of T3 Watchdock: add `"plugins": {"gingco_patchday": {"button": true}}` (Docker: rebuild once, `docker compose up -d --build`).
   `"button": true` shows a **Patchday** button on the project page; without it, start with the extension icon only.
2. Chrome: `chrome://extensions` → **Developer mode** → **Load unpacked** → select `plugins/gingco_patchday/chrome-extension`.
   Before removing an old Patchday 1.x: export its settings as CSV. Chrome deletes an extension's settings when it is removed.
3. Extension options (right-click icon → **Options**): names, time option, T3 Watchdock address (default `http://127.0.0.1:8787`), then **Projekte aus T3 Watchdock laden** (adds one row per domain) and enter the OpenProject link per website. Rows without a link are not saved. **Speichern** asks Chrome once for access to the T3 Watchdock address.
4. **CSV exportieren** = backup of all settings incl. links (also to share them with colleagues).

## Workflow

- **One project:** open the project page in T3 Watchdock (`#/p/<id>`) and click **Patchday** (button) or the extension icon. T3 Watchdock reads the site again (t3monitor, production), then OpenProject opens next to it and the rows are inserted as before. No link yet → the extension asks once and saves it in its settings.
- **All projects:** right-click the extension icon → **Alle ausführen**. Runs every mapping in the settings.

**Button → extension:** after **Speichern** in the options (access granted), the extension adds a small script (`wd-bridge.js`) to the T3 Watchdock address. It marks the page (`data-patchday="1"`) and passes the button click to the extension. Pages opened before need a reload. Without the extension the button only shows a message.

## Data

- Source: the update history of the **production** instance (version changes between t3monitor snapshots; own vendors from `t3monitor_local_vendors` are left out).
- Date = day on which T3 Watchdock noticed the change. Every run reads the site first, so updates made the same day get today's date.
- History starts with the first t3monitor check of the project in T3 Watchdock. Older rows already in the protocol stay; the duplicate check skips them.
- Site name = project name in T3 Watchdock. The first run on a protocol page used with 1.x shows the warning "Diese Seite wurde bisher für … verwendet" once (old name from T3Monitor); confirm it.
- Projects without t3monitor data (production) give an error instead of "Keine Updates gefunden".

## API (plugin)

| Route | Purpose |
|---|---|
| `GET /api/plugins/gingco_patchday/data?domain=<domain>&refresh=1` | Update history grouped by day (format of the extension); also `project=<id>`; `refresh=1` reads the site first |
| `GET /api/plugins/gingco_patchday/projects` | All projects (id, name, domain), for *Projekte laden* |
| `GET /api/plugins/gingco_patchday/settings` | `{"button": true/false}` for the web UI |

The extension calls these from inside the T3 Watchdock tab (same origin), so T3 Watchdock's Host / Origin checks stay unchanged.

## Versions

| Version | Changes |
|---|---|
| 2.0 | Data from T3 Watchdock instead of T3Monitor; mapping by production domain; optional *Patchday* button in T3 Watchdock; 1.x CSV mapping rows are taken over when their website is a domain |
| 1.4 | Last stand-alone version (repository `patchday`) |
