"""
WSGI config for mediators_on_call project.
"""

import os
import sys
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')

# Run migrations and create tables when app starts
try:
    from django.core.management import call_command
    from django.db import connection
    
    print("Running migrations on startup...")
    call_command('migrate', '--noinput', verbosity=0)
    print("Migrations completed")
    
    # Create users
    try:
        from django.contrib.auth import get_user_model
        from disputes.models import Mediator
        User = get_user_model()
        
        users_data = [
            ('frankstanley', 'frank@probonomediation.co.za', 'Frank', 'Stanley', 'FrankStanley2026!'),
            ('JVW', 'jvw@probonomediation.co.za', '', '', 'JVW123'),
        ]
        for uname, email, first, last, pwd in users_data:
            u, _ = User.objects.get_or_create(
                username=uname,
                defaults={'email': email, 'first_name': first, 'last_name': last, 'is_staff': True, 'is_active': True}
            )
            u.set_password(pwd)
            u.save()
            Mediator.objects.get_or_create(user=u, defaults={'cell': '0000000000'})
        print("Users created/updated")
    except Exception as e:
        print(f"User creation error: {e}")
except Exception as e:
    print(f"Startup error: {e}")
    import traceback
    traceback.print_exc()

application = get_wsgi_application()
