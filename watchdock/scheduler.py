"""Background scheduler for periodic tasks."""
import datetime
import os
import re
import sys
import threading

from .core import app_url, config, load, lock, log, now, save, save_config, stop_event
from .db import kv_get, kv_set, sched_result_set, sched_results, typo3_latest
from .alerts import notify_event
from .security import (_passed, advisories, nginx_latest, nginx_status, php_cycles, php_status, site_advisories,
                       site_packages, typo3_security_feed)
from .extensions import _vparse
from .t3monitor import T3M_ENVS, _n, _upd_text, t3m_cfg, t3m_fetch, t3m_history_file, t3m_key
from .watcher import check_typo3
from .updates import send_update_commands


# ---------------------------------------------------------------- scheduler
NO_WATCH = "--no-watch" in sys.argv or os.environ.get("WATCHDOCK_NO_WATCH") == "1"   # set by app.py for Gunicorn
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
sched_running = set()


def task_typo3_release():
    projects, errors = check_typo3()
    if not projects:
        return "No project with TYPO3 auto-update"
    if errors:
        raise RuntimeError(" | ".join(errors))
    latest = typo3_latest()
    return "Latest: " + ", ".join(f"TYPO3 {m}: {v}" for m, v in sorted(latest.items()))


def _grouped(rows):
    """Show site and environment only when they change, so rows of one site read as a group."""
    out, prev = [], (None, None)
    for r in rows:
        key = (r[0], r[1])
        out.append(([r[0], r[1]] if key[0] != prev[0] else ["", r[1]] if key != prev else ["", ""]) + r[2:])
        prev = key
    return out


def _explain_failure(err):
    """Plain-language problem and next step for a failed TYPO3 health check."""
    low = err.lower()
    if "encryption key" in low:
        return "The site rejects the t3monitor key", "Compare the key in the t3monitor extension with the one in T3 Watchdock"
    if "timed out" in low or "timeout" in low:
        return "The site did not answer in time", "Check that the site is online and not overloaded"
    if "web page instead" in low:
        return "The site showed a web page instead of status data", "Check the t3monitor URL and Basic auth login"
    if "empty response" in low:
        return "The site sent an empty answer", "Check that the t3monitor extension is installed and active"
    if "http 401" in low or "http 403" in low:
        return "Access denied", "Check the Basic auth login and the t3monitor key"
    if "http 404" in low:
        return "t3monitor not found at this URL", "Check the t3monitor URL"
    if "not resolve" in low or "name or service" in low or "nodename" in low:
        return "Site address not found", "Check the URL and DNS"
    return err[:150], "Open the site in T3 Watchdock and run the check again"


def task_t3monitor():
    sites = [(p, env) for p in config()["projects"] for env in T3M_ENVS
             if t3m_cfg(p, env).get("url") and t3m_key(p["id"], env)]
    if not sites:
        return "No project with t3monitor URL and key"
    failed, totals, results = [], {"err": 0, "upd": 0, "new": 0}, []
    sec_failed, sec_new, sec_status, sec_upd = [], [], [], []
    for p, env in sites:
        label = T3M_ENVS[env]["label"]
        try:
            r = t3m_fetch(p, env, alert=False)
        except Exception as e:
            failed.append(f"{p['name']} · {label}: {e}")
            problem, todo = _explain_failure(str(e))
            sec_failed.append([p["name"], label, {"text": problem, "sub": todo, "tone": "bad"}])
            continue
        results.append((p, env, r))
        d, sev = r["data"], [x.get("severity") for x in r["data"].get("status", [])]
        upd = {k: e for k, e in d["extensions"].items() if e.get("update")}
        totals["err"] += sev.count(2)
        totals["upd"] += len(upd)
        totals["new"] += len(r["new_err"]) + len(r["new_upd"])
        n_err, n_warn = sev.count(2), sev.count(1)
        sec_status.append([p["name"], label, {"text": d.get("typo3") or "?", "mono": True},
                           {"text": n_err, "num": True, "tone": "bad" if n_err else "muted"},
                           {"text": n_warn, "num": True, "tone": "warn" if n_warn else "muted"}])
        for x in r["new_err"][:5]:
            sec_new.append([p["name"], label, x["title"]])
        for k, e in upd.items():
            ext = {"text": k, "mono": True}
            if e.get("major"):
                ext.update(tag="Major")
            elif k in r["new_upd"]:
                ext.update(tag="New", tag_tone="ok")
            sec_upd.append([p["name"], label, ext, {"text": f"{str(e['version']).lstrip('v')} → "
                                                            f"{str(e['latest']).lstrip('v')}", "mono": True}])
    head = [_n(len(sites), "site"), _n(totals["err"], "error"), _n(totals["upd"], "extension update")]
    if failed:
        head.insert(1, f"{len(failed)} FAILED")
    if failed:
        headline = f"{_n(len(failed), 'site')} could not be checked"
    elif sec_new:
        headline = f"{_n(len(sec_new), 'new error')} since the last check"
    else:
        headline = f"All {_n(len(sites), 'site')} checked"
    W = ["30%", "16%"]                         # same Site / Environment column widths in every table
    notify_event("TYPO3 health check: " + " · ".join(head),
                 "Scheduled TYPO3 status check of every site with t3monitor.", [],
                 app_url(), "Open T3 Watchdock",
                 headline=headline,
                 stats=[("Sites checked", len(sites), None),
                        ("Not reachable", len(failed), "bad" if failed else "muted"),
                        ("TYPO3 errors", totals["err"], "bad" if totals["err"] else "muted"),
                        ("Updates", totals["upd"], "warn" if totals["upd"] else "muted")],
                 sections=[
                     {"title": "Could not be checked", "note": "These sites gave no usable answer.",
                      "widths": W, "cols": ["Site", "Environment", "Problem"], "rows": _grouped(sec_failed)},
                     {"title": "New errors since the last check",
                      "widths": W, "cols": ["Site", "Environment", "Error"], "rows": _grouped(sec_new)},
                     {"title": "Extension updates",
                      "note": "Major updates can change behaviour. Test them on staging first.",
                      "widths": W, "cols": ["Site", "Environment", "Extension", "Version"], "rows": _grouped(sec_upd)},
                     {"title": "Status per site", "note": "Errors and warnings from the TYPO3 system status.",
                      "widths": W, "cols": ["Site", "Environment", "TYPO3", "Errors", "Warnings"], "rows": _grouped(sec_status)}])
    try:
        send_update_commands(results)
    except Exception as e:                     # never fail the status check because of the extra message
        log(f"Update commands failed: {e}")
    if failed:
        raise RuntimeError(f"{len(sites) - len(failed)}/{len(sites)} OK. " + " | ".join(failed))
    return f"{len(sites)}/{len(sites)} site(s) checked"


def task_security():
    """PHP support status and security advisories of every site, from its last t3monitor snapshot.
    One summary message per run, only when there are findings not reported before."""
    sites = _monitored_sites()
    if not sites:
        return "No t3monitor data yet (run the TYPO3 health check first)"
    cycles = php_cycles()
    try:
        ngx, ngx_err = nginx_latest(), ""
    except RuntimeError as e:
        ngx, ngx_err = {}, f" · {e}"
    adv = advisories({k for _, _, d in sites for k in site_packages(d)})
    facts, n_adv, n_php, n_ngx, n_new = [], 0, 0, 0, 0
    for p, env, d in sites:
        php = php_status(d.get("php"), cycles) if d.get("php") else None
        found = site_advisories(site_packages(d), adv)
        keys = {f"adv:{a['id']}:{a['package']}:{a['version']}" for a in found}
        if php and php["severity"]:
            keys.add(f"php:{php['state']}:{php['version']}:{php.get('latest')}")
        ngs = nginx_status(d.get("webserver"), ngx)
        if ngs and ngs["severity"]:
            keys.add(f"nginx:{ngs['state']}:{ngs['version']}:{ngs['latest']}")
        with lock:
            hf = t3m_history_file(p["id"], env)
            h = load(hf, {"snapshots": []})
            new = keys - set((h.get("security") or {}).get("reported", []))
            h["security"] = {"checked": now(), "php": php, "advisories": found, "nginx": ngs,
                             "reported": sorted(keys)}
            save(hf, h)
        n_adv += len(found)
        n_php += bool(php and php["severity"])
        n_ngx += bool(ngs and ngs["severity"])
        n_new += len(new)
        if found or (php and php["severity"]) or (ngs and ngs["severity"]):
            line = ([("NEW " if any(k.startswith("php:") for k in new) else "") + php["text"]]
                    if php and php["severity"] else [])
            line += ([("NEW " if any(k.startswith("nginx:") for k in new) else "") + ngs["text"]]
                     if ngs and ngs["severity"] else [])
            line += [("NEW " if f"adv:{a['id']}:{a['package']}:{a['version']}" in new else "")
                     + f"{a['package']} {a['version']}: {a['title']}" + (f" ({a['severity']})" if a.get("severity") else "")
                     + (f" {a['link']}" if a.get("link") else "") for a in found]
            facts.append((f"{p['name']} ({T3M_ENVS[env]['label']})", " · ".join(line)))
    summary = f"{_n(len(sites), 'site')} · {n_adv} security {'advisory' if n_adv == 1 else 'advisories'} · {_n(n_php, 'PHP issue')} · {_n(n_ngx, 'nginx issue')}{ngx_err}"
    if n_new:
        notify_event(f"Security check: {n_new} new finding(s)", "Scheduled PHP, nginx and security advisory check.",
                     facts, app_url(), "Open T3 Watchdock")
    return summary + (f" · {n_new} new" if n_new else "")


def _monitored_sites():
    """(project, env, newest t3monitor data) of every instance with t3monitor URL, key and at least one snapshot."""
    sites = []
    for p in config()["projects"]:
        for env in T3M_ENVS:
            if t3m_cfg(p, env).get("url") and t3m_key(p["id"], env):
                snaps = load(t3m_history_file(p["id"], env), {"snapshots": []}).get("snapshots")
                if snaps:
                    sites.append((p, env, snaps[0]["data"]))
    return sites


def task_releases():
    """New PHP releases (php.net) and nginx releases (nginx.org) on the day they come out. One message per run,
    with the sites that still run an older version. The first run only stores what is there."""
    today = datetime.date.today().isoformat()
    cycles = php_cycles()
    cur = {f"php:{k}": c["latest"] for k, c in cycles.items()
           if c.get("latest") and not _passed(c.get("eol"), today)}
    ngx = nginx_latest()
    cur.update({f"nginx:{b}": v for b, v in ngx.items()})
    with lock:
        old = kv_get("releases") or {}
        first, seen = "seen" not in old, old.get("seen", {})
        newer = lambda k: not seen.get(k) or (_vparse(cur[k]) or ((0,),))[0] > (_vparse(seen[k]) or ((0,),))[0]
        new = [] if first else [k for k in cur if newer(k)]
        kv_set("releases", {"checked": now(), "seen": {**seen, **{k: cur[k] for k in cur if newer(k)}}})
    if new:
        sites, facts = _monitored_sites(), []
        for k in new:
            kind, branch = k.split(":")
            if kind == "php":
                c = cycles.get(branch, {})
                hit = [(p, env) for p, env, d in sites if d.get("php") and str(d["php"]).startswith(branch + ".")
                       and php_status(d["php"], cycles)["severity"]]
                label = f"PHP {cur[k]}" + (" (security release)" if c.get("security") else "")
            else:
                hit = [(p, env) for p, env, d in sites
                       if (st := nginx_status(d.get("webserver"), ngx)) and st["severity"]
                       and st["state"] in (branch, "unsupported")]
                label = f"nginx {cur[k]} ({branch})"
            facts.append((label, (f"{_n(len(hit), 'site')} on an older version: " + ", ".join(
                f"{p['name']} ({T3M_ENVS[env]['label']})" for p, env in hit)) if hit else "No monitored site affected"))
            log(f"New release: {label}")
        notify_event("New release: " + " · ".join(f[0] for f in facts),
                     "New PHP or nginx versions are out (php.net, nginx.org). Listed sites run an older version; "
                     "the PHP, nginx & security advisories check lists them per site.",
                     facts, app_url(), "Open T3 Watchdock")
    if first:
        return f"{len(cur)} branches stored as baseline (messages from the next release on)"
    return " · ".join(f"{k.replace(':', ' ')} {v}" for k, v in cur.items()) + (f" · {len(new)} new" if new else "")


def task_typo3_news():
    """TYPO3 security announcements (advisories and PSA). One message per run, only for items not seen before.
    The first run only stores what is there (no message for old announcements)."""
    items = typo3_security_feed()
    if not items:
        raise RuntimeError("TYPO3 security feed contains no announcements")
    with lock:
        old = kv_get("typo3_security") or {}
        first, seen = "seen" not in old, set(old.get("seen", []))
        new = [] if first else [i for i in items if i["id"] not in seen]
        kv_set("typo3_security", {"checked": now(), "seen": ([i["id"] for i in items] + [x for x in old.get("seen", [])
                                                             if x not in {i["id"] for i in items}])[:1000],
                                  "items": items[:30]})
    for i in new:
        log(f"TYPO3 security: {i['title']} {i['link']}")
    if new:
        psa = sum(1 for i in new if i["psa"])
        notify_event(f"TYPO3 security: {_n(len(new), 'new announcement')}" + (f" ({psa} PSA)" if psa else ""),
                     "New entries in the TYPO3 security feed (news.typo3.com). Affected sites are listed by the "
                     "PHP version & security advisories check; announcements (PSA) need a manual look.",
                     [(i["ref"] or i["date"] or "–", f"{i['title']} {i['link']}") for i in new],
                     new[0]["link"], "Open announcement")
    if first:
        return f"{_n(len(items), 'announcement')} stored as baseline (messages from the next new one on)"
    return f"{_n(len(items), 'announcement')} · {len(new)} new" + (f" · latest: {items[0]['title'][:120]}")


TASKS = {
    "typo3_release": {"name": "TYPO3 release check", "run": task_typo3_release, "legacy": "check_interval_hours",
                      "description": "Checks get.typo3.org for new TYPO3 releases; on a new version the update "
                                     "pipeline of every project with TYPO3 auto-update is started."},
    "t3monitor": {"name": "TYPO3 health check (version, extensions, status)", "run": task_t3monitor, "legacy": "t3monitor_interval_hours",
                  "description": "Reads TYPO3 version, extensions and status checks of every project with "
                                 "t3monitor URL and key, and records changes in the history."},
    "releases": {"name": "PHP & nginx releases", "run": task_releases, "legacy": "releases_interval_hours",
                 "defaults": {"hours": 3.0},
                 "description": "Checks php.net and nginx.org for new releases; one message per new version with "
                                "the monitored sites that still run an older version."},
    "security": {"name": "PHP, nginx & security advisories", "run": task_security, "legacy": "security_interval_hours",
                 "defaults": {"mode": "daily", "time": "07:00"},
                 "description": "Checks the PHP version of every site against the newest release (php.net) and support "
                                "dates (endoflife.date), nginx against the current mainline and stable release (nginx.org), "
                                "and TYPO3 core and extensions against known security advisories (Packagist). "
                                "Uses the data of the last TYPO3 health check; messages only for new findings."},
    "typo3_news": {"name": "TYPO3 security announcements", "run": task_typo3_news, "legacy": "typo3_news_interval_hours",
                   "defaults": {"hours": 3.0},
                   "description": "Reads the TYPO3 security feed (news.typo3.com): core and extension advisories and "
                                  "public service announcements such as security release pre-announcements. "
                                  "Messages only for new entries; the list is on the Activity page."},
}


def sched_cfg(tid):
    c = config()
    d = {"enabled": True, "mode": "interval", "hours": float(c.get(TASKS[tid]["legacy"], 6)),
         "time": "07:00", "days": list(range(7)), **TASKS[tid].get("defaults", {})}
    d.update((c.get("scheduler") or {}).get(tid) or {})
    return d


def sched_describe(c):
    if c["mode"] == "daily":
        days = "every day" if len(c["days"]) == 7 else ", ".join(DAYS[d] for d in sorted(c["days"]))
        return f"daily at {c['time']} ({days})"
    return f"every {c['hours']:g} h"


def sched_next(c, last):
    """Next due time; None = disabled. A missed run (launcher was off) is due immediately."""
    if not c["enabled"]:
        return None
    nowd = datetime.datetime.now().replace(microsecond=0)
    last = datetime.datetime.fromisoformat(last) if last else None
    if c["mode"] == "interval":
        return last + datetime.timedelta(hours=c["hours"]) if last else nowd
    h, m = map(int, c["time"].split(":"))
    base = last or nowd
    for i in range(8):
        d = (base + datetime.timedelta(days=i)).replace(hour=h, minute=m, second=0)
        if d > base and d.weekday() in c["days"]:
            return d
    return None


def save_sched(b):
    tid = b.get("id")
    if tid not in TASKS:
        raise RuntimeError(f"Unknown task: {tid}")
    mode = b.get("mode")
    if mode not in ("interval", "daily"):
        raise RuntimeError("Mode must be interval or daily")
    hours = float(b.get("hours") or 0)
    if mode == "interval" and not 0.25 <= hours <= 168:
        raise RuntimeError("Interval must be between 0.25 and 168 hours")
    t = (b.get("time") or "").strip()
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
        raise RuntimeError("Time must be HH:MM")
    days = sorted({int(d) for d in b.get("days") or [] if 0 <= int(d) <= 6})
    if mode == "daily" and not days:
        raise RuntimeError("Select at least one weekday")
    with lock:
        cfg = config()
        cfg.setdefault("scheduler", {})[tid] = {"enabled": bool(b.get("enabled")), "mode": mode,
                                                "hours": hours or 6, "time": t, "days": days or list(range(7))}
        save_config(cfg)
    log(f"Scheduler: '{TASKS[tid]['name']}' set to {sched_describe(sched_cfg(tid))}"
        + ("" if b.get("enabled") else " (disabled)"))
    return sched_view()


def sched_run(tid):
    """Run a task now (blocking); records last run and result."""
    if tid in sched_running:
        raise RuntimeError("Task is already running")
    sched_running.add(tid)
    started, ok = now(), True
    try:
        result = TASKS[tid]["run"]()
    except Exception as e:
        ok, result = False, str(e)
        log(f"Scheduler: '{TASKS[tid]['name']}' failed: {e}")
    finally:
        sched_running.discard(tid)
    sched_result_set(tid, started, now(), ok, result[:500])
    return ok, result


def sched_view():
    st = sched_results()
    out = []
    for tid, t in TASKS.items():
        c, r = sched_cfg(tid), st.get(tid, {})
        nxt = sched_next(c, r.get("last_run"))
        out.append({"id": tid, "name": t["name"], "description": t["description"], "cfg": c,
                    "schedule": sched_describe(c), "last_run": r.get("last_run"), "ok": r.get("ok"),
                    "result": r.get("result"), "running": tid in sched_running,
                    "blocked": tid == "typo3_release" and NO_WATCH,
                    "next_run": nxt.isoformat(timespec="seconds") if nxt else None})
    return out


def scheduler():
    while not stop_event.is_set():
        st = sched_results()
        for tid in TASKS:
            if tid in sched_running or (tid == "typo3_release" and NO_WATCH):
                continue
            nxt = sched_next(sched_cfg(tid), st.get(tid, {}).get("last_run"))
            if nxt and nxt <= datetime.datetime.now():
                threading.Thread(target=sched_run, args=(tid,), daemon=True).start()
        stop_event.wait(30)
