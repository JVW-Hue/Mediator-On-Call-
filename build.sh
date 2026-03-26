#!/usr/bin/env bash
set -e

echo "=== Running migrations ==="
python manage.py migrate

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
