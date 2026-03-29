#!/usr/bin/env bash

echo "=== Running migrations ==="
python manage.py migrate || true

echo "=== Creating users ==="
python manage.py shell -c "
from django.contrib.auth import get_user_model
from disputes.models import Mediator
User = get_user_model()

# Create Frank Stanley admin user
try:
    if not User.objects.filter(username='frankstanley').exists():
        user = User.objects.create_superuser('frankstanley', 'frank@probonomediation.co.za', 'FrankStanley2026!')
        user.first_name = 'Frank'
        user.last_name = 'Stanley'
        user.email = 'frank@probonomediation.co.za'
        user.is_staff = True
        user.is_superuser = True
        user.save()
        print('Admin user Frank Stanley created')
    else:
        user = User.objects.get(username='frankstanley')
        user.set_password('FrankStanley2026!')
        user.first_name = 'Frank'
        user.last_name = 'Stanley'
        user.email = 'frank@probonomediation.co.za'
        user.is_staff = True
        user.is_superuser = True
        user.save()
        print('Admin user Frank Stanley updated')
except Exception as e:
    print(f'Error creating Frank Stanley: {e}')

# Create JVW user
try:
    if not User.objects.filter(username='JVW').exists():
        user = User.objects.create_user('JVW', 'jvw@probonomediation.co.za', 'JVW123')
        user.is_staff = True
        user.save()
        try:
            Mediator.objects.create(user=user, name='JVW', email='jvw@probonomediation.co.za', phone='0000000000')
        except Exception as e:
            print(f'Mediator error: {e}')
        print('Mediator JVW created')
    else:
        user = User.objects.get(username='JVW')
        user.set_password('JVW123')
        user.is_staff = True
        user.save()
        print('Mediator JVW updated')
except Exception as e:
    print(f'Error creating JVW: {e}')

# Create admin user
try:
    if not User.objects.filter(username='mediatoradmin').exists():
        User.objects.create_superuser('mediatoradmin', 'mediator@probonomediation.co.za', 'Mediator@2026')
        print('Admin created')
    else:
        admin = User.objects.get(username='mediatoradmin')
        admin.set_password('Mediator@2026')
        admin.save()
        print('Admin updated')
except Exception as e:
    print(f'Error creating admin: {e}')
" || true

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput --clear || true

echo "=== Starting server ==="
gunicorn mediators_on_call.wsgi --bind 0.0.0.0:${PORT:-10000} --config gunicorn.conf.py