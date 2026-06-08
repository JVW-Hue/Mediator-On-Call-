"""
Keycloak Setup Script
Run this AFTER starting Keycloak via Docker:
    docker compose up -d

Then run:
    python setup_keycloak.py
"""
import requests
import sys

KEYCLOAK_URL = "http://localhost:8080"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"
REALM = "mediators-realm"
CLIENT_ID = "django-app"
CLIENT_SECRET = "your-client-secret"


def get_admin_token():
    resp = requests.post(
        f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": ADMIN_USER,
            "password": ADMIN_PASS,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_realm(token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.get(f"{KEYCLOAK_URL}/admin/realms/{REALM}", headers=headers)
    if resp.status_code == 200:
        print(f"  Realm '{REALM}' already exists.")
        return

    resp = requests.post(
        f"{KEYCLOAK_URL}/admin/realms",
        headers=headers,
        json={
            "realm": REALM,
            "enabled": True,
            "registrationAllowed": False,
            "loginWithEmailAllowed": True,
            "duplicateEmailsAllowed": False,
            "resetPasswordAllowed": True,
            "editUsernameAllowed": False,
            "bruteForceProtected": True,
            "permanentLockout": False,
            "maxFailureWaitSeconds": 900,
            "minimumQuickLoginWaitSeconds": 60,
            "waitIncrementSeconds": 60,
            "quickLoginCheckMilliSeconds": 1000,
            "maxDeltaTimeSeconds": 43200,
            "failureFactor": 5,
        },
    )
    if resp.status_code in (200, 201):
        print(f"  Realm '{REALM}' created.")
    else:
        print(f"  Error creating realm: {resp.status_code} {resp.text}")


def create_client(token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.get(
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients?clientId={CLIENT_ID}",
        headers=headers,
    )
    if resp.json():
        print(f"  Client '{CLIENT_ID}' already exists.")
        return

    resp = requests.post(
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients",
        headers=headers,
        json={
            "clientId": CLIENT_ID,
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": False,
            "secret": CLIENT_SECRET,
            "directAccessGrantsEnabled": True,
            "standardFlowEnabled": True,
            "serviceAccountsEnabled": True,
            "redirectUris": [
                "http://localhost:8000/auth/complete/keycloak/",
                "http://127.0.0.1:8000/auth/complete/keycloak/",
            ],
            "webOrigins": [
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            ],
            "defaultClientScopes": ["openid", "profile", "email"],
        },
    )
    if resp.status_code in (200, 201):
        print(f"  Client '{CLIENT_ID}' created.")
    else:
        print(f"  Error creating client: {resp.status_code} {resp.text}")


def create_roles(token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for role_name in ["admin", "staff", "mediator", "superadmin"]:
        resp = requests.get(
            f"{KEYCLOAK_URL}/admin/realms/{REALM}/roles/{role_name}",
            headers=headers,
        )
        if resp.status_code == 200:
            print(f"  Role '{role_name}' already exists.")
            continue
        resp = requests.post(
            f"{KEYCLOAK_URL}/admin/realms/{REALM}/roles",
            headers=headers,
            json={"name": role_name, "description": f"{role_name.title()} role"},
        )
        if resp.status_code in (200, 201):
            print(f"  Role '{role_name}' created.")
        else:
            print(f"  Error creating role '{role_name}': {resp.status_code}")


def create_test_user(token):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    username = "frankstanley"
    resp = requests.get(
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/users?username={username}",
        headers=headers,
    )
    if resp.json():
        print(f"  User '{username}' already exists.")
        return

    resp = requests.post(
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/users",
        headers=headers,
        json={
            "username": username,
            "email": "frank@probonomediation.co.za",
            "firstName": "Frank",
            "lastName": "Stanley",
            "enabled": True,
            "emailVerified": True,
            "credentials": [
                {"type": "password", "value": "FrankStanley2026!", "temporary": False}
            ],
        },
    )
    if resp.status_code in (200, 201):
        print(f"  User '{username}' created (password: FrankStanley2026!).")
        # Assign staff role
        resp = requests.get(
            f"{KEYCLOAK_URL}/admin/realms/{REALM}/users?username={username}",
            headers=headers,
        )
        user_id = resp.json()[0]["id"]
        role_resp = requests.get(
            f"{KEYCLOAK_URL}/admin/realms/{REALM}/roles/staff",
            headers=headers,
        )
        requests.post(
            f"{KEYCLOAK_URL}/admin/realms/{REALM}/users/{user_id}/role-mappings/clients/{_get_client_uuid(token)}",
            headers=headers,
            json=[role_resp.json()],
        )
    else:
        print(f"  Error creating user: {resp.status_code}")


def _get_client_uuid(token):
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients?clientId={CLIENT_ID}",
        headers=headers,
    )
    return resp.json()[0]["id"]


def main():
    print("=" * 60)
    print("  Keycloak Setup for Mediators on Call")
    print("=" * 60)
    print()
    print("Connecting to Keycloak at", KEYCLOAK_URL, "...")

    try:
        token = get_admin_token()
        print("  Connected successfully.\n")
    except Exception as e:
        print(f"\n  ERROR: Cannot connect to Keycloak at {KEYCLOAK_URL}")
        print(f"  Make sure Docker Desktop is running and Keycloak is started:")
        print(f"    docker compose up -d")
        print(f"\n  Details: {e}")
        sys.exit(1)

    print("Creating realm...")
    create_realm(token)
    print()

    print("Creating client...")
    create_client(token)
    print()

    print("Creating roles...")
    create_roles(token)
    print()

    print("Creating test user...")
    create_test_user(token)
    print()

    print("=" * 60)
    print("  Setup complete!")
    print()
    print(f"  Keycloak Admin Console: {KEYCLOAK_URL}")
    print(f"  Admin login: {ADMIN_USER} / {ADMIN_PASS}")
    print(f"  Realm: {REALM}")
    print(f"  Client: {CLIENT_ID}")
    print()
    print("  Test user: frankstanley / FrankStanley2026!")
    print("=" * 60)


if __name__ == "__main__":
    main()
