import urllib.request
import urllib.parse
import json
import time
import sys
import os
import ssl

CLIENT_ID = "178c6fc778ccc68e1d6a"
INTERVAL = 5

# Safe fallback for systems with SSL issues, but tries standard verification first
def get_ssl_context():
    try:
        # Standard context with system certs
        return ssl.create_default_context()
    except Exception:
        # Fallback to unverified context if it fails
        return ssl._create_unverified_context()

context = get_ssl_context()

def load_device_code(default_code=""):
    device_code = default_code
    if os.path.exists("auth_status.json"):
        try:
            with open("auth_status.json", "r") as f:
                auth_data = json.load(f)
                if "device_code" in auth_data:
                    device_code = auth_data["device_code"]
        except Exception:
            pass
    return device_code

def get_token(device_code):
    if not device_code:
        print("Error: No device code provided. Please run github_device_auth.py first.")
        sys.exit(1)
        
    print("Waiting for your authorization on GitHub...")
    url = "https://github.com/login/oauth/access_token"
    data = {
        "client_id": CLIENT_ID,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
    }
    encoded_data = urllib.parse.urlencode(data).encode("utf-8")
    
    while True:
        req = urllib.request.Request(url, data=encoded_data, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, context=context) as response:
                res = json.loads(response.read().decode())
        except Exception as e:
            print("Error polling token:", e)
            time.sleep(INTERVAL)
            continue
            
        if "access_token" in res:
            print("Successfully authenticated!")
            return res["access_token"]
        elif res.get("error") == "authorization_pending":
            time.sleep(INTERVAL)
        elif res.get("error") == "slow_down":
            time.sleep(INTERVAL + 5)
        else:
            print("Authentication failed or expired:", res)
            sys.exit(1)

def github_api_request(method, url, token, data=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Label-Studio-Monitor-App"
    }
    encoded_data = json.dumps(data).encode("utf-8") if data else None
    
    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=context) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode()
        print(f"HTTP Error {e.code}: {err_msg}")
        return None
