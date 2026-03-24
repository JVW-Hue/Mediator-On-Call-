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

# Run migrations and setup on startup
try:
    from django.core.management import call_command
    import django
    django.setup()
    
    logger.info("Running database migrations...")
    call_command('migrate', '--run-syncdb', verbosity=0)
    logger.info("Migrations complete")
    
    # Create superuser using management command
    logger.info("Creating superuser...")
    call_command('create_superuser')
    
    # Load fixture data if users are less than 10
    from django.contrib.auth import get_user_model
    User = get_user_model()
    if User.objects.count() < 10:
        try:
            from pathlib import Path
            base_dir = Path(__file__).resolve().parent.parent
            
            users_file = base_dir / 'users.json'
            if users_file.exists():
                logger.info("Loading users...")
                call_command('loaddata', str(users_file), verbosity=0)
            
            mediators_file = base_dir / 'mediators.json'
            if mediators_file.exists():
                logger.info("Loading mediators...")
                call_command('loaddata', str(mediators_file), verbosity=0)
            
            logger.info("Fixture data loaded")
        except UnicodeDecodeError as e:
            logger.warning(f"Encoding error loading fixtures (data may not be loaded): {e}")
        except Exception as e:
            logger.error(f"Error loading fixtures: {e}")
            
except Exception as e:
    logger.error(f"Startup setup error: {e}")

application = get_wsgi_application()
