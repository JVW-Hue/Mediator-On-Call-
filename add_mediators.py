#!/usr/bin/env python
"""Script to import mediators from Excel file into the database."""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mediators_on_call.settings')
django.setup()

from django.contrib.auth import get_user_model
from disputes.models import Mediator
import openpyxl

User = get_user_model()

def clean_phone(phone):
    """Clean phone number - remove spaces and ensure format."""
    if not phone:
        return ''
    phone = str(phone).strip()
    # Remove spaces
    phone = phone.replace(' ', '').replace('-', '')
    # Remove .0 at end if present
    if phone.endswith('.0'):
        phone = phone[:-2]
    return phone

def clean_email(email):
    """Clean email address."""
    if not email:
        return ''
    return str(email).strip().lower()

def import_mediators():
    filepath = 'Mediators UPDATED MEDIATORS PANEL. 5 JULY 2024.xlsx'
    
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return
    
    wb = openpyxl.load_workbook(filepath)
    ws = wb.active
    
    created_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        name = row[0]  # Name (first name)
        email = row[1]  # Email
        phone = row[2]  # Phone
        surname = row[3]  # Surname
        
        # Skip empty rows
        if not name:
            skipped_count += 1
            continue
        
        # Clean data
        first_name = str(name).strip() if name else ''
        last_name = str(surname).strip() if surname else ''
        email = clean_email(email)
        phone = clean_phone(phone)
        
        # Generate username from name
        username = f"{first_name.lower()}.{last_name.lower()}".replace(' ', '').replace("'", '')[:150]
        # Clean username of special characters
        username = ''.join(c for c in username if c.isalnum() or c == '.')
        
        if not email:
            email = f"{username}@placeholder.com"
        
        try:
            # Check if user exists by email
            user = None
            if email:
                try:
                    user = User.objects.get(email=email)
                    # Update user info
                    user.first_name = first_name
                    user.last_name = last_name
                    user.save()
                    updated_count += 1
                except User.DoesNotExist:
                    pass
            
            if not user:
                # Check by username
                try:
                    user = User.objects.get(username=username)
                    user.first_name = first_name
                    user.last_name = last_name
                    user.email = email
                    user.save()
                    updated_count += 1
                except User.DoesNotExist:
                    # Create new user
                    # Ensure username is unique
                    base_username = username
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}{counter}"[:150]
                        counter += 1
                    
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        password='Mediator2024!',  # Default password
                    )
                    created_count += 1
            
            # Create or update mediator profile
            mediator, created = Mediator.objects.update_or_create(
                user=user,
                defaults={'cell': phone or '0000000000'}
            )
            
            status = 'CREATED' if created else 'UPDATED'
            print(f"{status}: {first_name} {last_name} - {email} - {phone}")
            
        except Exception as e:
            error_count += 1
            print(f"ERROR row {row_num}: {first_name} {last_name} - {e}")
    
    print(f"\n=== IMPORT COMPLETE ===")
    print(f"Created: {created_count}")
    print(f"Updated: {updated_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Errors: {error_count}")

if __name__ == '__main__':
    import_mediators()
