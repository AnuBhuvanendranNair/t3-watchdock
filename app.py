#!/usr/bin/env python3
"""T3 Watchdock — web app (Flask, served by Gunicorn; packages in requirements.txt).

- Lists GitLab projects, runs pipelines, shows jobs, plays manual jobs.
- Background check of the TYPO3 release API; on a new release it triggers the
  pipelines of all projects with "auto_typo3.enabled" (intended: staging only).
- GitLab tokens (one per user + a service token for background work) are stored encrypted in watchdock.db
  and never sent to the browser (key: see watchdock/crypto.py).
- Projects, settings, runs and log are stored in the SQLite database watchdock.db.

Code lives in the watchdock/ package, the web UI in static/.

Settings without a UI (e.g. plugins, port) are changed on the command line:
    python3 app.py config get [KEY]
    python3 app.py config set KEY JSON      e.g.  config set plugins '{"gingco_patchday": {}}'
    python3 app.py config unset KEY

Login accounts (also as bin/t3-watchdock …):
    python3 app.py add-user NAME | set-password NAME | remove-user NAME | unlock-user NAME | list-users
    python3 app.py set-admin NAME on|off      (admins manage the GitLab service token)
    python3 app.py gen-secret-key              (prints a new key for WATCHDOCK_SECRET_KEY)
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


USER_CMDS = ("add-user", "set-password", "remove-user", "unlock-user", "list-users", "set-admin")


def user_cli(cmd, args):
    import getpass
    from watchdock import auth, db
    if cmd == "list-users":
        for u in db.users():
            print(f"{u['name']}\t{u['created']}" + ("\tadmin" if u["admin"] else "")
                  + ("\tGitLab token" if u["has_token"] else "") + (f"\tLOCKED since {u['locked']}" if u["locked"] else ""))
        return
    if cmd == "set-admin":
        if len(args) != 2 or args[1] not in ("on", "off"):
            sys.exit("usage: set-admin NAME on|off")
        if not db.user_set_admin(args[0], args[1] == "on"):
            sys.exit(f"No such user: {args[0]}")
        print(f"Admin {args[1]}: {args[0]}")
        return
    if len(args) != 1:
        sys.exit(f"usage: {cmd} NAME")
    name = args[0]
    try:
        if cmd == "remove-user":
            auth.remove_user(name)
            print(f"User removed: {name}")
            return
        if cmd == "unlock-user":
            auth.unlock_user(name)
            print(f"User unlocked: {name}")
            return
        if cmd == "add-user":
            auth.check_name(name)
        pw = getpass.getpass(f"Password for {name}: ")
        auth.check_password(pw)
        if getpass.getpass("Repeat password: ") != pw:
            sys.exit("Passwords do not match")
        (auth.add_user if cmd == "add-user" else auth.set_password)(name, pw)
    except ValueError as e:
        sys.exit(str(e))
    print(f"{'User added' if cmd == 'add-user' else 'Password changed (all sessions signed out)'}: {name}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["config"]:
        config_cli(sys.argv[2:])
    elif sys.argv[1:2] == ["gen-secret-key"]:
        from watchdock.crypto import new_key
        print(new_key())
    elif sys.argv[1:2] and sys.argv[1] in USER_CMDS:
        user_cli(sys.argv[1], sys.argv[2:])
    else:
        try:
            from watchdock.server import main
        except ImportError as e:
            sys.exit(f"{e}. Install the packages first: pip install -r requirements.txt (see README)")
        main()
