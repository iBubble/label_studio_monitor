import urllib.request
import urllib.parse
import json
import sys

CLIENT_ID = "178c6fc778ccc68e1d6a"

def get_device_code():
    url = "https://github.com/login/device/code"
    data = json.dumps({"client_id": CLIENT_ID, "scope": "repo"}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Accept": "application/json", "Content-Type": "application/json"})
    
    import ssl
    context = ssl._create_unverified_context()
    
    try:
        with urllib.request.urlopen(req, context=context) as response:
            res = json.loads(response.read().decode())
        
        if "user_code" not in res:
            print("Error getting device code:", res)
            sys.exit(1)
            
        print(f"VERIFICATION_URI: {res['verification_uri']}")
        print(f"USER_CODE: {res['user_code']}")
        print(f"DEVICE_CODE: {res['device_code']}")
        print(f"INTERVAL: {res['interval']}")
        
    except Exception as e:
        print(f"Exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    get_device_code()
