#!/usr/bin/env bash
set -e

exec gunicorn mediators_on_call.wsgi --bind 0.0.0.0:${PORT:-10000} --workers 1 --timeout 120
