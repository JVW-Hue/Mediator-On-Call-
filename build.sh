#!/usr/bin/env bash
set -e

echo "=== Running migrations ==="
python manage.py migrate --verbosity 2

echo "=== Creating Frank Stanley Admin + Mediator Account ==="
python manage.py shell << 'PYEOF'
from django.contrib.auth import get_user_model
from disputes.models import Mediator

User = get_user_model()

# Delete any existing frankstanley
User.objects.filter(username='frankstanley').delete()

# Create superuser with admin privileges
user = User.objects.create_superuser(
    username='frankstanley',
    email='frank@probonomediation.co.za',
    password='FrankStanley2026!'
)
user.first_name = 'Frank'
user.last_name = 'Stanley'
user.is_staff = True
user.is_superuser = True
user.is_active = True
user.save()

# Create mediator profile
mediator, created = Mediator.objects.get_or_create(
    user=user, 
    defaults={'cell': '0821234567'}
)

# Verify
u = User.objects.get(username='frankstanley')
print("="*50)
print("FRANK STANLEY ACCOUNT CREATED SUCCESSFULLY")
print("="*50)
print(f"Username: frankstanley")
print(f"Password: FrankStanley2026!")
print(f"Email: frank@probonomediation.co.za")
print(f"Full Name: Frank Stanley")
print(f"is_superuser: {u.is_superuser}")
print(f"is_staff: {u.is_staff}")
print(f"is_active: {u.is_active}")
print(f"Has mediator profile: {hasattr(u, 'mediator')}")
print(f"Mediator ID: {mediator.id}")
print("="*50)
PYEOF

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput --clear

echo "=== Creating media directories ==="
mkdir -p media/temp_photos
mkdir -p media/documents

echo "=== Build complete ==="
