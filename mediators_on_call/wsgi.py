"""
WSGI config for mediators_on_call project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import logging

from django.core.wsgi import get_wsgi_application
from django.db import connection
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')

logger = logging.getLogger(__name__)

def setup_database():
    """Setup database - runs once per gunicorn master process."""
    try:
        connection.ensure_connection()
        
        # Check if migrations have been run
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='django_migrations'
            """)
            if cursor.fetchone():
                logger.info("Database already migrated")
                return True
        
        # Run migrations
        logger.info("Running database migrations...")
        django.setup()
        from django.core.management import call_command
        call_command('migrate', '--run-syncdb', verbosity=1)
        logger.info("Migrations complete")
        return True
        
    except Exception as e:
        logger.error(f"Database setup error: {e}")
        return False

# Setup database BEFORE gunicorn workers start
setup_database()

application = get_wsgi_application()
