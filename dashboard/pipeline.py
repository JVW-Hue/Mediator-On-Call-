"""
Social Auth pipeline to sync Keycloak roles with Django user permissions.
"""


def set_keycloak_roles(backend, user, response, *args, **kwargs):
    """Extract roles from Keycloak token and set Django user flags."""
    if backend.name == "keycloak":
        # Get roles from the OAuth extra_data
        extra_data = kwargs.get("response", {}) or {}
        access_token = extra_data.get("access_token", {})

        if isinstance(access_token, str):
            import json
            try:
                access_token = json.loads(access_token)
            except (json.JSONDecodeError, TypeError):
                access_token = {}

        # Check for Keycloak client roles
        resource_access = access_token.get("resource_access", {})
        client_roles = resource_access.get("django-app", {}).get("roles", [])

        # Check for realm roles
        realm_access = access_token.get("realm_access", {})
        realm_roles = realm_access.get("roles", [])

        all_roles = client_roles + realm_roles

        # Set Django user flags based on Keycloak roles
        if "admin" in all_roles or "staff" in all_roles:
            user.is_staff = True
        if "superadmin" in all_roles:
            user.is_superuser = True
        user.save()
