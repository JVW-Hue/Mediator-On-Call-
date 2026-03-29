#!/usr/bin/env bash
set -e

echo "=== Running migrations ==="
python manage.py migrate --verbosity 2

echo "=== Creating frankstanley admin user ==="
python manage.py shell << 'PYEOF'
from django.contrib.auth import get_user_model
from disputes.models import Mediator

User = get_user_model()

# Delete any existing frankstanley
User.objects.filter(username='frankstanley').delete()

# Create superuser
user = User.objects.create_superuser(
    username='frankstanley',
    email='frank@probonomediation.co.za',
    password='FrankStanley2026!'
)
user.first_name = 'Frank'
user.last_name = 'Stanley'
user.save()

# Create mediator profile (user + cell only)
Mediator.objects.get_or_create(user=user, defaults={'cell': '0821234567'})

# Verify
u = User.objects.get(username='frankstanley')
print(f"SUCCESS: Created {u.username}")
print(f"Password valid: {u.check_password('FrankStanley2026!')}")
print(f"is_superuser: {u.is_superuser}")
print(f"is_staff: {u.is_staff}")
print(f"Has mediator: {hasattr(u, 'mediator')}")
PYEOF

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput --clear

echo "=== Creating media directories ==="
mkdir -p media/temp_photos
mkdir -p media/documents

echo "=== Build complete ==="
