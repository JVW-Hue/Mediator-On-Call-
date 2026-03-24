#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

python manage.py migrate --run-syncdb
python manage.py collectstatic --noinput --clear

# Create superuser
echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin', 'admin@example.com', 'admin123') if not User.objects.filter(username='admin').exists() else print('Admin exists')" | python manage.py shell

# Load fixture data
python manage.py loaddata users.json 2>/dev/null || true
python manage.py loaddata mediators.json 2>/dev/null || true
