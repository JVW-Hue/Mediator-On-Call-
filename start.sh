#!/usr/bin/env bash

echo "=== Starting Mediator on Call ==="

echo "Running migrations..."
python manage.py migrate --noinput || echo "Migration warning (non-fatal)"

echo "Ensuring users exist..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
from disputes.models import Mediator
User = get_user_model()
for udata in [
    {'username':'frankstanley','email':'frank@probonomediation.co.za','first_name':'Frank','last_name':'Stanley','password':'FrankStanley2026!','is_staff':True},
    {'username':'JVW','email':'jvw@probonomediation.co.za','password':'JVW123','is_staff':True},
    {'username':'admin','email':'admin@probonomediation.co.za','first_name':'Admin','password':'Admin2026!','is_staff':True},
]:
    pw = udata.pop('password')
    obj, _ = User.objects.get_or_create(username=udata['username'], defaults=udata)
    obj.set_password(pw)
    obj.is_active = True
    obj.save()
    Mediator.objects.get_or_create(user=obj, defaults={'cell':'0000000000'})
    print('Ready: ' + obj.username)
" || echo "User creation warning (non-fatal)"

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear || echo "Static files warning (non-fatal)"

echo "Starting gunicorn..."
exec gunicorn mediators_on_call.wsgi --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 120
