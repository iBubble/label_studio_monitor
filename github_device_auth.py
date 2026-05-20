import urllib.request
import urllib.parse
import json
import sys

# GitHub CLI Client ID
CLIENT_ID = "178c6fc778ccc68e1d6a"

def get_device_code():
    url = "https://github.com/login/device/code"
    data = {
        "client_id": CLIENT_ID,
        "scope": "repo"
    }
    encoded_data = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded_data,
        headers={"Accept": "application/json", "Content-Type": "application/json"}
    )
    
    try:
        import ssl
        try:
            context = ssl.create_default_context()
        except Exception:
            context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, context=context) as response:
            res = json.loads(response.read().decode())
    except Exception as e:
        print("Error getting device code:", e)
        sys.exit(1)
        
    if "user_code" not in res:
        print("Error getting device code:", res)
        sys.exit(1)
        
    print(f"VERIFICATION_URI: {res['verification_uri']}")
    print(f"USER_CODE: {res['user_code']}")
    
    with open("auth_status.json", "w") as f:
        json.dump(res, f)

if __name__ == "__main__":
    get_device_code()
