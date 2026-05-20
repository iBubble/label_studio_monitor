import base64
import os
from github_utils import load_device_code, get_token, github_api_request

def deploy_project():
    device_code = load_device_code("de5af6c2dc3398a69c7e3a051bd5dc07ccfe8e15")
    token = get_token(device_code)
    
    # 2. Get User Info
    user_res = github_api_request("GET", "https://api.github.com/user", token)
    username = user_res.get("login", "iBubble")
    
    # 3. Upload README
    file_path = "README.md"
    if not os.path.exists(file_path):
        print("README.md not found!")
        return
        
    print(f"Uploading {file_path}...")
    with open(file_path, "rb") as f:
        content = f.read()
        
    b64_content = base64.b64encode(content).decode("utf-8")
    upload_url = f"https://api.github.com/repos/{username}/label_studio_monitor/contents/{file_path}"
    
    existing_file = github_api_request("GET", upload_url, token)
    sha = existing_file.get("sha") if existing_file else None
    
    upload_payload = {
        "message": "Add concise and detailed README",
        "content": b64_content,
        "committer": {"name": "iBubble", "email": "ibubble@msn.com"}
    }
    if sha:
        upload_payload["sha"] = sha
        
    success = github_api_request("PUT", upload_url, token, data=upload_payload)
    if success:
        print(f"Successfully uploaded {file_path}")
    print("Deployment to GitHub complete!")

if __name__ == "__main__":
    deploy_project()
