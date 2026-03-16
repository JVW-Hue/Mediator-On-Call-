import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')
django.setup()

from disputes.tasks import send_whatsapp
from django.conf import settings

print("=" * 50)
print("TWILIO CONFIGURATION CHECK")
print("=" * 50)
print(f"DEBUG: {settings.DEBUG}")
print(f"TWILIO_ACCOUNT_SID: {'SET' if settings.TWILIO_ACCOUNT_SID else 'NOT SET'}")
print(f"TWILIO_AUTH_TOKEN: {'SET' if settings.TWILIO_AUTH_TOKEN else 'NOT SET'}")
print(f"TWILIO_WHATSAPP_NUMBER: {'SET' if settings.TWILIO_WHATSAPP_NUMBER else 'NOT SET'}")
print("=" * 50)

# Test sending WhatsApp
test_number = input("Enter phone number to test (e.g., +1234567890): ")
test_message = input("Enter test message: ")

print("\nSending WhatsApp...")
try:
    result = send_whatsapp(to=test_number, body=test_message)
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")
