"""Optional plugins: plugins/<name>/plugin.py, switched on in config.json.

    "plugins": {"<name>": {...settings of the plugin...}}     # false or {"enabled": false} = off

A plugin module may define
    GET  = {"route": fn(query dict) -> JSON}     served at GET  /api/plugins/<name>/<route>
    POST = {"route": fn(body dict)  -> JSON}     served at POST /api/plugins/<name>/<route>
and ship browser files in plugins/<name>/static/ (*.js, *.css), loaded by the web UI.
"""
import importlib
import re

from .core import BASE, config

PLUGIN_DIR = BASE / "plugins"
NAME = re.compile(r"[a-z][a-z0-9_]{0,40}")
FILE = re.compile(r"[A-Za-z0-9_-]+\.(js|css)")
CTYPES = {"js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8"}
_mods = {}


class NotFound(Exception):
    """Plugin, route or file does not exist (HTTP 404)."""


def enabled():
    """{name: settings} of the plugins switched on in config.json that exist on disk."""
    out = {}
    for name, cfg in (config().get("plugins") or {}).items():
        if not NAME.fullmatch(name) or cfg is False or (isinstance(cfg, dict) and cfg.get("enabled") is False):
            continue
        if (PLUGIN_DIR / name / "plugin.py").is_file():
            out[name] = cfg if isinstance(cfg, dict) else {}
    return out


def _module(name):
    if name not in enabled():
        raise NotFound(f"Plugin '{name}' is not enabled")
    if name not in _mods:
        _mods[name] = importlib.import_module(f"plugins.{name}.plugin")
    return _mods[name]


def assets():
    """[{name, js: [url], css: [url]}] for the web UI."""
    out = []
    for name in enabled():
        files = sorted(f.name for f in (PLUGIN_DIR / name / "static").glob("*") if FILE.fullmatch(f.name))
        out.append({"name": name,
                    "js": [f"/plugins/{name}/{f}" for f in files if f.endswith(".js")],
                    "css": [f"/plugins/{name}/{f}" for f in files if f.endswith(".css")]})
    return out


def asset(name, file):
    """(bytes, content type) of one browser file of an enabled plugin; NotFound if not allowed."""
    m = FILE.fullmatch(file)
    if name not in enabled() or not m:
        raise NotFound("not found")
    path = PLUGIN_DIR / name / "static" / file
    if not path.is_file():
        raise NotFound("not found")
    return path.read_bytes(), CTYPES[m.group(1)]


def call(method, name, route, arg):
    """Run a plugin route; NotFound if the plugin or route does not exist."""
    fn = getattr(_module(name), method, {}).get(route)
    if not fn:
        raise NotFound("not found")
    return fn(arg)
