#!/usr/bin/env bash
set -o errexit

echo "Running migrations..."
python manage.py migrate --run-syncdb

# Explicitly apply disputes migrations to ensure all tables exist
python manage.py migrate disputes --noinput 2>/dev/null || python manage.py migrate disputes 0010_tempdisputephoto_disputephoto --fake 2>/dev/null || true

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Creating media directories..."
mkdir -p media/temp_photos
mkdir -p media/documents
chmod -R 755 media
echo "Media directories created"

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
    print(f'Superuser password updated: {username} / {password}')
"

echo "Loading fixture data..."
python manage.py loaddata users.json 2>/dev/null || echo "No users.json or error loading"
python manage.py loaddata mediators.json 2>/dev/null || echo "No mediators.json or error loading"

echo "Build complete!"
