#!/usr/bin/env bash
set -o errexit

python manage.py migrate --run-syncdb
python manage.py collectstatic --noinput

# Create superuser if it doesn't exist
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('Superuser created: admin / admin123')
else:
    print('Superuser already exists')
"

# Load mediator data if files exist
if [ -f users.json ]; then
    python manage.py loaddata users.json || true
fi
if [ -f mediators.json ]; then
    python manage.py loaddata mediators.json || true
fi
