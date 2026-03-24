#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

echo "Running migrations..."
python manage.py migrate --run-syncdb

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Creating superuser..."
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('Superuser created: admin / admin123')
else:
    print('Admin user already exists')
"

echo "Loading fixture data..."
python manage.py loaddata users.json 2>/dev/null || echo "No users.json or error loading"
python manage.py loaddata mediators.json 2>/dev/null || echo "No mediators.json or error loading"

echo "Build complete!"
