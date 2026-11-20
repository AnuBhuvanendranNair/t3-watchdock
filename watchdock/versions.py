"""Daily version report: TYPO3, PHP, database (MySQL / MariaDB) and nginx of every monitored site
against the newest releases, with a status per component (ok / update / security or end of life)."""
import datetime
import re

from .core import TYPO3_API
from .db import typo3_latest
from .extensions import _vparse
from .security import _json, _passed, nginx_latest, nginx_status, php_cycles, php_status

EOL_API = "https://endoflife.date/api/{}.json"     # typo3, mariadb, mysql: per branch latest, eol, extendedSupport

# tone -> (glyph, meaning); colours come from alerts.TONES
ICONS = {"bad": ("!", "Security issue or end of life"), "warn": ("↑", "Update available"),
         "ok": ("✓", "Current"), "muted": ("–", "Not checked")}


def _cycles(product):
    try:
        return {str(c["cycle"]): c for c in _json(EOL_API.format(product))}
    except Exception:
        return {}


def _newer(latest, version):
    a, b = _vparse(latest), _vparse(version)
    return bool(a and b and a[0] > b[0])


def release_data():
    """Everything the report compares against; failed sources give empty dicts (status 'not checked')."""
    t3 = _cycles("typo3")
    t3_type = {}
    for major in typo3_latest():
        try:
            t3_type[major] = _json(TYPO3_API.format(major=major)).get("type")
        except Exception:
            pass
    try:
        php = php_cycles()
    except RuntimeError:
        php = {}
    try:
        ngx = nginx_latest()
    except RuntimeError:
        ngx = {}
    return {"typo3": t3, "typo3_latest": typo3_latest(), "typo3_type": t3_type, "php": php, "nginx": ngx,
            "mariadb": _cycles("mariadb"), "mysql": _cycles("mysql")}


def _st(tone, version, label, latest=None):
    return {"tone": tone, "version": version or "–", "label": label, "latest": latest}


def typo3_state(version, advisories, rel):
    if not version:
        return _st("muted", None, "No data")
    major = str(version).split(".")[0]
    today = datetime.date.today().isoformat()
    c = rel["typo3"].get(major) or {}
    latest = rel["typo3_latest"].get(major) or c.get("latest")
    core = [a for a in advisories or [] if a.get("package") == "typo3/cms-core"]
    if core:
        sev = max((a.get("severity") or "" for a in core), key=lambda s: ["", "low", "medium", "high", "critical"].index(s)
                  if s in ("low", "medium", "high", "critical") else 0)
        return _st("bad", version, f"{len(core)} security issue{'s' if len(core) > 1 else ''}"
                   + (f" ({sev})" if sev else ""), latest)
    if _passed(c.get("eol"), today):
        ext = c.get("extendedSupport")
        return _st("bad", version, "End of life" + (f" · ELTS until {ext}" if isinstance(ext, str) and ext > today else ""))
    if latest and _newer(latest, version):
        sec = rel["typo3_type"].get(major) == "security"
        return _st("bad" if sec else "warn", version, f"→ {latest}" + (" (security release)" if sec else ""), latest)
    return _st("ok" if latest else "muted", version, "Current" if latest else "No release data")


def php_state(version, rel):
    if not version:
        return _st("muted", None, "No data")
    if not rel["php"]:
        return _st("muted", version, "No release data")
    s = php_status(version, rel["php"])
    v = str(version).split("-")[0]
    if s["state"] == "eol":
        return _st("bad", v, "End of life")
    if s["severity"]:
        sec = (rel["php"].get(".".join(v.split(".")[:2])) or {}).get("security")
        return _st("bad" if sec else "warn", v, f"→ {s['latest']}" + (" (security release)" if sec else ""), s["latest"])
    if s["state"] == "unknown":
        return _st("muted", v, "No release data")
    return _st("ok", v, "Current" + (" · security fixes only" if s["state"] == "security" else ""))


def db_state(raw, rel):
    """'MySQL 11.8.9-MariaDB-ubu2404' -> MariaDB 11.8.9; '8.4.11-12' -> MySQL 8.4.11."""
    if not raw:
        return _st("muted", None, "No data"), "Database"
    text = re.sub(r"^mysql\s+", "", str(raw), flags=re.I)
    kind = "MariaDB" if "mariadb" in text.lower() else "MySQL"
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", text)
    if not m:
        return _st("muted", text, "Unknown version"), kind
    v = m.group(0)
    c = rel[kind.lower()].get(f"{m.group(1)}.{m.group(2)}")
    if not c:
        return _st("muted", v, "No release data"), kind
    today = datetime.date.today().isoformat()
    if _passed(c.get("eol"), today):
        return _st("bad", v, "End of life"), kind
    if _newer(c.get("latest"), v):
        return _st("warn", v, f"→ {c['latest']}", c["latest"]), kind
    return _st("ok", v, "Current"), kind


def nginx_state(server, rel):
    s = nginx_status(server, rel["nginx"])
    if not s:
        name = str(server or "").split("/")[0].split(" ")[0]
        return _st("muted", name or None, "Not nginx" if name else "No data")
    if s["state"] == "unsupported":
        return _st("bad", s["version"], "Branch no longer supported", s["latest"])
    if s["severity"]:
        return _st("warn", s["version"], f"→ {s['latest']}", s["latest"])
    return _st("ok", s["version"], f"Current ({s['state']})")
