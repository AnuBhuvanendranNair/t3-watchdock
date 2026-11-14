"""PHP version support (endoflife.date) and security advisories for TYPO3 core and extensions (Packagist)."""
import datetime
import json
import urllib.parse
import urllib.request

from .extensions import _vparse, constraint_ok

PHP_EOL_API = "https://endoflife.date/api/php.json"             # per branch: latest, support (active), eol
ADVISORY_API = "https://packagist.org/api/security-advisories/"  # FriendsOfPHP + GitHub advisories per package
ADVISORY_BATCH = 100                                            # packages per request


def _json(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "t3-watchdock"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def php_cycles():
    """{'8.4': {'cycle': '8.4', 'latest': '8.4.27', 'support': '2026-12-31', 'eol': '2028-12-31', ...}, ...}"""
    try:
        return {str(c["cycle"]): c for c in _json(PHP_EOL_API)}
    except Exception as e:
        raise RuntimeError(f"PHP release data (endoflife.date) not available: {e}") from None


def _passed(v, today):
    """endoflife.date fields are a date string or a boolean."""
    return v is True or (isinstance(v, str) and v <= today)


def php_status(version, cycles):
    """severity: 2 = end of life, 1 = newer patch release available, 0 = ok. state: eol | security | active | unknown."""
    pv = _vparse(version)
    c = cycles.get(f"{pv[0][0]}.{pv[0][1]}") if pv else None
    if not c:
        return {"version": version, "state": "unknown", "severity": 0, "text": f"PHP {version or '?'}: no release data"}
    today = datetime.date.today().isoformat()
    eol, support, latest = c.get("eol"), c.get("support"), c.get("latest") or ""
    state = "eol" if _passed(eol, today) else "security" if _passed(support, today) else "active"
    outdated = bool(_vparse(latest)) and _vparse(latest)[0] > pv[0]
    parts = [f"PHP {version}"]
    if state == "eol":
        parts.append(f"END OF LIFE since {eol}" if isinstance(eol, str) else "END OF LIFE")
    elif state == "security":
        parts.append("security fixes only" + (f" until {eol}" if isinstance(eol, str) else ""))
    elif isinstance(eol, str):
        parts.append(f"supported until {eol}")
    if outdated:
        parts.append(f"update to {latest} available")
    return {"version": version, "state": state, "latest": latest, "eol": eol if isinstance(eol, str) else None,
            "severity": 2 if state == "eol" else 1 if outdated else 0, "text": " · ".join(parts)}


def site_packages(data):
    """Composer packages of one t3monitor snapshot: TYPO3 core + public extensions -> installed version."""
    pk = {"typo3/cms-core": data["typo3"]} if data.get("typo3") else {}
    for e in (data.get("extensions") or {}).values():
        if e.get("composer") and e.get("version") and not e.get("local"):
            pk[e["composer"].lower()] = e["version"]
    return pk


def advisories(packages):
    """{package: [advisory, ...]} from Packagist for all given package names (batched POST requests)."""
    names, out = sorted(set(packages)), {}
    for i in range(0, len(names), ADVISORY_BATCH):
        body = urllib.parse.urlencode([("packages[]", n) for n in names[i:i + ADVISORY_BATCH]]).encode()
        try:
            adv = _json(ADVISORY_API, body).get("advisories")
        except Exception as e:
            raise RuntimeError(f"Packagist security advisories not available: {e}") from None
        if isinstance(adv, dict):                    # no advisories at all -> empty list instead of an object
            out.update(adv)
    return out


def site_advisories(packages, adv):
    """Advisories whose affected versions include the installed version."""
    found = []
    for name, ver in sorted(packages.items()):
        for a in adv.get(name) or []:
            if constraint_ok(ver, a.get("affectedVersions") or ""):
                found.append({"id": a.get("advisoryId"), "package": name, "version": ver, "title": a.get("title") or "",
                              "cve": a.get("cve"), "severity": a.get("severity"), "link": a.get("link"),
                              "affected": a.get("affectedVersions")})
    return found
