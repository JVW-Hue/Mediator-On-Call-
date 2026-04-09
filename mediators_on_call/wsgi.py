"""
WSGI config for mediators_on_call project.
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')

application = get_wsgi_application()

# Run migrations and create users on every startup
try:
    from django.core.management import call_command
    call_command('migrate', '--noinput')
    from django.contrib.auth import get_user_model
    from disputes.models import Mediator
    User = get_user_model()
    for udata in [
         {'username':'frankstanley','email':'frank@probonomediation.co.za','first_name':'Frank','last_name':'Stanley','password':'FrankStanley2026!','is_staff':True, 'is_superuser': True},
        {'username':'JVW','email':'jvw@probonomediation.co.za','password':'JVW123','is_staff':True},
        {'username':'admin','email':'admin@probonomediation.co.za','first_name':'Admin','password':'Admin2026!','is_staff':True},
    ]:
        pw = udata.pop('password')
        obj, _ = User.objects.get_or_create(username=udata['username'], defaults=udata)
        obj.set_password(pw)
        obj.is_active = True
        obj.save()
        Mediator.objects.get_or_create(user=obj, defaults={'cell':'0000000000'})
except Exception:
    pass
