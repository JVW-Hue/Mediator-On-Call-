#!/usr/bin/env bash

set -e

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Creating Frank Stanley admin user ==="
python manage.py shell << 'PYEOF'
from django.contrib.auth import get_user_model
from disputes.models import Mediator

User = get_user_model()

# Delete existing frankstanley if any issues
User.objects.filter(username='frankstanley').delete()

# Create fresh admin user
user = User.objects.create_superuser(
    username='frankstanley',
    email='frank@probonomediation.co.za',
    password='FrankStanley2026!'
)
user.first_name = 'Frank'
user.last_name = 'Stanley'
user.save()

# Create mediator profile
Mediator.objects.get_or_create(user=user, defaults={'cell': '0821234567'})

print(f"SUCCESS: Created frankstanley with password FrankStanley2026!")
print(f"User is_superuser: {user.is_superuser}")
print(f"User is_staff: {user.is_staff}")
PYEOF

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput --clear

echo "=== Starting server ==="
gunicorn mediators_on_call.wsgi --bind 0.0.0.0:${PORT:-10000} --config gunicorn.conf.py
