"""Gunicorn settings for T3 Watchdock (started by app.py / bin/t3-watchdock start / Docker).

Exactly ONE worker: the scheduler and the pipeline mail watches run as threads inside the worker process;
a second worker would run every pipeline trigger and notification twice. Concurrency comes from threads.
"""
# Every top-level name here is read as a Gunicorn setting (e.g. "config"), so imports get a leading underscore.
import os as _os

from watchdock import db as _db
from watchdock.core import HOST as _HOST, config as _config

bind = f"{_HOST}:{int(_config().get('port', 8787))}"
_db.close()                         # opened in the master only to read the port; the worker opens its own
workers = 1                         # never more, see above
worker_class = "gthread"
threads = int(_os.environ.get("WATCHDOCK_THREADS", 16))
timeout = 300                       # worker heartbeat; long GitLab / t3monitor calls run in threads
graceful_timeout = 10
keepalive = 5
limit_request_line = 8190
limit_request_fields = 100
accesslog = None                    # requests are not logged (as before); app events go to the Activity log
errorlog = "-"
loglevel = "warning"
proc_name = "t3-watchdock"


def post_worker_init(worker):
    from watchdock.server import start_background
    start_background()


def worker_exit(server, worker):
    from watchdock.server import stop
    stop()
