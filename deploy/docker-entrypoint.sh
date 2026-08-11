#!/bin/sh
# Container entrypoint: apply migrations, then exec the real command.
#
# Migrations run HERE - once, at container start, before the app process
# exists - never at import time and never inside the app's own startup path
# (see `cli/migrate_command.py`'s docstring). An unattended container restart
# must never be able to silently rewrite the schema of a system already
# serving traffic; running it as a separate step before `exec "$@"` is what
# keeps that true.
#
# POSIX sh, not bash: Debian slim's /bin/sh is dash, and this script has
# nothing in it that needs bash.
set -eu

echo "[entrypoint] applying database migrations..."
caps-dash migrate

echo "[entrypoint] starting: $*"
exec "$@"
