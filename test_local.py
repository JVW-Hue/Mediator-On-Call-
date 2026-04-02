import requests
import re

print("=== Local Login Test ===")

# Create a session to persist cookies
s = requests.Session()

# Get login page to obtain CSRF token
print("1. Fetching login page...")
try:
    login_page = s.get('http://127.0.0.1:8080/login/', timeout=10)
    print(f'   Status: {login_page.status_code}')
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
        exit(1)

# Now attempt login
login_data = {
    'username': 'JVW',
    'password': 'JVW123',
    'csrfmiddlewaretoken': csrftoken
}
print(f"\n3. Attempting login with username: JVW")

try:
    login_response = s.post(
        'http://127.0.0.1:8080/login/', 
        data=login_data, 
        headers={'Referer': 'http://127.0.0.1:8080/login/'},
        timeout=10
    )
    print(f'   Status: {login_response.status_code}')
    print(f'   URL: {login_response.url}')
    
    if login_response.status_code == 200 and 'dashboard' in login_response.url:
        print('   SUCCESS: Login worked!')
    elif login_response.status_code == 302:
        print(f'   REDIRECT: Login redirected to: {login_response.headers.get("Location", "unknown")}')
    else:
        print('   FAILED: Login failed')
        print(f'   Response text preview: {login_response.text[:500]}')
        
except Exception as e:
    print(f'   ERROR during POST: {e}')
