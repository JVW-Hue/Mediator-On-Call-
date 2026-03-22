"""
WSGI config for mediators_on_call project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import logging

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')

logger = logging.getLogger(__name__)

def run_migrations():
    """Run database migrations on startup."""
    try:
        from django.core.management import call_command
        
        # For SQLite, we can just run migrations. It will create the database file if it doesn't exist.
        logger.info("Running database migrations...")
        call_command('migrate', '--run-syncdb', verbosity=2)
        logger.info("Migrations complete")
        return True
    except Exception as e:
        logger.error(f"Migration error: {e}", exc_info=True)
        return False

# Run migrations before starting
# Note: This runs in the main process before forking workers (in Gunicorn).
# If we are in a Gunicorn environment with multiple workers, each worker will run this.
# However, running migrations multiple times is safe because Django's migration system is atomic.
run_migrations()

application = get_wsgi_application()
