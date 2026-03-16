import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mediators_on_call.settings")

app = Celery("mediators_on_call")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
