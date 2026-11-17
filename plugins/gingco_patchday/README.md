**Patchday Plugin – README - Gingco Communication - Version: 2.0 - 11 2026**

---

# Patchday plugin (Gingco Communication only)

Writes the update history of a project from **T3 Watchdock** into its **Patchday protocol** in **OpenProject** (`op.hub.gingco.de`).
Successor of the stand-alone Patchday extension 1.4: the data now comes from T3 Watchdock instead of T3Monitor (`t3m.hub.gingco.de`).

Two parts:

| Part | Purpose |
|---|---|
| `plugin.py`, `static/patchday.js` | T3 Watchdock plugin (read-only): update history (production), project list, optional *Patchday* button on the project page |
| `chrome-extension/` | Browser extension (Chrome, Firefox 128+): settings incl. OpenProject link per website (domain); reads the data from the open T3 Watchdock tab and fills the OpenProject page (editor, duplicate check, time, executor, confirmation before saving — unchanged from 1.4) |

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
3. Extension options (right-click icon → **Options**): names, time option, T3 Watchdock address (default `http://127.0.0.1:8787`), then **Projekte aus T3 Watchdock laden** (adds one row per domain) and enter the OpenProject link per website. Rows without a link are not saved. Access to `127.0.0.1`, `localhost` and `local-gitlabrunner.local` is built in; for any other T3 Watchdock address **Speichern** asks once for access.
4. **CSV exportieren** = backup of all settings incl. links (also to share them with colleagues).

## Firefox

The same folder works in Firefox 128+ (`manifest.json` lists the background script for both browsers, add-on ID `patchday@gingco.de`).

- Test: `about:debugging` → *This Firefox* → **Load Temporary Add-on** → select `chrome-extension/manifest.json` (removed when Firefox restarts).
- Permanent: Firefox only installs signed add-ons. Sign it as *unlisted* (self-distributed) on addons.mozilla.org, then install the signed `.xpi`.
- Firefox may not grant site access at install: *about:addons* → Patchday → **Permissions** → allow `op.hub.gingco.de` and the T3 Watchdock address.
- Settings are stored per browser: use **CSV exportieren / importieren** to move them from Chrome.

## Workflow

- **One project:** open the project page in T3 Watchdock (`#/p/<id>`) and click **Patchday** (button) or the extension icon. T3 Watchdock reads the site again (t3monitor, production), then OpenProject opens next to it and the rows are inserted as before. No link yet → the extension asks once and saves it in its settings.
- **All projects:** right-click the extension icon → **Alle ausführen**. Runs every mapping in the settings.
- **Nothing new** (history empty or everything already in the protocol): asks, then adds a row for today with "Keine Updates gefunden" — as in 1.x. No prompt if today already has a row.
- **Login:** only OpenProject (log in first; on the login page the rows are inserted after login, within 10 minutes). No T3Monitor login needed.

**Button → extension:** the extension loads a small script (`wd-bridge.js`) on T3 Watchdock pages. It marks the page (`data-patchday="1"`), passes the button click to the extension and shows its result: errors and cancels appear as a message top right. After reloading the extension, reload the T3 Watchdock page too.

## Troubleshooting

| Message | Solution |
|---|---|
| "Patchday extension not found" | Extension not installed, or the T3 Watchdock page was opened before it: reload the page (F5) |
| "… Erweiterung neu geladen? Bitte diese Seite neu laden" | Extension was reloaded: reload the T3 Watchdock page |
| "Die Erweiterung kann diese Seite nicht lesen" | No site access: `chrome://extensions` → Patchday → *Details* → *Site access* (Firefox: *about:addons* → *Permissions*) |
| "No project with production domain … in T3 Watchdock" | Domain in the mapping does not match the production t3monitor URL of any project |
| "No t3monitor data for … (production)" | Set the production t3monitor URL and key of the project in T3 Watchdock |
| "Plugin "gingco_patchday" ist in T3 Watchdock nicht aktiviert" | Add the plugin to `config.json` (see Setup) |

## Data

- Source: the update history of the **production** instance (version changes between t3monitor snapshots; own vendors from `t3monitor_local_vendors` are left out).
- Date = day on which T3 Watchdock noticed the change. Every run reads the site first, so updates made the same day get today's date.
- History starts with the first t3monitor check of the project in T3 Watchdock. Older rows already in the protocol stay; the duplicate check skips them.
- Site name in OpenProject = production domain (as T3Monitor used in 1.x), so protocol pages used with 1.x match without the warning "Diese Seite wurde bisher für … verwendet".
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
| 2.0 | Data from T3 Watchdock instead of T3Monitor; mapping by production domain; optional *Patchday* button in T3 Watchdock; Firefox 128+; 1.x CSV mapping rows are taken over when their website is a domain |
| 1.4 | Last stand-alone version (repository `patchday`) |
