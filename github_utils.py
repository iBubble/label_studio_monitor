import urllib.request
import urllib.parse
import json
import time
import sys
import os
import ssl

CLIENT_ID = "178c6fc778ccc68e1d6a"
INTERVAL = 5
TOKEN_CACHE_FILE = "auth_status.json"

# Safe fallback for systems with SSL issues, but tries standard verification first
def get_ssl_context():
    try:
        # Standard context with system certs
        return ssl.create_default_context()
    except Exception:
        # Fallback to unverified context if it fails
        return ssl._create_unverified_context()

context = get_ssl_context()

def _load_cache():
    """加载本地缓存的 auth_status.json"""
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_cache(data):
    """将认证数据写入本地缓存"""
    try:
        with open(TOKEN_CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Warning: 无法写入缓存文件: {e}")

def _verify_token(token):
    """验证 Token 是否仍然有效（调用 GitHub /user 接口）"""
    try:
        req = urllib.request.Request(
            "https://api.github.com/user",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "Label-Studio-Monitor-App"
            }
        )
        with urllib.request.urlopen(req, context=context) as response:
            if response.status == 200:
                return True
    except Exception:
        pass
    return False

def _request_device_code():
    """向 GitHub 请求新的 device_code（自动化，无需用户手动运行脚本）"""
    url = "https://github.com/login/device/code"
    data = json.dumps({"client_id": CLIENT_ID, "scope": "repo"}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, context=context) as response:
            res = json.loads(response.read().decode())
    except Exception as e:
        print(f"Error requesting device code: {e}")
        sys.exit(1)
    
    if "user_code" not in res:
        print("Error getting device code:", res)
        sys.exit(1)
    return res

def _poll_for_token(device_code):
    """轮询等待用户在浏览器上完成授权"""
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
            return res["access_token"]
        elif res.get("error") == "authorization_pending":
            time.sleep(INTERVAL)
        elif res.get("error") == "slow_down":
            time.sleep(INTERVAL + 5)
        else:
            print("Authentication failed or expired:", res)
            sys.exit(1)

def get_token_smart():
    """
    智能获取 GitHub Token，优先级：
    1. 从缓存中读取已保存的 access_token，验证有效性后直接复用
    2. 若缓存无效或不存在，自动发起 Device Flow 授权（仅此一次需要用户操作）
    3. 授权成功后将 token 缓存到本地，后续调用直接跳过授权
    """
    cache = _load_cache()
    
    # 1. 尝试复用缓存的 access_token
    cached_token = cache.get("access_token")
    if cached_token:
        print("检测到本地缓存的 Token，正在验证有效性...")
        if _verify_token(cached_token):
            print("Token 有效，跳过授权流程 [OK]")
            return cached_token
        else:
            print("缓存的 Token 已失效，需要重新授权。")
    
    # 2. 自动发起 Device Flow
    print("正在请求 GitHub 设备授权码...")
    device_res = _request_device_code()
    
    print("=" * 50)
    print(f"  请打开: {device_res['verification_uri']}")
    print(f"  输入码: {device_res['user_code']}")
    print("=" * 50)
    print("等待您在浏览器中完成授权...")
    
    token = _poll_for_token(device_res["device_code"])
    
    # 3. 缓存 token 到本地
    cache["access_token"] = token
    cache["device_code"] = device_res["device_code"]
    _save_cache(cache)
    
    print("授权成功，Token 已缓存到本地，下次无需再次授权 [OK]")
    return token

# ---- 兼容旧接口 (deprecated, 保留向后兼容) ----

def load_device_code(default_code=""):
    cache = _load_cache()
    return cache.get("device_code", default_code)

def get_token(device_code):
    """旧接口：优先尝试智能缓存，回退到传统 device_code 轮询"""
    cache = _load_cache()
    cached_token = cache.get("access_token")
    if cached_token and _verify_token(cached_token):
        print("Token 有效，跳过授权流程 [OK]")
        return cached_token
    
    # 回退到旧的轮询逻辑
    if not device_code:
        print("Error: No device code provided. Please run github_device_auth.py first.")
        sys.exit(1)
    
    print("Waiting for your authorization on GitHub...")
    token = _poll_for_token(device_code)
    
    # 缓存新 token
    cache["access_token"] = token
    _save_cache(cache)
    print("Token 已自动缓存，下次无需再次授权 [OK]")
    return token

# ---- GitHub API 请求 ----

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
