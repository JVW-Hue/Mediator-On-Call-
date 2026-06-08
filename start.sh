#!/usr/bin/env bash

echo "=== Starting Mediator on Call ==="
exec gunicorn mediators_on_call.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120
