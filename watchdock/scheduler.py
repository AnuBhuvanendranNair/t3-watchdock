"""Background scheduler for periodic tasks."""
import datetime
import re
import sys
import threading

from .core import CONFIG, STATE, config, load, lock, log, now, save, stop_event
from .alerts import notify_event
from .security import advisories, php_cycles, php_status, site_advisories, site_packages, typo3_security_feed
from .t3monitor import T3M_ENVS, _n, _upd_text, t3m_cfg, t3m_fetch, t3m_history_file, t3m_key
from .watcher import check_typo3
from .updates import send_update_commands


# ---------------------------------------------------------------- scheduler
NO_WATCH = "--no-watch" in sys.argv
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
sched_running = set()


def task_typo3_release():
    projects, errors = check_typo3()
    if not projects:
        return "No project with TYPO3 auto-update"
    if errors:
        raise RuntimeError(" | ".join(errors))
    latest = load(STATE, {}).get("typo3_latest", {})
    return "Latest: " + ", ".join(f"TYPO3 {m}: {v}" for m, v in sorted(latest.items()))


def task_t3monitor():
    sites = [(p, env) for p in config()["projects"] for env in T3M_ENVS
             if t3m_cfg(p, env).get("url") and t3m_key(p["id"], env)]
    if not sites:
        return "No project with t3monitor URL and key"
    failed, facts, totals, results = [], [], {"err": 0, "upd": 0, "new": 0}, []
    for p, env in sites:
        name = f"{p['name']} ({T3M_ENVS[env]['label']})"
        try:
            r = t3m_fetch(p, env, alert=False)
        except Exception as e:
            failed.append(f"{name}: {e}")
            facts.append((name, f"❌ CHECK FAILED: {e}"))
            continue
        results.append((p, env, r))
        d, sev = r["data"], [x.get("severity") for x in r["data"].get("status", [])]
        upd = {k: e for k, e in d["extensions"].items() if e.get("update")}
        totals["err"] += sev.count(2)
        totals["upd"] += len(upd)
        totals["new"] += len(r["new_err"]) + len(r["new_upd"])
        line = [f"TYPO3 {d.get('typo3') or '?'}", _n(sev.count(2), "error"), _n(sev.count(1), "warning")]
        if r["new_err"]:
            line.append("NEW errors: " + ", ".join(x["title"] for x in r["new_err"][:5]))
        line.append("updates: " + ("; ".join(("NEW " if k in r["new_upd"] else "") + f"{k} {_upd_text(e)}"
                                              for k, e in upd.items()) if upd else "none"))
        facts.append((name, " · ".join(line)))
    head = [_n(len(sites), "site"), _n(totals["err"], "error"), _n(totals["upd"], "extension update")]
    if failed:
        head.insert(1, f"{len(failed)} FAILED")
    notify_event("t3monitor check: " + " · ".join(head),
                 "Scheduled TYPO3 status check" + (f" – {totals['new']} new finding(s)." if totals["new"] else "."),
                 facts, f"http://127.0.0.1:{int(config().get('port', 8787))}/", "Open launcher")
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
    sites = []
    for p in config()["projects"]:
        for env in T3M_ENVS:
            if t3m_cfg(p, env).get("url") and t3m_key(p["id"], env):
                snaps = load(t3m_history_file(p["id"], env), {"snapshots": []}).get("snapshots")
                if snaps:
                    sites.append((p, env, snaps[0]["data"]))
    if not sites:
        return "No t3monitor data yet (run the t3monitor check first)"
    cycles = php_cycles()
    adv = advisories({k for _, _, d in sites for k in site_packages(d)})
    facts, n_adv, n_php, n_new = [], 0, 0, 0
    for p, env, d in sites:
        php = php_status(d.get("php"), cycles) if d.get("php") else None
        found = site_advisories(site_packages(d), adv)
        keys = {f"adv:{a['id']}:{a['package']}:{a['version']}" for a in found}
        if php and php["severity"]:
            keys.add(f"php:{php['state']}:{php['version']}:{php.get('latest')}")
        with lock:
            hf = t3m_history_file(p["id"], env)
            h = load(hf, {"snapshots": []})
            new = keys - set((h.get("security") or {}).get("reported", []))
            h["security"] = {"checked": now(), "php": php, "advisories": found, "reported": sorted(keys)}
            save(hf, h)
        n_adv += len(found)
        n_php += bool(php and php["severity"])
        n_new += len(new)
        if found or (php and php["severity"]):
            line = ([("NEW " if any(k.startswith("php:") for k in new) else "") + php["text"]]
                    if php and php["severity"] else [])
            line += [("NEW " if f"adv:{a['id']}:{a['package']}:{a['version']}" in new else "")
                     + f"{a['package']} {a['version']}: {a['title']}" + (f" ({a['severity']})" if a.get("severity") else "")
                     + (f" {a['link']}" if a.get("link") else "") for a in found]
            facts.append((f"{p['name']} ({T3M_ENVS[env]['label']})", " · ".join(line)))
    summary = f"{_n(len(sites), 'site')} · {n_adv} security {'advisory' if n_adv == 1 else 'advisories'} · {_n(n_php, 'PHP issue')}"
    if n_new:
        notify_event(f"Security check: {n_new} new finding(s)", "Scheduled PHP version and security advisory check.",
                     facts, f"http://127.0.0.1:{int(config().get('port', 8787))}/", "Open launcher")
    return summary + (f" · {n_new} new" if n_new else "")


def task_typo3_news():
    """TYPO3 security announcements (advisories and PSA). One message per run, only for items not seen before.
    The first run only stores what is there (no message for old announcements)."""
    items = typo3_security_feed()
    if not items:
        raise RuntimeError("TYPO3 security feed contains no announcements")
    with lock:
        st = load(STATE, {})
        old = st.get("typo3_security") or {}
        first, seen = "seen" not in old, set(old.get("seen", []))
        new = [] if first else [i for i in items if i["id"] not in seen]
        st["typo3_security"] = {"checked": now(), "seen": ([i["id"] for i in items] + [x for x in old.get("seen", [])
                                                               if x not in {i["id"] for i in items}])[:1000],
                                "items": items[:30]}
        save(STATE, st)
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
    "t3monitor": {"name": "t3monitor check (TYPO3 & extensions)", "run": task_t3monitor, "legacy": "t3monitor_interval_hours",
                  "description": "Reads TYPO3 version, extensions and status checks of every project with "
                                 "t3monitor URL and key, and records changes in the history."},
    "security": {"name": "PHP version & security advisories", "run": task_security, "legacy": "security_interval_hours",
                 "defaults": {"mode": "daily", "time": "07:00"},
                 "description": "Checks the PHP version of every site against php.net support dates (endoflife.date) "
                                "and TYPO3 core and extensions against known security advisories (Packagist). "
                                "Uses the data of the last t3monitor check; messages only for new findings."},
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
        save(CONFIG, cfg)
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
    with lock:
        st = load(STATE, {})
        st.setdefault("scheduler", {})[tid] = {"last_run": started, "finished": now(), "ok": ok, "result": result[:500]}
        save(STATE, st)
    return ok, result


def sched_view():
    st = load(STATE, {}).get("scheduler", {})
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
        st = load(STATE, {}).get("scheduler", {})
        for tid in TASKS:
            if tid in sched_running or (tid == "typo3_release" and NO_WATCH):
                continue
            nxt = sched_next(sched_cfg(tid), st.get(tid, {}).get("last_run"))
            if nxt and nxt <= datetime.datetime.now():
                threading.Thread(target=sched_run, args=(tid,), daemon=True).start()
        stop_event.wait(30)
