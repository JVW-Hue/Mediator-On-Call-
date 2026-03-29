from django.apps import AppConfig
from django.contrib.auth import get_user_model


class DisputesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'disputes'

    def ready(self):
        self.create_admin_user()

    @staticmethod
    def create_admin_user():
        try:
            User = get_user_model()
            from disputes.models import Mediator

            username = 'frankstanley'
            password = 'FrankStanley2026!'

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': 'frank@probonomediation.co.za',
                    'first_name': 'Frank',
                    'last_name': 'Stanley',
                    'is_staff': True,
                    'is_superuser': True,
                }
            )
            user.set_password(password)
            user.is_staff = True
            user.is_superuser = True
            user.save()

            if not hasattr(user, 'mediator'):
                Mediator.objects.get_or_create(user=user, defaults={'cell': '0821234567'})

            print(f"Admin user '{username}' ready - password: {password}")
        except Exception as e:
            print(f"Admin user creation: {e}")
