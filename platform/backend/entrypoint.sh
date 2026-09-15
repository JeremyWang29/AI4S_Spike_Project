#!/bin/sh
set -eu
python manage.py check --fail-level ERROR
if [ "${1:-}" = "migrate" ]; then
  exec python manage.py migrate --noinput
fi
python manage.py migrate --check
exec "$@"
