import requests
import re

# Create a session to persist cookies
s = requests.Session()

# Get login page to obtain CSRF token
print("Fetching login page...")
login_page = s.get('https://mediator-on-call.onrender.com/login/')
print('Login page status:', login_page.status_code)

# Extract CSRF token from cookies
csrftoken = s.cookies.get('csrftoken')
print('CSRF token from cookies:', csrftoken)

# If not in cookies, try to extract from HTML
if not csrftoken:
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login_page.text)
    if match:
        csrftoken = match.group(1)
        print('CSRF token from HTML:', csrftoken)
    else:
        print('Could not find CSRF token')
        exit(1)

# Now attempt login
login_data = {
    'username': 'JVW',
    'password': 'JVW123',
    'csrfmiddlewaretoken': csrftoken
}
print("\nAttempting login with username: JVW")
login_response = s.post('https://mediator-on-call.onrender.com/login/', data=login_data, headers={'Referer': 'https://mediator-on-call.onrender.com/login/'})

print('Login status:', login_response.status_code)
print('Login URL:', login_response.url)

if login_response.status_code == 200 and 'dashboard' in login_response.url:
    print('SUCCESS: Login worked!')
elif login_response.status_code == 302:
    print('REDIRECT: Login redirected to:', login_response.headers.get('Location', 'unknown'))
else:
    print('FAILED: Login failed')
    print('Response text preview:', login_response.text[:500])