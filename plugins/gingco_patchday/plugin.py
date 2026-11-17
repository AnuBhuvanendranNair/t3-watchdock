"""Gingco Patchday (Gingco Communication only): update history of a project for the Patchday protocol in OpenProject.

The Chrome extension in chrome-extension/ fetches these routes from the open T3 Watchdock tab and writes the data
into OpenProject; the OpenProject link per project is kept in the extension's options. Switched on in config.json:

    "plugins": {"gingco_patchday": {"button": true}}     # button: "Patchday" button on the project page
"""
from watchdock.core import config
from watchdock.gitlab import find_project
from watchdock.plugins import enabled
from watchdock.t3monitor import t3m_fetch, t3m_view


def data(q):
    """Update history of the production instance, grouped by day, newest first, in the format of the extension.
    refresh=1 reads the site first, so updates made just now are included."""
    p = find_project(q["project"][0])
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
    return {"project": p["id"], "site": p.get("name") or p["id"], "groups": list(groups.values()), "cnt": len(seen),
            "tracked_since": v["history"][-1]["t"], "last_check": v["last_check"]}


def projects(q):
    """All projects (id, name), for the project list in the extension's options."""
    return [{"id": p["id"], "name": p.get("name") or p["id"]} for p in config()["projects"]]


def settings(q):
    """Options of the plugin for the web UI."""
    return {"button": enabled().get("gingco_patchday", {}).get("button") is True}


GET = {"data": data, "projects": projects, "settings": settings}
