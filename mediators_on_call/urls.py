from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.db import connection

from dashboard.views import CustomLoginView, no_access

def health_check(request):
    try:
        # Test database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        # Check if auth_user table exists
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auth_user'")
            else:
                cursor.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE tablename = 'auth_user'")
            table_exists = cursor.fetchone() is not None
        
        from django.conf import settings
        db_name = connection.settings_dict.get("NAME", "unknown")
        # Convert PosixPath to string if needed
        if hasattr(db_name, '__fspath__'):
            db_name = str(db_name)
        
        db_info = {
            "vendor": connection.vendor,
            "name": db_name,
            "user": connection.settings_dict.get("USER", "unknown"),
            "auth_user_exists": table_exists,
        }
        
        if not table_exists:
            return JsonResponse({"status": "error", "database": "auth_user table missing", "db_info": db_info}, status=500)
        
        return JsonResponse({"status": "ok", "database": "connected", "db_info": db_info})
    except Exception as e:
        import traceback
        return JsonResponse({"status": "error", "database": str(e), "trace": traceback.format_exc()}, status=500)

def run_migrations(request):
    """Run migrations on demand"""
    try:
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('migrate', '--noinput', stdout=out)
        return JsonResponse({"status": "ok", "output": out.getvalue()})
    except Exception as e:
        import traceback
        return JsonResponse({"status": "error", "error": str(e), "trace": traceback.format_exc()}, status=500)

def debug_env(request):
    """Debug endpoint to check environment variables"""
    import os
    from django.conf import settings
    
    db_url = os.environ.get('DATABASE_URL', 'NOT SET')
    # Mask the password
    if db_url and '@' in db_url:
        parts = db_url.split('@')
        user_pass = parts[0].split('://')
        if len(user_pass) > 1 and ':' in user_pass[1]:
            user_pass[1] = '****'
        parts[0] = '://'.join(user_pass)
        db_url = '@'.join(parts)
    
    return JsonResponse({
        "DATABASE_URL": db_url,
        "DEBUG": settings.DEBUG,
        "ALLOWED_HOSTS": settings.ALLOWED_HOSTS,
    })

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("run-migrations/", run_migrations, name="run_migrations"),
    path("debug-env/", debug_env, name="debug_env"),
    path("admin/", admin.site.urls),
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("no-access/", no_access, name="no_access"),
    path("dashboard/", include("dashboard.urls")),
    path("", include("disputes.urls")),
]

# Serve media files
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
