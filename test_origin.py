import urllib.request as r, urllib.parse as p
import os

# Load environment variables from .env
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ[k.strip()] = v.strip()

EMAIL = os.environ.get("LABEL_STUDIO_EMAIL", "student@yncjzy.com")
PASSWORD = os.environ.get("LABEL_STUDIO_PASSWORD", "1q2w3e4r")

req1 = r.Request('http://10.74.196.8:8080/user/login/')
resp = r.urlopen(req1)
cookie = resp.headers.get('Set-Cookie', '')
csrf = cookie.split('csrftoken=')[1].split(';')[0] if 'csrftoken' in cookie else ''
data = p.urlencode({'csrfmiddlewaretoken': csrf, 'email': EMAIL, 'password': PASSWORD}).encode()

class NoRedir(r.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

opener = r.build_opener(NoRedir)
req2 = r.Request('http://10.74.196.8:8080/user/login/', data=data, method='POST')
req2.add_header('Cookie', f'csrftoken={csrf}')
req2.add_header('Origin', 'null')

try:
    resp2 = opener.open(req2)
    print("FAILED TO REDIRECT:", resp2.getcode())
    print("Is CSRF error?", b"CSRF verification failed" in resp2.read())
except r.HTTPError as e:
    print("STATUS:", e.code)
    print("LOCATION:", e.headers.get('Location'))
