import aiohttp
import asyncio
import yarl
import os
import urllib.parse

# Load environment variables from .env
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ[k.strip()] = v.strip()

EMAIL = os.environ.get("LABEL_STUDIO_EMAIL", "student@yncjzy.com")
PASSWORD = os.environ.get("LABEL_STUDIO_PASSWORD", "1q2w3e4r")

async def main():
    ip = '10.74.196.8'
    port = 8080
    base = f'http://{ip}:{port}'
    login_url = f'{base}/user/login/'
    projects_url = f'{base}/api/projects/'

    # Approach 1: dict data (application/x-www-form-urlencoded)
    print("=== Approach 1: dict data ===")
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        async with session.get(login_url) as r:
            html = await r.text()
            print("GET login status:", r.status, "final URL:", r.url)
        
        url_obj = yarl.URL(base)
        csrf = jar.filter_cookies(url_obj).get('csrftoken')
        print("Cookie CSRF:", csrf.value if csrf else 'NONE')
        
        data = {
            'csrfmiddlewaretoken': csrf.value,
            'email': EMAIL,
            'password': PASSWORD,
        }
        headers = {'Referer': login_url, 'Origin': base}
        
        async with session.post(login_url, data=data, headers=headers, allow_redirects=False) as r:
            print("POST status:", r.status, "Location:", r.headers.get('Location', 'none'))
            if r.status == 200:
                text = await r.text()
                if "don" in text:
                    print("FAILED: credentials mismatch")
                    
    # Approach 2: raw string with manual encoding
    print("\n=== Approach 2: raw URL-encoded string ===")
    jar2 = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar2) as session:
        async with session.get(login_url) as r:
            await r.text()
        
        url_obj = yarl.URL(base)
        csrf = jar2.filter_cookies(url_obj).get('csrftoken')
        
        encoded_email = urllib.parse.quote(EMAIL)
        encoded_password = urllib.parse.quote(PASSWORD)
        body = f'csrfmiddlewaretoken={csrf.value}&email={encoded_email}&password={encoded_password}'
        headers = {
            'Referer': login_url,
            'Origin': base,
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        
        async with session.post(login_url, data=body, headers=headers, allow_redirects=False) as r:
            print("POST status:", r.status, "Location:", r.headers.get('Location', 'none'))
            if r.status == 302:
                print("SUCCESS!")
                async with session.get(projects_url) as r2:
                    print("Projects status:", r2.status)
                    if r2.status == 200:
                        import json
                        d = await r2.json()
                        if isinstance(d, dict) and 'results' in d:
                            for p in d['results'][:3]:
                                print(f"  Project: {p.get('title')} (id={p.get('id')})")
                        elif isinstance(d, list):
                            for p in d[:3]:
                                print(f"  Project: {p.get('title')} (id={p.get('id')})")
            elif r.status == 200:
                text = await r.text()
                if "don" in text:
                    print("FAILED: credentials mismatch")

    # Approach 3: JSON login via X-CSRFToken header
    print("\n=== Approach 3: JSON + X-CSRFToken ===")
    jar3 = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar3) as session:
        async with session.get(login_url) as r:
            await r.text()
        
        url_obj = yarl.URL(base)
        csrf = jar3.filter_cookies(url_obj).get('csrftoken')
        
        import json
        payload = json.dumps({'email': EMAIL, 'password': PASSWORD})
        headers = {
            'Referer': login_url,
            'X-CSRFToken': csrf.value,
            'Content-Type': 'application/json',
        }
        
        async with session.post(login_url, data=payload, headers=headers, allow_redirects=False) as r:
            print("POST status:", r.status, "Location:", r.headers.get('Location', 'none'))
            if r.status == 302:
                print("SUCCESS!")
            elif r.status == 200:
                text = await r.text()
                if "don" in text:
                    print("FAILED: credentials mismatch")
                else:
                    print("Response:", text[:200])

    # Approach 4: use aiohttp.FormData explicitly
    print("\n=== Approach 4: FormData (multipart) ===")
    jar4 = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar4) as session:
        async with session.get(login_url) as r:
            await r.text()
        
        url_obj = yarl.URL(base)
        csrf = jar4.filter_cookies(url_obj).get('csrftoken')
        
        form = aiohttp.FormData()
        form.add_field('csrfmiddlewaretoken', csrf.value)
        form.add_field('email', EMAIL)
        form.add_field('password', PASSWORD)
        
        headers = {'Referer': login_url, 'Origin': base}
        
        async with session.post(login_url, data=form, headers=headers, allow_redirects=False) as r:
            print("POST status:", r.status, "Location:", r.headers.get('Location', 'none'))
            if r.status == 302:
                print("SUCCESS!")
            elif r.status == 200:
                text = await r.text()
                if "don" in text:
                    print("FAILED: credentials mismatch")

if __name__ == '__main__':
    asyncio.run(main())
