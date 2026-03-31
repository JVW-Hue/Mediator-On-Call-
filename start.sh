#!/bin/bash
echo "Running migrations..."
python manage.py migrate --noinput
echo "Creating users..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
from disputes.models import Mediator
User = get_user_model()
user, c = User.objects.get_or_create(username='frankstanley', defaults={'email':'frank@probonomediation.co.za','first_name':'Frank','last_name':'Stanley','is_staff':True,'is_active':True})
user.set_password('FrankStanley2026!')
user.save()
Mediator.objects.get_or_create(user=user, defaults={'cell':'0821234567'})
jvw, c = User.objects.get_or_create(username='JVW', defaults={'email':'jvw@probonomediation.co.za','is_staff':True,'is_active':True})
jvw.set_password('JVW123')
jvw.save()
Mediator.objects.get_or_create(user=jvw, defaults={'cell':'0000000000'})
print('Users ready')
"
echo "Starting server..."
gunicorn mediators_on_call.wsgi --bind 0.0.0.0:${PORT:-10000} --timeout 300
