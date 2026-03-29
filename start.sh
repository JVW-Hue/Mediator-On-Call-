#!/usr/bin/env bash

echo "=== Running migrations ==="
python manage.py migrate || true

echo "=== Creating users ==="
python manage.py shell -c "
from django.contrib.auth import get_user_model
from disputes.models import Mediator
User = get_user_model()

# Create Frank Stanley admin user + mediator
try:
    if not User.objects.filter(username='frankstanley').exists():
        user = User.objects.create_superuser(
            'frankstanley', 
            'frank@probonomediation.co.za', 
            'FrankStanley2026!'
        )
        user.first_name = 'Frank'
        user.last_name = 'Stanley'
        user.save()
    else:
        user = User.objects.get(username='frankstanley')
        user.set_password('FrankStanley2026!')
        user.first_name = 'Frank'
        user.last_name = 'Stanley'
        user.is_staff = True
        user.is_superuser = True
        user.save()
    
    # Create Mediator profile for Frank Stanley
    if not hasattr(user, 'mediator'):
        Mediator.objects.create(user=user, cell='0821234567')
        print('Frank Stanley mediator profile created')
    else:
        print('Frank Stanley mediator profile exists')
    
    print('Frank Stanley account ready - frankstanley / FrankStanley2026!')
except Exception as e:
    print(f'Error: {e}')

# Create JVW mediator user
try:
    if not User.objects.filter(username='JVW').exists():
        user = User.objects.create_user('JVW', 'jvw@probonomediation.co.za', 'JVW123')
        user.is_staff = True
        user.save()
    else:
        user = User.objects.get(username='JVW')
        user.set_password('JVW123')
        user.is_staff = True
        user.save()
    
    if not hasattr(user, 'mediator'):
        Mediator.objects.create(user=user, cell='0000000000')
        print('Mediator JVW created')
    else:
        print('Mediator JVW exists')
except Exception as e:
    print(f'Error JVW: {e}')

# Additional admin user (backup)
try:
    if not User.objects.filter(username='mediatoradmin').exists():
        User.objects.create_superuser('mediatoradmin', 'mediator@probonomediation.co.za', 'Mediator@2026')
        print('Backup admin created')
    else:
        admin = User.objects.get(username='mediatoradmin')
        admin.set_password('Mediator@2026')
        admin.save()
except Exception as e:
    print(f'Admin error (non-critical): {e}')
" || true

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput --clear || true

echo "=== Starting server ==="
gunicorn mediators_on_call.wsgi --bind 0.0.0.0:${PORT:-10000} --config gunicorn.conf.py