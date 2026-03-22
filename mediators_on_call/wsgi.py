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

def run_migrations():
    """Run database migrations on startup."""
    try:
        from django.core.management import call_command
        from django.db import connection
        from django.db.utils import OperationalError
        
        logger = logging.getLogger(__name__)
        
        # Check if we can connect to the database
        try:
            connection.ensure_connection()
        except OperationalError:
            logger.error("Cannot connect to database - tables may not exist")
            return
        
        # Run migrations
        logger.info("Running database migrations...")
        call_command('migrate', '--run-syncdb', verbosity=1)
        logger.info("Migrations complete")
    except Exception as e:
        logging.error(f"Migration error: {e}")

# Run migrations before starting
run_migrations()

application = get_wsgi_application()
