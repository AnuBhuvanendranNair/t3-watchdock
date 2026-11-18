"""Example plugin: skeleton to copy when writing a new plugin (does nothing useful).

Shows a small card on every project page with the project's name and the plugin's "greeting" setting.
Copy the folder to plugins/<your_name>/, rename the files and start from here; see README.md in this folder.

Settings on the Plugins page, e.g.: {"greeting": "Hello"}
"""
# A plugin is a normal Python module inside the app: it may import from watchdock.* (config, gitlab, t3monitor, …).
from watchdock.core import log
from watchdock.gitlab import find_project
from watchdock.plugins import enabled

NAME = "example"                                    # = folder name


def _settings():
    """This plugin's settings from the Plugins page ({} = defaults)."""
    return enabled().get(NAME, {})


def info(q):
    """GET /api/plugins/example/info?project=<id> -> JSON for the browser part (static/example.js)."""
    p = find_project(q["project"][0])              # q: query string as {key: [values]}; RuntimeError -> HTTP 500
    return {"project": p.get("name") or p["id"], "greeting": _settings().get("greeting", "Hello")}


def ping(body):
    """POST /api/plugins/example/ping with a JSON body -> JSON. POST routes change things; this one only logs."""
    log(f"Example plugin: ping from project {body.get('project', '?')}")      # shows up on the Activity page
    return {"ok": True}


# Routes: {"<route>": function}. Served at /api/plugins/<folder name>/<route>, only while the plugin is switched on.
GET = {"info": info}
POST = {"ping": ping}
