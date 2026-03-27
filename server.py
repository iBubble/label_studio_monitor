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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get_index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/interfaces")
async def get_interfaces():
    try:
        hostname = socket.gethostname()
        _, _, ip_addresses = socket.gethostbyname_ex(hostname)
        
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
    try:
        conn = asyncio.open_connection(ip, port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except:
        return False

async def check_label_studio(ip, port, timeout=2.5):
    url = f"http://{ip}:{port}/"
    try:
        # aiohttp follows redirects by default up to 10 redirects.
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as response:
                # Check if we were redirected to /user/login/
                redirected_url = str(response.url)
                text = (await response.text()).lower()
                
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
    except:
        pass
    return False

@app.get("/api/scan")
async def scan_network(subnet: str, skip_ips: str = ""):
    # subnet is expected like 192.168.1.0
    prefix = subnet.rsplit('.', 1)[0]
    
    skip_ips_list = set(skip_ips.split(",")) if skip_ips else set()
    ips_to_scan = [f"{prefix}.{i}" for i in range(1, 255) if f"{prefix}.{i}" not in skip_ips_list]
    total_ips = len(ips_to_scan)
    
    async def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'total': total_ips})}\n\n"
        
        # Limit concurrent ip scanning to save file descriptors, but each IP will scan 6 ports internally.
        sem = asyncio.Semaphore(40)
        
        async def scan_ip(ip):
            async with sem:
                result = {"ip": ip, "open_ports": [], "label_studio_ports": []}
                ports_to_check = range(8080, 8086) # 8080 to 8085
                
                # Check ports concurrently for this IP
                port_results = await asyncio.gather(*(check_port(ip, p) for p in ports_to_check))
                
                for port, is_open in zip(ports_to_check, port_results):
                    if is_open:
                        result["open_ports"].append(port)
                        # Check Label Studio on this port
                        is_ls = await check_label_studio(ip, port)
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
