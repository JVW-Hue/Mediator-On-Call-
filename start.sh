#!/usr/bin/env bash
set -e

echo "=== Running migrations ==="
python manage.py migrate --noinput
echo "=== Migration completed ==="

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
