#!/usr/bin/env bash

echo "Running migrations..."
python manage.py migrate --run-syncdb || echo "Migration error (continuing)"

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear || echo "Static files error (continuing)"

echo "Creating media directories..."
mkdir -p media/temp_photos
mkdir -p media/documents
chmod -R 755 media
echo "Media directories created"

echo "Creating JVW mediator user..."
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
try:
    from disputes.models import Mediator
    has_mediator = True
except:
    has_mediator = False
User = get_user_model()
username = 'JVW'
email = 'jvw@probonomediation.co.za'
password = 'JVW123'
if not User.objects.filter(username=username).exists():
    user = User.objects.create_user(username, email, password)
    user.is_staff = True
    user.save()
    if has_mediator:
        Mediator.objects.create(user=user, name='JVW', email=email, phone='0000000000')
    print(f'Mediator created: {username} / {password}')
else:
    user = User.objects.get(username=username)
    user.set_password(password)
    user.is_staff = True
    user.save()
    if has_mediator and not Mediator.objects.filter(user=user).exists():
        Mediator.objects.create(user=user, name='JVW', email=email, phone='0000000000')
    print(f'Mediator updated: {username} / {password}')
" || echo "Error creating JVW user (continuing)"

echo "Creating superuser..."
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
username = 'mediatoradmin'
email = 'mediator@probonomediation.co.za'
password = 'Mediator@2026'
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password)
    print(f'Superuser created: {username} / {password}')
else:
    user = User.objects.get(username=username)
    user.set_password(password)
    user.save()
    print(f'Superuser updated: {username} / {password}')
" || echo "Error creating superuser (continuing)"

echo "Build complete!"
