#!/usr/bin/env python3
"""T3 Watchdock — local web app (Python stdlib only).

- Lists GitLab projects, runs pipelines, shows jobs, plays manual jobs.
- Background check of the TYPO3 release API; on a new release it triggers the
  pipelines of all projects with "auto_typo3.enabled" (intended: staging only).
- Token is read server-side from ~/.gitlab-token and never sent to the browser.
- Projects, settings, runs and log are stored in the SQLite database watchdock.db.

Code lives in the watchdock/ package, the web UI in static/.

Settings without a UI (e.g. plugins, port) are changed on the command line:
    python3 app.py config get [KEY]
    python3 app.py config set KEY JSON      e.g.  config set plugins '{"gingco_patchday": {}}'
    python3 app.py config unset KEY
"""
import json
import sys


def config_cli(args):
    from watchdock.core import config, lock, save_config
    usage = "usage: app.py config get [KEY] | set KEY JSON | unset KEY"
    if not args or args[0] not in ("get", "set", "unset"):
        sys.exit(usage)
    cmd, rest = args[0], args[1:]
    if cmd == "get":
        cfg = {k: v for k, v in config().items() if k != "projects"}
        if rest and rest[0] not in cfg:
            sys.exit(f"Not set: {rest[0]}")
        print(json.dumps(cfg[rest[0]] if rest else cfg, indent=2, ensure_ascii=False))
        return
    if not rest or rest[0] == "projects" or (cmd == "set") != (len(rest) == 2):
        sys.exit(usage + "\n(projects are managed in the UI or with the JSON export / import)")
    with lock:
        cfg = config()
        if cmd == "set":
            try:
                cfg[rest[0]] = json.loads(rest[1])
            except json.JSONDecodeError as e:
                sys.exit(f"Value is not valid JSON ({e}). Strings need quotes: '\"text\"'")
        else:
            cfg.pop(rest[0], None)
        save_config(cfg)
    print(f"{rest[0]} {'saved' if cmd == 'set' else 'removed'}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["config"]:
        config_cli(sys.argv[2:])
    else:
        from watchdock.server import main
        main()
