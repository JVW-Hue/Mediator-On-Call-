import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')
import django
django.setup()

import openpyxl
from django.contrib.auth import get_user_model
from disputes.models import Mediator

User = get_user_model()

print("Loading Excel file...")
wb = openpyxl.load_workbook('UPDATED MEDIATORS PANEL. 5 JULY 2024.xlsx')
sheet = wb.active

# Print header to understand columns
headers = [cell.value for cell in sheet[1]]
print("Columns:", headers)
print()

print("Importing mediators...")
count = 0
errors = []

for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
    try:
        name = row[0]
        email = row[1] if row[1] else ''
        phone = row[2] if row[2] else ''
        
        if name and str(name).strip():
            name_str = str(name).strip()
            
            # Create username
            username = name_str.lower().replace(' ', '_').replace('.', '').replace('-', '').replace("'", '')[:30]
            
            # Extract first and last name
            parts = name_str.split()
            first_name = parts[0] if parts else name_str
            last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''
            
            # Use email or create one
            final_email = str(email) if email else f'{username}@mediators.com'
            
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': final_email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'is_staff': True
                }
            )
            if created:
                user.set_password('mediator123')
                user.save()
            
            # Extract phone number (try to get digits only)
            phone_str = ''
            if phone:
                phone_str = ''.join(c for c in str(phone) if c.isdigit())
                if len(phone_str) > 0:
                    phone_str = phone_str[:10]  # Limit to 10 digits
                else:
                    phone_str = ''
            
            med, med_created = Mediator.objects.get_or_create(
                user=user,
                defaults={'cell': phone_str if phone_str else '0820000000'}
            )
            
            status = "NEW" if created else "EXISTS"
            print(f"[{status}] {name_str}")
            count += 1
            
    except Exception as e:
        errors.append(f"Row {row_num}: {str(e)[:80]}")
        print(f"[ERROR] Row {row_num}: {str(e)[:50]}")

print(f"\nTotal mediators imported: {count}")
if errors:
    print(f"Total errors: {len(errors)}")
