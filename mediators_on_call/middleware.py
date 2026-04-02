import logging
from django.db import OperationalError
from django.http import HttpResponse


class DatabaseErrorMiddleware:
    """Catch all errors and show a friendly message."""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger(__name__)

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except OperationalError as e:
            self.logger.error(f"Database error: {e}")
            return HttpResponse(
                """
                <!DOCTYPE html>
                <html>
                <head><title>System Maintenance</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1>Database Setup In Progress</h1>
                    <p>The database is being created. Please refresh in 1 minute.</p>
                    <p><a href="javascript:location.reload()">Refresh Page</a></p>
                </body>
                </html>
                """,
                status=200,
                content_type='text/html'
            )
        except Exception as e:
            self.logger.error(f"Error: {e}")
            return HttpResponse(
                f"""
                <!DOCTYPE html>
                <html>
                <head><title>System Maintenance</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1>System Maintenance</h1>
                    <p>The system is starting up. Please refresh in 1 minute.</p>
                    <p><a href="javascript:location.reload()">Refresh Page</a></p>
                </body>
                </html>
                """,
                status=200,
                content_type='text/html'
            )
