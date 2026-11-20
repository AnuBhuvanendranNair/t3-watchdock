"""PHP version support (endoflife.date, newest releases from php.net), nginx versions (nginx.org), security advisories for TYPO3 core and extensions (Packagist)
and the TYPO3 security announcement feed (news.typo3.com)."""
import datetime
import email.utils
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .extensions import _vparse, constraint_ok

PHP_EOL_API = "https://endoflife.date/api/php.json"             # per branch: latest, support (active), eol
PHP_RELEASES_API = "https://www.php.net/releases/index.php?json&max=1&version={}"  # newest release of one branch
NGINX_DOWNLOAD = "https://nginx.org/en/download.html"           # current mainline and stable version
ADVISORY_API = "https://packagist.org/api/security-advisories/"  # FriendsOfPHP + GitHub advisories per package
ADVISORY_BATCH = 100                                            # packages per request
TYPO3_SEC_FEED = "https://news.typo3.com/security/rss-security"  # advisories + public service announcements (PSA)
FEED_MAX = 2_000_000                                            # bytes read from the feed at most


def _json(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "t3-watchdock"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def php_cycles():
    """{'8.4': {'cycle': '8.4', 'latest': '8.4.27', 'support': '2026-12-31', 'eol': '2028-12-31', ...}, ...}
    Support dates come from endoflife.date; 'latest' of supported branches from php.net, which has new
    releases on the day they come out (endoflife.date can be days behind). 'security' = release is a security release."""
    try:
        cycles = {str(c["cycle"]): c for c in _json(PHP_EOL_API)}
    except Exception as e:
        raise RuntimeError(f"PHP release data (endoflife.date) not available: {e}") from None
    today = datetime.date.today().isoformat()
    for k, c in cycles.items():
        if _passed(c.get("eol"), today):
            continue
        try:
            ver, info = next(iter(_json(PHP_RELEASES_API.format(k)).items()))
        except Exception:
            continue  # php.net unavailable: keep the endoflife.date value
        if _vparse(ver) and (not _vparse(c.get("latest")) or _vparse(ver)[0] >= _vparse(c["latest"])[0]):
            c.update(latest=ver, latestReleaseDate=info.get("date") or c.get("latestReleaseDate"),
                     security="security" in (info.get("tags") or []))
    return cycles


def nginx_latest():
    """{'mainline': '1.31.9', 'stable': '1.30.7'} from the nginx.org download page."""
    req = urllib.request.Request(NGINX_DOWNLOAD, headers={"User-Agent": "t3-watchdock"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read(500_000).decode("utf-8", "replace")
    except Exception as e:
        raise RuntimeError(f"nginx versions (nginx.org) not available: {e}") from None
    out = {}
    for kind in ("mainline", "stable"):
        m = re.search(kind + r" version.*?nginx-(\d+\.\d+\.\d+)\.tar\.gz", page, re.I | re.S)
        if m:
            out[kind] = m.group(1)
    if not out:
        raise RuntimeError("nginx versions not found on nginx.org")
    return out


def nginx_status(server, latest):
    """None if the web server is not nginx or has no version. severity: 2 = branch no longer supported
    (only the current mainline and stable branch get fixes), 1 = newer release of the same branch, 0 = current."""
    m = re.match(r"nginx/(\d+\.\d+\.\d+)", (server or "").strip(), re.I)
    if not m or not latest:
        return None
    v = m.group(1)
    branch = next((b for b, lv in latest.items() if lv.split(".")[:2] == v.split(".")[:2]), None)
    if not branch:
        tips = " or ".join(f"{b} {lv}" for b, lv in latest.items())
        return {"version": v, "state": "unsupported", "latest": latest.get("stable") or latest.get("mainline"),
                "severity": 2, "text": f"nginx {v} · branch {'.'.join(v.split('.')[:2])} no longer supported · update to {tips}"}
    lv = latest[branch]
    outdated = _vparse(lv)[0] > _vparse(v)[0]
    return {"version": v, "state": branch, "latest": lv, "severity": 1 if outdated else 0,
            "text": f"nginx {v} ({branch})" + (f" · update to {lv} available" if outdated else " · current")}


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
        parts.append(f"update to {latest} available" + (" (security release)" if c.get("security") else ""))
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


def parse_security_feed(raw):
    """RSS bytes -> [{'id', 'ref', 'title', 'link', 'date', 'category', 'psa'}, ...], newest first as in the feed."""
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:        # a plain RSS feed needs neither; no entity expansion
        raise RuntimeError("unexpected document type")
    items = []
    for it in ET.fromstring(raw).iter("item"):
        title = " ".join((it.findtext("title") or "").split())
        link = (it.findtext("link") or "").strip()
        if not title or not re.match(r"https://[^\s/]+/\S*$", link):   # the link is shown as a clickable URL
            continue
        m = re.match(r"TYPO3-[A-Z]+(?:-[A-Z]+)*-\d{4}-\d+", title)
        try:
            date = email.utils.parsedate_to_datetime(it.findtext("pubDate") or "").date().isoformat()
        except (TypeError, ValueError):
            date = ""
        items.append({"id": (it.findtext("guid") or link).strip()[:300], "ref": m.group(0) if m else "",
                      "title": title[:300], "link": link[:500], "date": date,
                      "category": ", ".join(c.text.strip() for c in it.findall("category") if c.text)[:100],
                      "psa": bool(m and "-PSA-" in m.group(0))})
    return items


def typo3_security_feed():
    try:
        req = urllib.request.Request(TYPO3_SEC_FEED, headers={"User-Agent": "t3-watchdock"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return parse_security_feed(r.read(FEED_MAX))
    except Exception as e:
        raise RuntimeError(f"TYPO3 security feed (news.typo3.com) not available: {e}") from None
