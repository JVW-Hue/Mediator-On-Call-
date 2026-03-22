"""
WSGI config for mediators_on_call project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import sys
import logging

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')

# Run migrations on startup
if 'migrate' not in sys.argv:
    try:
        from django.core.management import call_command
        logging.info("Running migrations on startup...")
        call_command('migrate', '--run-syncdb', verbosity=0)
        logging.info("Migrations complete")
    except Exception as e:
        logging.error(f"Migration error: {e}")

application = get_wsgi_application()
