from django.shortcuts import render


def custom_permission_denied(request, exception=None):
    """Custom 403 error page - Access Denied"""
    return render(request, '403.html', {
        'exception': 'You do not have permission to access this page.',
    }, status=403)


def custom_page_not_found(request, exception=None):
    """Custom 404 error page - Page Not Found"""
    return render(request, '404.html', {
        'exception': 'The page you are looking for does not exist.',
    }, status=404)


def custom_server_error(request):
    """Custom 500 error page - Server Error"""
    return render(request, '500.html', {
        'exception': 'Something went wrong. Please try again later.',
    }, status=500)
