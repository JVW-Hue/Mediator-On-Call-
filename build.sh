#!/usr/bin/env bash
set -e

echo "=== Running migrations ==="
python manage.py migrate --verbosity 2

echo "=== Checking for auth_user table ==="
TABLE_CHECK=$(python manage.py shell -c "from django.db import connection; cursor = connection.cursor(); cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='auth_user';\"); result = cursor.fetchone(); print('FOUND' if result else 'NOT FOUND')")
echo "Auth user table check: $TABLE_CHECK"

if [ "$TABLE_CHECK" != "FOUND" ]; then
    echo "ERROR: auth_user table not found after migrations!"
    echo "Listing tables:"
    python manage.py shell -c "from django.db import connection; cursor = connection.cursor(); cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table';\"); tables = cursor.fetchall(); print('\\n'.join([t[0] for t in tables]))"
    exit 1
fi

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput --clear

echo "=== Creating media directories ==="
mkdir -p media/temp_photos
mkdir -p media/documents

echo "=== Creating users ==="
python manage.py shell -c "
from django.contrib.auth import get_user_model
from disputes.models import Mediator
User = get_user_model()

if not User.objects.filter(username='JVW').exists():
    user = User.objects.create_user('JVW', 'jvw@probonomediation.co.za', 'JVW123')
    user.is_staff = True
    user.save()
    Mediator.objects.create(user=user, name='JVW', email='jvw@probonomediation.co.za', phone='0000000000')
    print('Mediator JVW created')
else:
    user = User.objects.get(username='JVW')
    user.set_password('JVW123')
    user.is_staff = True
    user.save()
    print('Mediator JVW updated')

if not User.objects.filter(username='mediatoradmin').exists():
    User.objects.create_superuser('mediatoradmin', 'mediator@probonomediation.co.za', 'Mediator@2026')
    print('Admin created')
else:
    admin = User.objects.get(username='mediatoradmin')
    admin.set_password('Mediator@2026')
    admin.save()
    print('Admin updated')
"

echo "=== Build complete ==="