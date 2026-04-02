#!/usr/bin/env bash
set -e

echo "=== Environment Check ==="
echo "DATABASE_URL is set: [[[ ${DATABASE_URL:-EMPTY} ]]]"
echo "DEBUG is set: [[[ ${DEBUG:-EMPTY} ]]]"

echo "=== Running migrations ==="
python manage.py migrate --noinput --verbosity=2
echo "=== Migration completed ==="

echo "=== Checking database connection ==="
python manage.py shell -c "
import os
print('DATABASE_URL from env:', os.environ.get('DATABASE_URL', 'NOT SET')[:80] + '...' if os.environ.get('DATABASE_URL') and len(os.environ.get('DATABASE_URL', '')) > 80 else os.environ.get('DATABASE_URL', 'NOT SET'))
from django.db import connection
print('Database vendor:', connection.vendor)
print('Database name:', connection.settings_dict.get('NAME', 'unknown'))
print('Database user:', connection.settings_dict.get('USER', 'unknown'))
"

echo "=== Checking if auth_user table exists ==="
python manage.py shell -c "
from django.db import connection
cursor = connection.cursor()
if connection.vendor == 'sqlite':
    cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='auth_user'\")
else:
    cursor.execute(\"SELECT tablename FROM pg_catalog.pg_tables WHERE tablename = 'auth_user'\")
result = cursor.fetchone()
if result:
    print('auth_user table EXISTS')
else:
    print('auth_user table does NOT exist')
"

echo "=== Counting tables ==="
python manage.py shell -c "
from django.db import connection
cursor = connection.cursor()
if connection.vendor == 'sqlite':
    cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
else:
    cursor.execute(\"SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'\")
tables = cursor.fetchall()
print('Number of tables:', len(tables))
print('Tables:', [t[0] for t in tables[:20]])
"

echo "=== Ensuring users exist ==="
python manage.py shell << 'PYEOF'
from django.contrib.auth import get_user_model
from disputes.models import Mediator

User = get_user_model()

users = [
    dict(username='frankstanley', email='frank@probonomediation.co.za',
         first_name='Frank', last_name='Stanley', password='FrankStanley2026!', is_staff=True),
    dict(username='JVW', email='jvw@probonomediation.co.za',
         password='JVW123', is_staff=True),
]

for udata in users:
    pw = udata.pop('password')
    obj, created = User.objects.get_or_create(username=udata['username'], defaults=udata)
    obj.set_password(pw)
    obj.is_active = True
    obj.save()
    Mediator.objects.get_or_create(user=obj, defaults={'cell': '0000000000'})
    print(('Created' if created else 'Updated') + ': ' + obj.username)
PYEOF

echo "=== Starting gunicorn ==="
exec gunicorn mediators_on_call.wsgi --bind 0.0.0.0:${PORT:-10000} --workers 1 --timeout 120
