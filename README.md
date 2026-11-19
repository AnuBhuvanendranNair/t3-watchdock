# T3 Watchdock

> **Repo renamed** (was `gitlab-launcher`). If you cloned the old name, migrate once:
> ```bash
> docker compose down                                                          # stop old 'gitlab-launcher' container (name changed)
> git remote set-url origin git@github.com:sivaprasad1988/t3-watchdock.git     # point at new repo name
> git pull                                                                     # latest main
> docker compose up -d --build                                                 # rebuild, container is now 't3-watchdock'
> ```
> Optional, cosmetic: `cd .. && mv gitlab-launcher t3-watchdock && cd t3-watchdock`.
> Your `config.json`, `state.json` and key files are local and gitignored — untouched by the rename. Since the database switch, the first start imports `config.json` and `state.json` into `watchdock.db` (see *Configuration*).

Small local web app to start GitLab pipelines, watch their jobs and play manual jobs — plus:

- a **TYPO3 release watcher** that starts the staging pipelines automatically when a new TYPO3 version is published,
- **notifications** in Microsoft Teams (or by email) before and after these automatic runs,
- **TYPO3 status per project** (version, extensions, status checks and their history) read via the t3monitor extension,
- a **Scheduler** page to set when the automatic checks run.

Python web app ([Flask](https://flask.palletsprojects.com), served by [Gunicorn](https://gunicorn.org); `requirements.txt`). Uses the `openssl` command for t3monitor (built into macOS and the Docker image). Runs on `127.0.0.1` only.

## Features

- **Login** — named user accounts, managed on the command line (`bin/t3-watchdock add-user NAME`); every page and API call needs a session (see *Login*)
- **Project list** — GitLab projects (path + branch) managed in the UI, stored in the SQLite database `watchdock.db`
- **Project form pre-fill** — new projects start with defaults (staging/production, `build:main`, TYPO3 13, `TARGET_TASK_NAME=shup01`); branch, production branch and TYPO3 major are select boxes; when GitLab is reachable, project path search plus name, branches, manual jobs (CI lint) and TYPO3 major are read from GitLab
- **Export / import projects** — *Settings → Export / import projects* writes all projects including their t3monitor keys and Basic auth passwords to one JSON file and reads such a file again (existing projects are skipped unless *Overwrite* is ticked). The GitLab token, Teams webhook URL and SMTP password are never exported
- **Run pipelines** — the project page has one card for staging and one for production, each with its own ▶ button (*Run staging*, *Run production*) and its latest pipeline; plus the "TYPO3 update" run (header icon), each with its own CI variables
- **Run all** — ▶ on the Projects page starts the normal (non-production) pipeline of every project with CI/CD at once (one confirmation, failures reported per project)
- **Projects without CI/CD** — untick *Uses GitLab CI/CD* in the project form: no pipelines, no TYPO3 auto-update, no *Run all*; the project page shows only the TYPO3 status (t3monitor). Path and branch are optional; with a branch, extension update messages contain ready-to-run commands, without one they only list the updates
- **Production pipelines** — started directly from the production card, independent of staging (see below)
- **Pipeline progress** — one step per stage (✓ done, spinner running, ✕ failed, ▶ manual job waiting — click ▶ to play it); the job table is in the collapsible *Job details* (opens by itself when a job failed)
- **Auto-play** — listed manual jobs (e.g. `build:main`) are started automatically once they become playable (polled every 15 s, max. 2 h)
- **TYPO3 watcher** — checks `get.typo3.org` for the latest release of a major version on the schedule set in *Scheduler*; on a new version it announces the update in Teams, then triggers the pipeline of every project with `auto_typo3.enabled` (plus a macOS notification when not running in Docker)
  - First check only stores a baseline, it does not trigger
  - Failed triggers are retried on the next check
- **Notifications (Microsoft Teams, email)** — when a pipeline started by the TYPO3 watcher has finished (success, failed, canceled, skipped), a Teams message and/or email with status and link is sent; also when the auto-trigger could not start the pipeline. The t3monitor check sends a summary per scheduled run and alerts on new findings (see below). Set up in *Settings*
- **TYPO3 status (t3monitor)** — reads TYPO3 version, extensions and status checks from sites with the [t3monitor](https://github.com/BrainAppeal/t3monitor) extension, plus server info (PHP, database, web server, OS kernel without hostname), for the production and (optionally) the staging instance of a project; shown on the project page with a change history (see below)
- **Extension updates & changelogs** — newest compatible release per extension from Packagist (major updates marked separately); click an extension row to read the changelog of that release
- **Projects page** — switch between *grid* (project cards) and *list* (TYPO3 overview table), remembered per browser. A card shows the GitLab avatar, name, monitoring pills per environment (*Key missing* when no key is saved) and the latest CI/CD run with its status. Same layout in every style; the style only changes colours and fonts. Filter icon opens tabs per technology (TYPO3, PHP, Database, Web server, OS) with one chip per version and its project count (*All* = no filter; TYPO3 by major, shown as `v13`, the rest by product + major.minor; a project matches if production or staging matches); refresh icon re-checks the TYPO3 status of every monitored site (4 at a time)
- **Refresh progress** — every refresh icon fills from bottom to top while it works (finished sites plus an estimate for the ones in flight)
- **TYPO3 overview on the home page** — table (list view) with row numbers and a sort select (project order, name, newest check); per project and environment the TYPO3 version (↑ = update available), PHP / database / web server versions and icon chips with counts: errors (circle), warnings (triangle), security advisories (shield), PHP version check (clock), *OK* when there is nothing to report (tooltip = full text); *versions differ* / *PHP differs* markers and the oldest last check; data from the last t3monitor check
- **PHP version & security advisories** — scheduled check of every instance: PHP version against [endoflife.date](https://endoflife.date/php) (*end of life*, *security fixes only*, newer patch release available) and TYPO3 core (`typo3/cms-core`) plus public extensions against the [Packagist security advisories](https://packagist.org/apidoc#list-security-advisories) (FriendsOfPHP, GitHub). Uses the data of the last t3monitor check (no extra request to the sites). Results: *Security* section on the project page, shield / clock chips in the overview; Teams/email message only for findings not reported before
- **Scheduler** — page to set when the TYPO3 release check, the t3monitor check and the security check run: every N hours or daily at a fixed time on chosen weekdays; shows last run, result and next run, with *Run now*
- **Run history & log** — kept in the SQLite database `watchdock.db` (all runs, newest 10 000 log entries)
- **Plugins page** — nav bar, after *Settings*: one row per plugin in `plugins/` with name and On/Off; click to open the description, the on/off switch and the plugin's settings (JSON). See *Plugins*
- **Save & close** — Scheduler and Settings forms have *Save* (stay on the page) and *Save & close* (back to Projects)
- **Flash messages** — results and errors appear top right (green ✓ / red ⚠; 6 s, errors 12 s; click to close)
- **Icon buttons** — actions are icons with a tooltip (also the accessible name); icon set: [Lucide](https://lucide.dev), see *Icons*
- **Dark / light theme** — switch in the header: monitor icon *Auto* (follows the system setting) → sun *Light* → moon *Dark*; the choice is saved in the browser (`localStorage`) and applied before the page is drawn
- **Focus style** — choose *Focus* in the header style selector for a quieter look with less repeated copy (its projects page layout is now the layout of every style). It follows the Auto, Light, or Dark setting and is saved per browser.
- **Terminal style** — monospace font everywhere (system SF Mono/Menlo, no web fonts), square corners, outlined buttons, `$ ~/t3 watchdock` prompt with blinking cursor, `#`/`##` heading prefixes and `./` nav links; project cards of equal height with the CI/CD line at the bottom, environments as `PRD` / `STG`, a waiting manual job as an info icon with the message in a tooltip (hover, focus or click); *Dark* = phosphor green on black, *Light* = paper terminal; saved per browser
- **Turbo C++ style** — classic DOS IDE look in the 16-colour CGA palette — grey menu bar with red hotkey letters and green selection, windows with double borders and centered titles, green buttons with shadow, cyan input fields; *Dark* = blue editor screen, *Light* = grey dialog look

## Requirements

- Python 3 with the packages from `requirements.txt` (Flask, Gunicorn; installed in the Docker image automatically)
- `openssl` command (for t3monitor; present on macOS and in the Docker image)
- GitLab personal access token with `api` scope
- Docker (recommended) — or run directly with Python
- macOS for notifications (only when not running in Docker)

## Quick start

```bash
git clone git@github.com:sivaprasad1988/t3-watchdock.git
cd t3-watchdock
cp config.example.json config.json   # optional — imported into watchdock.db on first start; projects can also be added in the UI
# once: key that encrypts the GitLab tokens, outside the data folder (Docker reads it as a secret, see "GitLab tokens")
python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())" > ~/.t3-watchdock-secret-key && chmod 600 ~/.t3-watchdock-secret-key
docker compose up -d --build         # runs permanently, see "Run with Docker"
```

Create a login first (without an account nobody can sign in):

```bash
bin/t3-watchdock add-user NAME                                # asks for the password twice
docker compose exec launcher bin/t3-watchdock add-user NAME   # same in Docker
```

Open <http://127.0.0.1:8787>, sign in, save your GitLab token in *Profile → GitLab token*, add projects. For the scheduler and TYPO3 watcher, an admin (`bin/t3-watchdock set-admin NAME on`) saves a service token in *Settings → GitLab service token*.

Without Docker (runs only while the terminal is open):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # once
.venv/bin/python app.py               # with TYPO3 watcher (Gunicorn on http://127.0.0.1:8787)
.venv/bin/python app.py --no-watch    # TYPO3 release check paused (Scheduler)
```

`config …` and the account commands need no packages; plain `python3 app.py config get` works without the venv.

### App server (Gunicorn)

`app.py` (and `bin/t3-watchdock start`) replaces itself with Gunicorn, settings in `gunicorn.conf.py`:

- **Exactly one worker** (`workers = 1`), several threads (`threads`, default 16, env `WATCHDOCK_THREADS`). The scheduler and the pipeline mail watches run as threads inside the worker; a second worker would trigger every pipeline and notification twice. Do not raise `workers`.
- Worker timeout 300 s, graceful stop 10 s (`docker compose stop` / Ctrl+C).
- Request size max. 10 MB in the app as well (`413`).
- No access log (as before); errors go to stderr, app events to the Activity log.

## Login

Every page and every API call needs a signed-in session; without one, pages redirect to `/login` and API calls answer `401`. Accounts are created only on the command line, never in the browser.

```bash
bin/t3-watchdock add-user NAME        # new account, asks for the password twice
bin/t3-watchdock set-password NAME    # new password, signs the user out everywhere
bin/t3-watchdock remove-user NAME     # delete account and its sessions
bin/t3-watchdock unlock-user NAME     # unlock after 3 failed logins
bin/t3-watchdock list-users           # names, creation dates, admins, own GitLab token, locked accounts
bin/t3-watchdock set-admin NAME on    # admins manage the GitLab service token (off: set-admin NAME off)
bin/t3-watchdock gen-secret-key       # print a new key for WATCHDOCK_SECRET_KEY
```

- **`bin/t3-watchdock`** without a command lists all commands. `bin/t3-watchdock start [--no-watch]` starts the app (same as `python3 app.py`); `config …` and the account commands work as with `app.py`. Works from any directory and through a symlink. When T3 Watchdock is installed with Composer, it is available as `vendor/bin/t3-watchdock` (needs `"bin": ["bin/t3-watchdock"]` in a `composer.json`; this repository has none yet).
- **Docker:** `docker compose exec launcher bin/t3-watchdock add-user NAME`.
- **Names:** 1–64 characters, letters, digits and `. _ @ -`. **Passwords:** at least 12 characters.
- **Sessions:** 12 hours from sign-in (no extension on activity). *Sign out NAME* in the header ends the session.
- **Account lock:** 3 failed logins in a row lock the account; also the correct password is then refused. Only `unlock-user NAME` or `set-password NAME` on the command line unlock it. A successful login resets the count. Lock and unlock are written to the log.
- **Failed logins per address:** 5 failures per client address (any name) within 15 minutes block that address for the rest of the window (in memory, reset on restart). Behind a reverse proxy all requests come from the proxy address, so the limit then applies to everyone together.
- **Profile** (user icon in the header, `#/profile`): full name and email (optional, stored with the account; login name read-only), and change your own password in the browser. Needs the current password; your other sessions are signed out, the current one stays. A wrong current password counts as a failed login (3 lock the account).
- A locked account is also signed out everywhere.
- Logins and logouts are written to the log (*Activity*) with the user name.
- **After updating** an existing instance: the database gets the `users` and `sessions` tables automatically on start, but no account. Run `add-user` once, otherwise nobody can sign in (also not the Patchday browser extension, which uses the signed-in Watchdock tab).

## Configuration

Projects and settings are stored in the SQLite database `watchdock.db` (gitignored, mode `600`). The layout is the same as the former `config.json` (see `config.example.json`):

- **First start:** an existing `config.json` (and `state.json`) is imported once and renamed to `config.json.imported-<time>` (backup). Editing `config.json` after that has no effect.
- **Projects:** add and edit them in the UI; move them between instances with *Export* / *Import* on the projects page (JSON file, includes keys and passwords).
- **Settings without a UI** (`port`, `plugins`, `t3monitor_local_vendors`, …): command line, also while the app runs:

```bash
python3 app.py config get                     # all settings
python3 app.py config set plugins '{"gingco_patchday": {}}'
python3 app.py config unset plugins
docker compose exec launcher python app.py config get    # same in Docker
```


| Key | Description |
|---|---|
| `port` | HTTP port (default `8787`) |
| `scheduler.<task>` | Schedule per task (`typo3_release`, `t3monitor`): `enabled`, `mode` (`interval`/`daily`), `hours`, `time` (`HH:MM`), `days` (0 = Mon … 6 = Sun); set in the *Scheduler* page |
| `check_interval_hours` | Old setting: default interval of the TYPO3 release check until a schedule is saved |
| `projects[].id` | Stable ID, generated from `path` + `ref` |
| `projects[].name` | Display name |
| `projects[].gitlab_url` | GitLab base URL |
| `projects[].ci` | `false` = project without GitLab CI/CD (monitoring only); missing = `true` |
| `projects[].path` | Project path, e.g. `group/project` (optional when `ci` is `false`) |
| `projects[].ref` | Branch to run the pipeline on (optional when `ci` is `false`; used for update commands) |
| `projects[].variables` | CI variables for a normal run |
| `projects[].auto_play` | Manual jobs to auto-play after a normal run |
| `projects[].auto_typo3.enabled` | Enable TYPO3 auto-trigger for this project |
| `projects[].auto_typo3.major` | TYPO3 major version to watch, e.g. `13` |
| `projects[].auto_typo3.variables` | CI variables for a TYPO3 update run |
| `projects[].auto_typo3.auto_play` | Manual jobs to auto-play after a TYPO3 update run |
| `projects[].production.ref` | Production branch; empty = no production card |
| `projects[].production.variables` | CI variables for the production run |
| `projects[].production.auto_play` | Manual jobs to auto-play after the production run |
| `projects[].t3monitor.url` | Site URL with the t3monitor extension; key is stored in `<project-id>.t3monitor-key` |
| `projects[].t3monitor.auth_user` | HTTP Basic auth user for password-protected sites (empty = none); password in `<project-id>.t3monitor-auth` |
| `projects[].t3monitor_staging.url` / `.auth_user` | Same for the staging instance; key in `<project-id>.t3monitor-staging-key`, password in `<project-id>.t3monitor-staging-auth` |
| `teams.enabled` | Send Teams messages for TYPO3 auto-trigger runs; webhook URL is stored in `.teams-webhook` |
| `t3monitor_interval_hours` | Old setting: default interval of the t3monitor check until a schedule is saved |
| `t3monitor_local_vendors` | Composer vendors of own extensions, hidden and not tracked in history (default `["gingco"]`; `dev-*` versions also count as local) |
| `email.enabled` | Send email notifications for TYPO3 auto-trigger runs |
| `email.host` / `email.port` / `email.security` | SMTP server; security `starttls`, `ssl` or `none` |
| `email.user` | SMTP login (empty = no login); password is stored in `.smtp-password` |
| `email.from` / `email.to` | Sender and list of recipients |
| `plugins.<name>` | Switch on a plugin from `plugins/<name>/` and hold its settings (`false` or `{"enabled": false}` = off); see *Plugins* |

Changing a project's TYPO3 major resets its baseline (no immediate trigger).

## Scheduler

Page *Scheduler* (top menu) lists the automatic tasks:

| Task | Does |
|---|---|
| TYPO3 release check | Checks `get.typo3.org`; on a new release: Teams announcement, then the update pipelines on staging |
| t3monitor check (TYPO3 & extensions) | Reads TYPO3 version, extensions and status checks of every instance (production, staging) with t3monitor URL and key |
| PHP version & security advisories | For every instance with t3monitor data: PHP version against support dates (end of life, newer patch release), TYPO3 core and public extensions against known security advisories; one message per run, only for new findings |
| TYPO3 security announcements | Reads the TYPO3 security feed (`news.typo3.com/security/rss-security`): core and extension advisories and public service announcements (e.g. security release pre-announcements). The first run stores the current entries; afterwards one message per run for new entries. The latest entries are listed on the *Activity* page |

- Per task: on/off, *Every N hours* (0.25–168) or *Daily at a fixed time* on chosen weekdays; shows last run, result and next run; **▶ Run now**.
- Tasks run only while the launcher runs (checked every 30 s). A run missed while it was off starts right after the next start.
- Default until a schedule is saved: every 6 h (or the old `check_interval_hours` / `t3monitor_interval_hours`); PHP version & security advisories: daily at 07:00; TYPO3 security announcements: every 3 h.
- `python3 app.py --no-watch` pauses the TYPO3 release check (shown as *paused*).

## TYPO3 status (t3monitor)

1. In the TYPO3 site: *Admin Tools → Settings → Extension Configuration → t3monitor → encryption_key* (64 characters).
2. In the launcher: project → **Edit** → *t3monitor – Production* and/or *t3monitor – Staging*: site URL and key → **Save changes**. Or use the pencil on the *Production* / *Staging* tile of the project page: a modal with the same fields for that instance only (saves only that instance). Each instance has its own key (the staging site has its own `encryption_key`).
3. The project page shows a *System overview* tile per instance (TYPO3, PHP, database, web server, error/warning badges, last check) with three icons: refresh (this instance now), pencil (monitoring settings of this instance) and expand. The expand icon (or a badge) opens the **TYPO3 status** modal: site, environment, check time and schedule; a banner (*N errors and M warnings need attention* / *All checks passing*, with *Review problems*); TYPO3, Security, Extensions, *Unchanged since*; server chips; and the expandable rows *Problems*, *Security* (only with findings), *All status checks*, *Extensions*, *Update history* and *Change history*. The refresh icon in the modal fetches that instance immediately, the one in the page header both instances; otherwise on the schedule of the *t3monitor check* task in *Scheduler*.
4. The home page shows all projects in one table (production and staging side by side).

- Request: `?t3monitor=1&secret=<first 32 chars of the key>&reports=internal,security,installed_extensions,system`; the answer is AES-encrypted with the last 32 chars (never sent), decrypted with `openssl`.
- Only technical data is stored (version, extensions, status checks) — no backend users or paths.
- **Extension updates:** for every public extension the newest stable release on [Packagist](https://packagist.org) whose `typo3/cms-core` requirement fits the site's TYPO3 version is looked up (column *Latest*). Rows with an update are tinted; major updates (e.g. 7.x → 8.0, may contain breaking changes) get an amber tint and a *major* chip. Counts appear in the section header and the *Extensions* box. Local extensions are skipped; packages not on Packagist show *not on Packagist*. Package lists are cached for 1 h; if Packagist is unreachable the t3monitor check still succeeds (*unknown*).
- **Changelog:** click an extension row to show the changelog of the latest version (when an update is available) or of the installed version. Sources in this order: GitHub/GitLab release notes of the tag, then the changelog file at the tag (`CHANGELOG.md`, `ChangeLog`, … — the section of that version, or the per-version file it links to). Links to the source, the full compare view (installed → latest) and the repository. Only packages hosted on github.com or gitlab.com; results are cached until restart.
- History in `t3monitor/<project-id>.json` (production) and `t3monitor/staging/<project-id>.json` (staging): a new entry only when something changes (TYPO3 version, extension added/removed/updated, status severity); otherwise "seen until" is updated. Last 300 changes are kept.
- Key file: mode `600`, removed with the project. The edit form can reveal an individual saved key on demand over same-origin HTTPS or localhost.
- Password-protected site (HTTP Basic auth): set *Basic auth user* and *password* in the project's t3monitor settings. The user is stored in the database, the password in `<project-id>.t3monitor-auth` (mode `600`, never sent to the browser). Empty user = no basic auth.

## Notifications (Microsoft Teams, email)

Microsoft Teams (no mail server needed):

1. In Teams, open the channel → **⋯ → Workflows** → template **"Send webhook alerts to a channel"** (older name: "Post to a channel when a webhook request is received") → select team and channel → copy the webhook URL shown at the end.
2. *Settings → Microsoft Teams notifications*: paste the URL, tick *Send Teams messages*, **Save & send test message**.
3. To get a Teams alert for each message: channel → **⋯ → Channel notifications → Custom → All new posts: Banner and feed**.

Anyone who has the webhook URL can post into the channel — treat it like a password (never paste it into chats or tickets).

Email (optional, needs SMTP access): *Settings → Email notifications*: SMTP host, port, security, optional user/password, sender, recipients, tick *Send email notifications*, **Save & send test email**.

- Before the staging pipelines of a new TYPO3 release start, one message "New TYPO3 x released: starting update on staging" lists all affected projects (sent once per project and version, not again on retries).
- Only pipelines started automatically by the TYPO3 watcher are watched (not manual runs, Run all or production runs).
- **t3monitor check, scheduled run** (also *Run now* in Scheduler): **one summary message per run** with every site (production and staging): TYPO3 version, errors, warnings, extension updates (`NEW` = first time reported, `MAJOR` = may contain breaking changes), new errors, and sites whose check failed.
- **t3monitor, refresh icon** on a project (modal, page header or Projects page): a message only when something is new for that site — the check failed (once per new error text), new errors appeared (the first check of a site is the baseline), or a new extension update was found. Each extension version is reported as new only once.
- Teams Workflow webhooks answer *accepted* (HTTP 202) before the message is posted. If the test message is accepted but does not appear, open the run history of the Workflow in Teams (**Workflows → the flow → Run history**) to see why it failed.
- The pipeline status is polled every 60 s; the message is sent once it has finished. After 24 h without a final status a "NOT FINISHED" message is sent.
- If the pipeline could not be started, a "NOT STARTED" message is sent (on every failed retry).
- Pending pipelines are kept in the database (`watchdock.db`) and watched again after a restart.
- Webhook URL (`.teams-webhook`) and SMTP password (`.smtp-password`) are stored with file mode `600` and never sent to the browser; leave the field empty to keep the stored value.
- Send errors are written to the Activity log.

## Production pipelines

1. Run the staging pipeline (▶ on the *Staging* card, or ▶ *Run all*) and check the result.
2. Merge `staging` into the production branch **in GitLab** — the launcher does not merge.
3. Click ▶ on the *Production* card (red) and confirm. A pipeline starts on the production branch with the production variables and auto-play jobs (API: `POST /api/run` with `"mode": "production"`).

Staging and production run independently: the launcher no longer requires a successful staging pipeline first, the confirmation dialog is the only safeguard. Runs started by the former *Promote to production* still show in *Recent runs* (as *from #…*, tagged `PROD`).

In the project form, the production branch is pre-filled from GitLab (`production` if it exists, otherwise the default branch) and the production auto-play jobs mirror the staging ones until edited. Run all and the TYPO3 auto-trigger never touch production.

## GitLab tokens

- **Personal token** — every user saves their own in *Profile → GitLab token*. Pipelines and jobs started in the browser (run, promote, production, play, auto-play of manual jobs) use it, so GitLab shows who started what. Without one, these actions are refused; read-only views fall back to the service token.
- **Service token** — one for the app, saved by an admin in *Settings → GitLab service token*. Used when no user is signed in: scheduler, TYPO3 watcher, pipeline mail watches. Prefer a project or group access token limited to the needed projects, with an expiry date (`api` scope is needed to play manual jobs).
- Both are stored encrypted (Fernet, package `cryptography`) in `watchdock.db`, read server-side only, never sent to the browser or exported. They can be tested and removed in the UI.
- **Key** — kept outside the data folder, so a copy of the database alone does not reveal the tokens. First match wins: `WATCHDOCK_SECRET_KEY` (the key), `WATCHDOCK_SECRET_KEY_FILE` (path to it; Docker uses this with the secret `~/.t3-watchdock-secret-key` from the host, see `compose.yaml`), else `~/.t3-watchdock-secret-key` (created on first local start, mode `600`). A lost or changed key makes the stored tokens unreadable: save them again. Back up the key separately from the database.
- **Upgrade** — on first start, an existing `.gitlab-token` in the app folder is imported as the encrypted service token and the plaintext file is deleted. `~/.gitlab-token` is imported if no service token exists yet, but left in place (delete it yourself).
- **Docker upgrade** — create `~/.t3-watchdock-secret-key` first (command in *Quick start*) — the container reads it as a Docker secret.

## Run with Docker (always on)

The container restarts automatically (`restart: unless-stopped`), also after a reboot as long as Docker Desktop starts at login (*Docker Desktop → Settings → General → Start Docker Desktop when you sign in*).

```bash
docker compose up -d --build
```

Two containers:

- **`t3-watchdock-proxy`** ([Traefik](https://traefik.io) `v3.7.13`, own container, separate from other projects' Traefik): the only part with published ports. HTTPS, timeouts, request size limit, rate limit, security headers. Routes are in `traefik/dynamic.yml` (file provider, no Docker socket).
- **`t3-watchdock`** (the app): no published port, reachable only through the proxy on the internal network `backend`.

Open <http://127.0.0.1:8787>. All data — `watchdock.db`, `t3monitor/` and the secret files (`.teams-webhook`, `.smtp-password`, `*.t3monitor-key`, `*.t3monitor-auth`, `*.t3monitor-staging-key`, `*.t3monitor-staging-auth`) — is read from and written to this folder (mounted as `/data`), so it survives rebuilds.

| Task | Command |
|---|---|
| Update after code changes (`watchdock/` or `static/`) | `docker compose up -d --build` |
| Logs | `docker compose logs -f` |
| Restart | `docker compose restart` |
| Stop | `docker compose down` |

### Local hostname with HTTPS (optional)

Serve the app at <https://local-gitlabrunner.local> with a trusted [mkcert](https://github.com/FiloSottile/mkcert) certificate:

```bash
brew install mkcert && mkcert -install          # once: local CA (asks for password)
mkdir -p certs
mkcert -cert-file certs/local-gitlabrunner.local.pem \
       -key-file certs/local-gitlabrunner.local-key.pem local-gitlabrunner.local
echo "127.0.0.1 local-gitlabrunner.local" | sudo tee -a /etc/hosts
echo "::1 local-gitlabrunner.local" | sudo tee -a /etc/hosts   # avoids 5 s .local lookup delay
docker compose up -d --build
```

- Traefik serves HTTPS with the certificate from `certs/` (configured in `traefik/dynamic.yml`); http://local-gitlabrunner.local redirects to https, http://127.0.0.1:8787 stays plain HTTP as fallback
- `certs/` is gitignored; the certificate is valid for ~2 years, re-run the `mkcert` command to renew
- Without the certificate files Traefik uses its own self-signed certificate (browser warning); http://127.0.0.1:8787 keeps working
- Firefox may need `mkcert -install` again (own certificate store)

### Reverse proxy (Traefik)

| Setting | Value | Where |
|---|---|---|
| Entry points | `:8787` (plain, `127.0.0.1` / `localhost`), `:80` (redirect), `:443` (HTTPS) | `compose.yaml` |
| Timeouts | read 30 s, write 300 s (long GitLab / t3monitor calls), idle 180 s | `compose.yaml` |
| Request size | max. 10 MB (larger: `413`) | `traefik/dynamic.yml` |
| Rate limit | 50 requests/s per client address, burst 100 (more: `429`) | `traefik/dynamic.yml` |
| Headers | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`; header names with `_` / `.` aliases are dropped | both |

- The app runs with `LAUNCHER_BEHIND_PROXY=1`: it takes HTTPS and the client address from `X-Forwarded-Proto` / `X-Forwarded-For` (set by Traefik, which overwrites values sent by clients). The failed-login limit then counts the real client address, and session cookies get `Secure` on HTTPS. Never set it when the app port is reachable without the proxy.
- Traefik reloads `traefik/dynamic.yml` on change; changes in `compose.yaml` need `docker compose up -d`.
- New hostname: add it to the `Host(...)` rules in `traefik/dynamic.yml`, to `LAUNCHER_ALLOWED_HOSTS` in `compose.yaml`, and a certificate under `tls.certificates`.

Notes:
- Ports are published on `127.0.0.1` only (proxy). The host port `8787` must match the `port` setting (default `8787`, `python app.py config get port`), otherwise the Host header check rejects requests.
- Stop any copy of `app.py` running in a terminal first (same port).
- macOS notifications (TYPO3 auto-trigger) do not work inside the container; use Teams notifications or the Activity log instead.
- HTTPS is done by Traefik only; the app itself serves plain HTTP (the former `LAUNCHER_TLS_*` settings are gone).
- Environment: `LAUNCHER_DATA` (data folder, default: app folder), `LAUNCHER_HOST` (bind address, default `127.0.0.1`), `LAUNCHER_ALLOWED_HOSTS` (extra accepted hostnames, comma-separated), `LAUNCHER_BEHIND_PROXY` (`1` = trust `X-Forwarded-*`, see above).

## Icons

The UI uses [Lucide](https://lucide.dev) icons (ISC licence, copy in `static/icons-LICENSE.txt`), version **lucide-static 1.66.0**. There is no build step and no CDN: the icons used are copied as `<symbol id="i-<name>">` into one inline SVG sprite at the top of `static/index.html`.

| Name in the app | Lucide icon | Used for |
|---|---|---|
| `refresh` | `refresh-cw` | Refresh status |
| `play` | `play` | Run pipeline, play manual job |
| `update` | `circle-arrow-up` | Run TYPO3 update |
| `send` | `send` | Send update commands |
| `edit` | `pencil` | Edit project, edit monitoring settings of an instance |
| `patchday` | `calendar-check` | Patchday plugin |
| `ext` | `external-link` | External links |
| `details`, `close` | `maximize-2`, `x` | Open / close the status modal |
| `info` | `info` | Waiting manual job on a project card (Terminal style) |
| `shield`, `clock` | `shield-alert`, `clock` | Security advisories / PHP check chips in the TYPO3 overview |
| `err`, `warn`, `ok` | `circle-alert`, `triangle-alert`, `circle-check` | Error / warning badges |
| `grid`, `list`, `filter`, `plus` | `layout-grid`, `list`, `list-filter`, `plus` | Projects page |
| `chev` | `chevron-down` | Expandable rows in the status modal |
| `auto`, `sun`, `moon` | `monitor`, `sun`, `moon` | Theme switch |
| `logout` | `log-out` | Sign out (tooltip shows the signed-in name) |
| `palette` | `palette` | Style selector in the header |
| `user` | `user` | Profile page (change own password) |

Use in `static/app.js`: `ic("refresh")` returns the `<svg>`, `icBtn("refresh", "Tooltip text", 'data-act="…"')` an icon-only button (tooltip = accessible name). Plugins get the same helper as `watchdock.ic`.

Add an icon:

1. Find it on [lucide.dev/icons](https://lucide.dev/icons), e.g. [lucide.dev/icons/refresh-cw](https://lucide.dev/icons/refresh-cw).
2. Open the SVG of the pinned version, e.g. `https://unpkg.com/lucide-static@1.66.0/icons/refresh-cw.svg`.
3. Copy the elements inside `<svg>…</svg>` into a new `<symbol id="i-<name>" viewBox="0 0 24 24">…</symbol>` in the sprite. Stroke, width and caps come from the `.ic` class in `style.css`.
4. Use it with `ic("<name>")`. When updating the Lucide version, change the version in the sprite comment and here.

## Plugins

Optional, team-specific features live in `plugins/<name>/` and stay off until switched on on the **Plugins** page (nav bar, after *Settings*): it lists every plugin in `plugins/`, with an on/off switch and its settings as JSON. Saving reloads the page.

To add a plugin: copy its folder to `plugins/<name>/` (to write one, start from `plugins/example/`), rebuild (`docker compose up -d --build`), switch it on on the Plugins page. Plugins are Python code running inside the app, so there is no upload in the browser.

On the command line (same setting): `python3 app.py config set plugins '{"gingco_patchday": {}}'` (replaces the whole list).

A plugin is a folder with

- `plugin.py` — `GET = {"route": fn(query)}` and `POST = {"route": fn(body)}`, served at `/api/plugins/<name>/<route>` (same Host / Origin checks as the rest of the API)
- `static/*.js`, `static/*.css` — loaded by the web UI; a script calls `watchdock.register({projectPage(project, view), settingsPage(stack)})` to add to the project and settings pages

Switched off (or missing) plugins answer `404` and load nothing. Settings are read on every request: after switching a plugin on or off, reload the browser page. Docker copies `plugins/` into the image, so rebuild once after updating the code (`docker compose up -d --build`); Chrome extensions (`plugins/*/chrome-extension`) are not copied.

| Plugin | Purpose |
|---|---|
| [`example`](plugins/example/README.md) | Skeleton to copy for a new plugin: server routes, browser part, settings (off by default) |
| [`gingco_patchday`](plugins/gingco_patchday/README.md) | Gingco Communication only: provides the production update history to the Patchday Chrome extension, which writes it into the Patchday protocol in OpenProject |

## Security

- Binds to `127.0.0.1` only (Docker: only the Traefik proxy is published, on `127.0.0.1`; the app container has no published port)
- Traefik in front: HTTPS, timeouts, 10 MB request limit, rate limit per client address, security headers (see *Reverse proxy*)
- Login required for every page and API call. Passwords hashed with `scrypt` (random salt per user); the session cookie is a random token (`HttpOnly`, `SameSite=Strict`, `Secure` on HTTPS) and the database stores only its SHA-256 hash. Failed logins are rate limited; an unknown name takes as long to check as a wrong password
- Optional HTTPS with a local mkcert certificate
- `Host` header check against DNS rebinding
- `Origin` check and `application/json` requirement on POST against cross-site requests
- GitLab tokens are stored encrypted in the database, the key outside the data folder (see *GitLab tokens*). Other secrets (Teams webhook URL, SMTP password, t3monitor keys and Basic auth passwords) are stored in separate files with mode `600`. Only t3monitor keys can be revealed from the project edit form; the project export file contains t3monitor keys and Basic auth passwords in plain text. Both work only on a same-origin HTTPS or localhost request
- Token, secrets, config, state, t3monitor history and logs are gitignored
- Outgoing connections: GitLab (only to the GitLab URLs of configured projects), `get.typo3.org`, `news.typo3.com` (security feed), the Teams webhook / SMTP server if enabled, the t3monitor site URLs, `repo.packagist.org` (only public Composer package names are sent), and — when a changelog is opened — `api.github.com`, `raw.githubusercontent.com` or `gitlab.com` (public repository paths and tags only)

## Files

| File | Purpose |
|---|---|
| `app.py` | Entry point (starts `watchdock.server.main`; `config …` and account commands) |
| `bin/t3-watchdock` | Command line wrapper for `app.py` (works from any directory, `vendor/bin` symlink) |
| `watchdock/auth.py` | Login: password hashing, accounts, sessions, failed-login limit |
| `watchdock/core.py` | Paths, settings, shared state, JSON storage |
| `watchdock/db.py` | SQLite storage: projects, settings, runs, log, scheduler results, TYPO3 baselines, pending notifications, users, sessions |
| `watchdock/alerts.py` | E-mail and Microsoft Teams notifications |
| `watchdock/gitlab.py` | GitLab API: tokens (per user + service token), pipelines, manual jobs, project lookup |
| `watchdock/crypto.py` | Encryption of the stored GitLab tokens (key outside the data folder) |
| `watchdock/extensions.py` | Extension update check (Packagist) and changelogs |
| `watchdock/t3monitor.py` | t3monitor client, history, change detection |
| `watchdock/watcher.py` | TYPO3 release watcher, pipeline result mails |
| `watchdock/projects.py` | Create / update project entries, export / import |
| `watchdock/scheduler.py` | Background scheduler |
| `watchdock/server.py` | Flask app: API routes, Host / Origin checks, login check |
| `gunicorn.conf.py` | Gunicorn settings (1 worker, threads, timeouts; starts the scheduler in the worker) |
| `requirements.txt` | Python packages (Flask, Gunicorn, cryptography), pinned |
| `watchdock/plugins.py` | Plugin loader (routes and browser files of enabled plugins) |
| `static/` | Web UI (`index.html` with the icon sprite, `login.html`, `style.css`, `app.js`, `icons-LICENSE.txt`) |
| `plugins/` | Optional plugins, off by default (see *Plugins*) |
| `config.example.json` | Example configuration (copy to `config.json` before the first start to import it) |
| `Dockerfile`, `compose.yaml` | Docker setup (app + Traefik proxy) |
| `traefik/dynamic.yml` | Traefik routes, middlewares (limits, headers) and TLS certificate |
| `certs/` | mkcert certificate + key (gitignored) |
| `watchdock.db` | SQLite database (stdlib `sqlite3`, mode `600`): projects, settings, runs, log, TYPO3 baselines, scheduler results, pending notifications, user accounts (password hashes, admin flag, encrypted GitLab tokens), encrypted service token and sessions (gitignored). On first start an existing `config.json` / `state.json` is imported and renamed to `<name>.imported-<time>` (backup) |
| `.gitlab-token` | Legacy plaintext GitLab token: imported encrypted on start, then deleted (gitignored) |
| `.smtp-password` | SMTP password (gitignored) |
| `.teams-webhook` | Teams webhook URL (gitignored) |
| `*.t3monitor-key` | t3monitor key per project (gitignored) |
| `*.t3monitor-auth` | Basic auth password per project for t3monitor (gitignored) |
| `*.t3monitor-staging-key`, `*.t3monitor-staging-auth` | Same for the staging instance (gitignored) |
| `t3monitor/` | t3monitor history per project (gitignored) |
