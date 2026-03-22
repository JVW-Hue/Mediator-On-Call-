"""
WSGI config for mediators_on_call project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import logging
import json
from pathlib import Path

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
                
                # Check if we need to load fixture data
                from django.contrib.auth import get_user_model
                User = get_user_model()
                if User.objects.count() < 10:
                    logger.info("Loading mediator data...")
                    load_mediator_data()
                return True
        
        # Run migrations
        logger.info("Running database migrations...")
        django.setup()
        from django.core.management import call_command
        call_command('migrate', '--run-syncdb', verbosity=1)
        
        # Load fixture data
        logger.info("Loading mediator data...")
        load_mediator_data()
        
        logger.info("Migrations complete")
        return True
        
    except Exception as e:
        logger.error(f"Database setup error: {e}")
        return False

def load_mediator_data():
    """Load mediator users and data from JSON fixtures."""
    try:
        from django.core.management import call_command
        base_dir = Path(__file__).resolve().parent.parent
        
        # Load users first
        users_file = base_dir / 'users.json'
        if users_file.exists():
            logger.info(f"Loading users from {users_file}")
            call_command('loaddata', str(users_file), verbosity=1)
        
        # Load mediators
        mediators_file = base_dir / 'mediators.json'
        if mediators_file.exists():
            logger.info(f"Loading mediators from {mediators_file}")
            call_command('loaddata', str(mediators_file), verbosity=1)
        
        logger.info("Mediator data loaded successfully")
    except Exception as e:
        logger.error(f"Error loading mediator data: {e}")

# Setup database BEFORE gunicorn workers start
setup_database()

application = get_wsgi_application()
