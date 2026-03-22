"""
WSGI config for mediators_on_call project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import sys
import logging
import time

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')

def run_migrations():
    """Run database migrations on startup with retries."""
    max_retries = 3
    retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        try:
            from django.core.management import call_command
            from django.db import connection
            from django.db.utils import OperationalError
            
            logger = logging.getLogger(__name__)
            
            # Check if we can connect to the database
            try:
                connection.ensure_connection()
            except OperationalError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Database connection failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"Cannot connect to database after {max_retries} attempts: {e}")
                    return False
            
            # Run migrations
            logger.info("Running database migrations...")
            call_command('migrate', '--run-syncdb', verbosity=0)
            logger.info("Migrations complete")
            return True
        except Exception as e:
            logging.error(f"Migration error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                logging.error(f"Migration failed after {max_retries} attempts")
                return False
    return False

# Run migrations before starting
if not run_migrations():
    logging.warning("Migrations did not run successfully, but continuing startup...")

application = get_wsgi_application()
