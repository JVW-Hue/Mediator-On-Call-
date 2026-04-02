import requests
import re

print("=== Detailed Login Test ===")

# Create a session to persist cookies
s = requests.Session()

# Get login page to obtain CSRF token
print("1. Fetching login page...")
try:
    login_page = s.get('https://mediator-on-call.onrender.com/login/', timeout=30)
    print(f'   Status: {login_page.status_code}')
    print(f'   Headers: {dict(login_page.headers)}')
except Exception as e:
    print(f'   ERROR: {e}')
    exit(1)

# Extract CSRF token from cookies
csrftoken = s.cookies.get('csrftoken')
print(f'2. CSRF token from cookies: {csrftoken}')

# If not in cookies, try to extract from HTML
if not csrftoken:
    print("   CSRF token not in cookies, searching HTML...")
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login_page.text)
    if match:
        csrftoken = match.group(1)
        print(f'   CSRF token from HTML: {csrftoken}')
    else:
        print('   ERROR: Could not find CSRF token')
        print(f'   HTML preview: {login_page.text[:500]}')
        exit(1)

# Now attempt login
login_data = {
    'username': 'JVW',
    'password': 'JVW123',
    'csrfmiddlewaretoken': csrftoken
}
print(f"\n3. Attempting login with username: JVW")
print(f'   Data: {login_data}')

try:
    login_response = s.post(
        'https://mediator-on-call.onrender.com/login/', 
        data=login_data, 
        headers={'Referer': 'https://mediator-on-call.onrender.com/login/'},
        timeout=30
    )
    print(f'   Status: {login_response.status_code}')
    print(f'   URL: {login_response.url}')
    print(f'   Headers: {dict(login_response.headers)}')
    
    if login_response.status_code == 200 and 'dashboard' in login_response.url:
        print('   SUCCESS: Login worked!')
    elif login_response.status_code == 302:
        print(f'   REDIRECT: Login redirected to: {login_response.headers.get("Location", "unknown")}')
    else:
        print('   FAILED: Login failed')
        print(f'   Response text preview: {login_response.text[:1000]}')
        
except Exception as e:
    print(f'   ERROR during POST: {e}')