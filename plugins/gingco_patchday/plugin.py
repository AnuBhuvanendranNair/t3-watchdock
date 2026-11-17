"""Gingco Patchday (Gingco Communication only): update history of a project for the Patchday protocol in OpenProject.

The Chrome extension in chrome-extension/ fetches these routes from the open T3 Watchdock tab and writes the data
into OpenProject; the OpenProject link per website is kept in the extension's options. The mapping key is the
production domain (host of the production t3monitor URL, lowercase, without "www."): the same in every T3 Watchdock
instance and stable when a project is re-created. Switched on in config.json:

    "plugins": {"gingco_patchday": {"button": true}}     # button: "Patchday" button on the project page
"""
import urllib.parse

from watchdock.core import config
from watchdock.gitlab import find_project
from watchdock.plugins import enabled
from watchdock.t3monitor import t3m_cfg, t3m_fetch, t3m_view


def domain(p):
    """Production domain of a project, e.g. "https://www.die-region.de/" -> "die-region.de" ("" if no URL)."""
    host = (urllib.parse.urlsplit((t3m_cfg(p, "production").get("url") or "").strip()).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _project(q):
    """Project by ?project=<id> or ?domain=<production domain>."""
    if q.get("domain"):
        d = q["domain"][0].strip().lower().removeprefix("www.")
        p = next((x for x in config()["projects"] if d and domain(x) == d), None)
        if not p:
            raise RuntimeError(f"No project with production domain {d} in T3 Watchdock")
        return p
    return find_project(q["project"][0])


def data(q):
    """Update history of the production instance, grouped by day, newest first, in the format of the extension.
    refresh=1 reads the site first, so updates made just now are included."""
    p = _project(q)
    if q.get("refresh", ["0"])[0] == "1":
        t3m_fetch(p, "production")                          # RuntimeError (site not reachable, ...) -> HTTP 500
    v = t3m_view(p["id"], "production")
    if not v["current"]:
        raise RuntimeError(f"No t3monitor data for {p.get('name') or p['id']} (production) yet")
    groups, seen = {}, set()
    for r in v["updates"]:                                  # newest day first
        d = r["t"][:10]
        it = {"key": r["key"], "name": r["title"] or r["key"], "o": r["old"] or "", "n": r["new"] or ""}
        if (d, it["key"], it["o"], it["n"]) in seen:
            continue
        seen.add((d, it["key"], it["o"], it["n"]))
        groups.setdefault(d, {"raw": ".".join(reversed(d.split("-"))), "d": d, "items": []})["items"].append(it)
    return {"project": p["id"], "domain": domain(p), "site": p.get("name") or p["id"], "groups": list(groups.values()), "cnt": len(seen),
            "tracked_since": v["history"][-1]["t"], "last_check": v["last_check"]}


def projects(q):
    """All projects (id, name, production domain), for the project list in the extension's options."""
    return [{"id": p["id"], "name": p.get("name") or p["id"], "domain": domain(p)} for p in config()["projects"]]


def settings(q):
    """Options of the plugin for the web UI."""
    return {"button": enabled().get("gingco_patchday", {}).get("button") is True}


GET = {"data": data, "projects": projects, "settings": settings}
