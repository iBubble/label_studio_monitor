import asyncio
import socket
import aiohttp
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
import ipaddress
import os

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Cache static/index.html in memory to optimize disk I/O
try:
    with open("static/index.html", "r", encoding="utf-8") as f:
        INDEX_HTML_CONTENT = f.read()
except Exception:
    INDEX_HTML_CONTENT = "<h1>Label Studio Monitor - HTML Not Found</h1>"

@app.get("/")
async def get_index():
    return HTMLResponse(INDEX_HTML_CONTENT)

@app.get("/api/interfaces")
async def get_interfaces():
    try:
        ip_addresses = []
        try:
            hostname = socket.gethostname()
            _, _, ips = socket.gethostbyname_ex(hostname)
            ip_addresses.extend(ips)
        except Exception:
            pass
        
        # Fallback 1: getaddrinfo
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None):
                ip = info[4][0]
                if isinstance(ip, str) and "." in ip and ip not in ip_addresses:
                    ip_addresses.append(ip)
        except Exception:
            pass
            
        # Fallback 2: UDP connection routing test
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip not in ip_addresses:
                ip_addresses.append(ip)
            s.close()
        except Exception:
            pass

        # Filter local or private IPv4 addresses
        subnets = []
        for ip in ip_addresses:
            if ip.startswith("127."):
                continue
            # Assume a /24 subnet for simplicity which covers most home/office LANs
            subnet = f"{ip.rsplit('.', 1)[0]}.0"
            subnets.append({"ip": ip, "subnet": subnet})
        
        # Sort and deduplicate
        subnets = sorted(list({v['subnet']:v for v in subnets}.values()), key=lambda x: x['ip'])
        return {"subnets": subnets}
    except Exception as e:
        return {"error": str(e), "subnets": []}

async def check_port(ip, port, timeout=1.5):
    """
    使用底层非阻塞 socket 检查端口，规避 StreamReader/StreamWriter 资源开销和在取消时的句柄泄露隐患
    """
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    try:
        await asyncio.wait_for(
            loop.sock_connect(sock, (ip, port)),
            timeout=timeout
        )
        return True
    except Exception:
        return False
    finally:
        sock.close()

async def check_label_studio(ip, port, timeout=2.5, session=None):
    url = f"http://{ip}:{port}/"
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        if session is None:
            async with aiohttp.ClientSession() as new_session:
                return await _do_check_label_studio(new_session, url, client_timeout)
        else:
            return await _do_check_label_studio(session, url, client_timeout)
    except:
        pass
    return False

async def _do_check_label_studio(session, url, timeout):
    async with session.get(url, timeout=timeout) as response:
        # Check if we were redirected to /user/login/
        redirected_url = str(response.url)
        text = (await response.text(errors="ignore")).lower()
        
        # The user criteria:
        # 1. URL ends with /user/login/ or has it
        # 2. Title is Label Studio or text contains label studio
        is_redirected_login = "/user/login/" in redirected_url
        is_label_studio_title = "label studio" in text or "ls-app" in text

        if is_redirected_login and is_label_studio_title:
            return True
        
        # Fallback: if it just says Label Studio and no redirect, it might also be valid depending on auth
        if is_label_studio_title:
            return True
    return False

@app.get("/api/scan")
async def scan_network(subnet: str, skip_ips: str = ""):
    # 严格输入格式校验，规避无效网段输入触发的大量 DNS 同步查询风暴
    is_valid = False
    try:
        ipaddress.IPv4Address(subnet)
        is_valid = True
    except ValueError:
        try:
            prefix = subnet.rsplit('.', 1)[0]
            ipaddress.IPv4Address(f"{prefix}.1")
            is_valid = True
        except ValueError:
            pass
            
    if not is_valid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid subnet format. Expected '192.168.1.0' or '192.168.1'")

    prefix = subnet.rsplit('.', 1)[0]
    skip_ips_list = set(skip_ips.split(",")) if skip_ips else set()
    ips_to_scan = [f"{prefix}.{i}" for i in range(1, 255) if f"{prefix}.{i}" not in skip_ips_list]
    total_ips = len(ips_to_scan)
    
    async def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'total': total_ips})}\n\n"
        
        # 限制并发 IP 数量为 30（总端口并发最大 180），可确保在 Windows 上的稳定和极高探测精度
        sem = asyncio.Semaphore(30)
        
        async with aiohttp.ClientSession() as session:
            async def scan_ip(ip):
                async with sem:
                    result = {"ip": ip, "open_ports": [], "label_studio_ports": []}
                    ports_to_check = range(8080, 8086) # 8080 to 8085
                    
                    # 并发检测单个 IP 的 6 个端口
                    port_results = await asyncio.gather(*(check_port(ip, p) for p in ports_to_check))
                    
                    for port, is_open in zip(ports_to_check, port_results):
                        if is_open:
                            result["open_ports"].append(port)
                            is_ls = await check_label_studio(ip, port, session=session)
                            if is_ls:
                                result["label_studio_ports"].append(port)
                    
                    return result

            tasks = [scan_ip(ip) for ip in ips_to_scan]
            
            completed_count = 0
            for task in asyncio.as_completed(tasks):
                res = await task
                completed_count += 1
                yield f"data: {json.dumps({'type': 'progress', 'result': res, 'completed': completed_count})}\n\n"
                
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/latest_project")
async def get_latest_project(ip: str, port: int, search: str = ""):
    url_base = f"http://{ip}:{port}"
    login_url = f"{url_base}/user/login/"
    projects_url = f"{url_base}/api/projects/"
    
    import yarl
    timeout = aiohttp.ClientTimeout(total=10)
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(timeout=timeout, cookie_jar=jar) as session:
        try:
            # 1. Get CSRF token
            async with session.get(login_url) as resp:
                await resp.text()
            
            url_obj = yarl.URL(url_base)
            csrftoken_cookie = session.cookie_jar.filter_cookies(url_obj).get('csrftoken')
            
            if not csrftoken_cookie:
                return {"error": "未能获取 csrf token"}
                
            token_value = csrftoken_cookie.value
            
            # 2. Login
            data = {
                "csrfmiddlewaretoken": token_value,
                "email": os.environ.get("LABEL_STUDIO_EMAIL", "student@yncjzy.com"),
                "password": os.environ.get("LABEL_STUDIO_PASSWORD", "1q2w3e4r")
            }
            headers = {"Referer": login_url, "Origin": url_base}
            
            async with session.post(login_url, data=data, headers=headers, allow_redirects=False) as resp:
                if resp.status != 302:
                    if resp.status == 200:
                        text = await resp.text(errors="ignore")
                        if "CSRF" in text or "csrf" in text:
                            return {"error": "登录失败: CSRF 验证失败"}
                        return {"error": "登录失败: 密码错误或用户不存在"}
                    return {"error": f"登录失败 (状态码 {resp.status})"}
                
            # 3. Get projects
            async with session.get(projects_url) as resp:
                if resp.status != 200:
                    return {"error": f"认证失败或无权限 (状态码 {resp.status})"}
                
                resp_json = await resp.json()
                
                projects = []
                if isinstance(resp_json, list):
                    projects = resp_json
                elif isinstance(resp_json, dict) and "results" in resp_json:
                    projects = resp_json["results"]
                
                if not projects:
                    return {"project": None}
                
                # 按创建时间倒序
                projects_sorted = sorted(projects, key=lambda p: p.get("created_at") or str(p.get("id") or ""), reverse=True)
                
                target = None
                if search.strip():
                    # 模糊搜索：在排序后的列表中找第一个标题包含搜索词的
                    search_lower = search.strip().lower()
                    for p in projects_sorted:
                        if search_lower in (p.get("title") or "").lower():
                            target = p
                            break
                    if not target:
                        return {"project": None, "not_found": True}
                else:
                    target = projects_sorted[0]
                
                return {
                    "project": {
                        "id": target.get("id"),
                        "title": target.get("title") or "未命名项目",
                        "description": target.get("description") or "",
                        "created_at": target.get("created_at"),
                        "updated_at": target.get("updated_at") or target.get("created_at") or ""
                    }
                }
        except Exception as e:
            return {"error": f"请求异常: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
