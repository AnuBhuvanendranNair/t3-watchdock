"""Daily version report: TYPO3, PHP, database (MySQL / MariaDB) and web server (nginx / Apache) of every monitored site
against the newest releases, with a status per component (ok / update / security or end of life)."""
import datetime
import html
import re
import urllib.request

from .core import TYPO3_API
from .db import typo3_latest
from .extensions import _vparse
from .security import _json, _passed, nginx_latest, nginx_status, php_cycles, php_status

EOL_API = "https://endoflife.date/api/{}.json"     # typo3, mariadb, mysql, apache-http-server: latest, eol, extendedSupport
APACHE_VULNS = "https://httpd.apache.org/security/vulnerabilities_24.html"   # CVEs per fixed 2.4 release
APACHE_BAD = {"critical", "important"}             # Apache ratings: critical, important, moderate, low

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


def apache_vulns():
    """[{'cve', 'rating', 'title', 'fixed': '2.4.71', 'from': '2.4.55', 'to': '2.4.70'}, ...] from the Apache
    httpd security page. 'from'/'to' come from the 'Affects' line ('2.4.55 through 2.4.70'); missing -> None."""
    req = urllib.request.Request(APACHE_VULNS, headers={"User-Agent": "t3-watchdock"})
    with urllib.request.urlopen(req, timeout=30) as r:
        page = r.read(3_000_000).decode("utf-8", "replace")
    out = []
    for sec in re.split(r'<h1 id="', page)[1:]:
        fixed = re.match(r"(2\.4\.\d+)", sec)
        if not fixed:
            continue
        for cve in re.split(r"<dt>", sec)[1:]:
            m = re.search(r'id="(CVE-[\d-]+)".*?\((\w+)\):\s*<name[^>]*>(.*?)</name>', cve, re.S)
            if not m:
                continue
            aff = re.search(r'Affects</td><td class="cve-value">\s*(2\.4\.\d+)\s+through\s+(2\.4\.\d+)', cve)
            out.append({"cve": m.group(1), "rating": m.group(2).lower(), "title": html.unescape(m.group(3)).strip(),
                        "fixed": fixed.group(1), "from": aff and aff.group(1), "to": aff and aff.group(2)})
    return out


def apache_affecting(version, vulns):
    """CVEs of the list that affect this 2.4 version (inside 'Affects', else: fixed in a later release)."""
    v = _vparse(version)
    if not v:
        return []
    hit = []
    for x in vulns:
        if x["from"] and x["to"]:
            if _vparse(x["from"])[0] <= v[0] <= _vparse(x["to"])[0]:
                hit.append(x)
        elif _vparse(x["fixed"])[0] > v[0]:
            hit.append(x)
    return hit


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
    try:
        ap = apache_vulns()
    except Exception:
        ap = None                                   # None = not available (no CVE status), [] = no CVEs
    return {"typo3": t3, "typo3_latest": typo3_latest(), "typo3_type": t3_type, "php": php, "nginx": ngx,
            "mariadb": _cycles("mariadb"), "mysql": _cycles("mysql"), "apache": _cycles("apache-http-server"),
            "apache_vulns": ap}


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


def web_state(server, rel):
    """Web server column: nginx (nginx.org) or Apache httpd (endoflife.date + Apache security page).
    Returns (status, name, [affecting Apache CVEs])."""
    raw = str(server or "").strip()
    name = raw.split("/")[0].split(" ")[0]
    if name.lower() == "nginx":
        s = nginx_status(raw, rel["nginx"])
        if not s:
            return _st("muted", None, "Version hidden"), "nginx", []
        if s["state"] == "unsupported":
            return _st("bad", s["version"], "Branch no longer supported", s["latest"]), "nginx", []
        if s["severity"]:
            return _st("warn", s["version"], f"→ {s['latest']}", s["latest"]), "nginx", []
        return _st("ok", s["version"], f"Current ({s['state']})"), "nginx", []
    if name.lower() == "apache":
        m = re.match(r"apache/(\d+)\.(\d+)\.(\d+)", raw, re.I)
        if not m:
            return _st("muted", None, "Version hidden"), "Apache", []
        v = m.group(0).split("/")[1]
        distro = re.search(r"\(([^)]+)\)", raw)
        note = f" · {distro.group(1)} build" if distro else ""
        c = rel["apache"].get(f"{m.group(1)}.{m.group(2)}") or {}
        today = datetime.date.today().isoformat()
        if _passed(c.get("eol"), today):
            return _st("bad", v, "End of life" + note), "Apache", []
        cves = apache_affecting(v, rel["apache_vulns"] or []) if m.group(2) == "4" else []
        if cves:
            worst = min(cves, key=lambda x: ["critical", "important", "moderate", "low"].index(x["rating"])
                        if x["rating"] in ("critical", "important", "moderate", "low") else 9)["rating"]
            return (_st("bad" if worst in APACHE_BAD else "warn", v,
                        f"{len(cves)} CVE{'s' if len(cves) > 1 else ''} ({worst}) → {c.get('latest') or 'update'}" + note,
                        c.get("latest")), "Apache", cves)
        if _newer(c.get("latest"), v):
            return _st("warn", v, f"→ {c['latest']}" + note, c["latest"]), "Apache", []
        if not c:
            return _st("muted", v, "No release data"), "Apache", []
        return _st("ok", v, "Current" + note), "Apache", []
    return _st("muted", name or None, "Not checked" if name else "No data"), name or "Web server", []
