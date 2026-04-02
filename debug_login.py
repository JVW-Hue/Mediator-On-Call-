import os
import sys
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')
sys.path.insert(0, os.getcwd())

try:
    django.setup()
    print("Django setup successful")
except Exception as e:
    print(f"Django setup failed: {e}")
    sys.exit(1)

# Test database connection
try:
    from django.db import connection
    cursor = connection.cursor()
    cursor.execute("SELECT 1")
    print("Database connection successful")
except Exception as e:
    print(f"Database connection failed: {e}")
    sys.exit(1)

# Check if auth_user table exists
try:
    from django.db import connection
    cursor = connection.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='auth_user'
    """)
    result = cursor.fetchone()
    if result:
        print("auth_user table EXISTS")
    else:
        print("auth_user table does NOT exist")
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print("Available tables:", [t[0] for t in tables])
except Exception as e:
    print(f"Error checking tables: {e}")

# Try to import User model
try:
    from django.contrib.auth import get_user_model
    User = get_user_model()
    print("User model imported successfully")
    print("User model:", User)
    print("User model table:", User._meta.db_table)
except Exception as e:
    print(f"Error importing User model: {e}")
    import traceback
    traceback.print_exc()