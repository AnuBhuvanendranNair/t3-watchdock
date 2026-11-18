# Example plugin

Skeleton for a new plugin. It does nothing useful: it adds a card to every project page with a greeting and a *Ping* button.

## Try it

1. *Plugins* page → *Example plugin* → tick *Switched on* → *Save*.
2. Open a project: the card is above the *Danger zone*.
3. Optional setting: `{"greeting": "Moin"}`.

## Write your own

1. Copy this folder to `plugins/<your_name>/` (lowercase letters, digits, `_`).
2. In `plugin.py` set `NAME = "<your_name>"`, write the docstring (first line = title on the Plugins page, second paragraph = description) and your routes.
3. Rename `static/example.js` / `example.css`, change the API paths to `/api/plugins/<your_name>/…`.
4. Rebuild: `docker compose up -d --build`; switch it on on the *Plugins* page.

## Files

| File | Purpose |
|---|---|
| `plugin.py` | Server part. `GET = {"route": fn(query)}`, `POST = {"route": fn(body)}`, served at `/api/plugins/<name>/<route>` while the plugin is on. Return JSON-able data; raise `RuntimeError("message")` for an error (HTTP 500 with that message). |
| `static/*.js` | Browser part, loaded on page load. `window.watchdock.register({projectPage(project, view), settingsPage(stack)})`. |
| `static/*.css` | Styles, loaded on page load. |
| `README.md` | Documentation (the Plugins page points to it). |

## Rules

- Plugin code runs inside the app with full access: only install plugins you trust.
- Settings come from the *Plugins* page: `enabled().get("<name>", {})` (from `watchdock.plugins`).
- API requests get the same Host / Origin checks as the rest of the app; no extra auth is needed or possible.
