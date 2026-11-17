"""Gingco Patchday (Gingco Communication only): update history of a project for the Patchday protocol in OpenProject.

The Chrome extension in chrome-extension/ fetches GET data from the open T3 Watchdock tab and writes it into the
OpenProject page. Switched on and configured in config.json:

    "plugins": {"gingco_patchday": {"op": {"<project id>": "https://op.hub.gingco.de/projects/.../wiki/..."}}}
"""
import re

from watchdock.core import CONFIG, config, lock, log, save
from watchdock.gitlab import find_project
from watchdock.t3monitor import t3m_fetch, t3m_view

NAME = "gingco_patchday"
OP_URL = re.compile(r"https://[^\s/?#]+/\S*")


def _settings(cfg):
    s = (cfg.get("plugins") or {}).get(NAME)
    return s if isinstance(s, dict) else {}


def _links():
    return _settings(config()).get("op") or {}


def data(q):
    """Update history (production) grouped by day, newest first, in the format of the Patchday extension.
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
    return {"project": p["id"], "site": p.get("name") or p["id"], "op": _links().get(p["id"], ""),
            "groups": list(groups.values()), "cnt": len(seen),
            "tracked_since": v["history"][-1]["t"], "last_check": v["last_check"]}


def projects(q):
    """All projects with their OpenProject link ("" = none yet)."""
    links = _links()
    return [{"id": p["id"], "name": p.get("name") or p["id"], "op": links.get(p["id"], "")} for p in config()["projects"]]


def links(body):
    """Save OpenProject links: {"links": {"<project id>": "https://..." or ""}} ("" removes the link)."""
    new = body.get("links") or {}
    with lock:
        cfg = config()
        ids = {p["id"] for p in cfg["projects"]}
        st = cfg.setdefault("plugins", {}).setdefault(NAME, {})
        if not isinstance(st, dict):
            st = cfg["plugins"][NAME] = {}
        op = st.setdefault("op", {})
        for pid, url in new.items():
            url = (url or "").strip()
            if pid not in ids:
                raise RuntimeError(f"Unknown project: {pid}")
            if url and not OP_URL.fullmatch(url):
                raise RuntimeError(f"Not an https link: {url}")
            if url:
                op[pid] = url
            else:
                op.pop(pid, None)
        save(CONFIG, cfg)
    log(f"Patchday: OpenProject links saved ({len(new)})")
    return {"ok": True, "op": op}


GET = {"data": data, "projects": projects}
POST = {"links": links}
