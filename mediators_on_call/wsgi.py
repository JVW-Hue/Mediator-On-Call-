"""
WSGI config for mediators_on_call project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import logging
import sys

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')

logger = logging.getLogger(__name__)

# Configure logging to stdout for Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    stream=sys.stdout
)

def run_migrations():
    """Run database migrations on startup."""
    try:
        from django.core.management import call_command
        
        logger.info("=== Starting database migration process ===")
        
        # Ensure the database directory exists
        from django.conf import settings
        db_path = settings.DATABASES['default']['NAME']
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            logger.info(f"Creating database directory: {db_dir}")
            os.makedirs(db_dir, exist_ok=True)
        
        logger.info(f"Database path: {db_path}")
        logger.info("Running database migrations...")
        
        # Run migrate with fake_initial to handle existing databases safely
        call_command('migrate', '--run-syncdb', verbosity=2)
        
        logger.info("=== Database migrations complete ===")
        return True
    except Exception as e:
        logger.error(f"Migration error: {e}", exc_info=True)
        return False

def ensure_database():
    """Ensure database exists and is initialized."""
    try:
        from django.core.management import call_command
        from django.db import connection
        
        # Check if we can connect to the database
        connection.ensure_connection()
        logger.info("Database connection successful")
        
        # Check if tables exist
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='django_migrations'")
            if cursor.fetchone():
                logger.info("Database already has migrations table")
            else:
                logger.info("Database exists but needs migrations")
                run_migrations()
                
    except Exception as e:
        logger.warning(f"Database check failed: {e}")
        logger.info("Will run migrations to create database...")
        run_migrations()

# Run migrations before starting
run_migrations()

application = get_wsgi_application()
