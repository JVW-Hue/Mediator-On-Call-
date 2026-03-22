import logging
from django.db import OperationalError
from django.http import HttpResponse


class DatabaseErrorMiddleware:
    """Catch OperationalError (e.g., missing tables) and show a friendly message."""
    
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
                <head>
                    <title>System Maintenance</title>
                    <style>
                        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }
                        .container { background: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 500px; margin: 0 auto; }
                        h1 { color: #e74c3c; }
                        p { color: #666; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>System Temporarily Unavailable</h1>
                        <p>We're performing maintenance. Please try again in a few minutes.</p>
                        <p>If this persists, please contact support.</p>
                    </div>
                </body>
                </html>
                """,
                status=503,
                content_type='text/html'
            )
