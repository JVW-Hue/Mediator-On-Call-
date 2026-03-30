import logging
from django.db import OperationalError
from django.http import HttpResponse


class DatabaseErrorMiddleware:
    """Catch OperationalError and show a friendly message."""
    
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
                    <h1>System Temporarily Unavailable</h1>
                    <p>We're performing maintenance. Please try again in a few minutes.</p>
                </body>
                </html>
                """,
                status=503,
                content_type='text/html'
            )
