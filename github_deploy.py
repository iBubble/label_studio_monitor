import base64
import os
import time
from github_utils import load_device_code, get_token, github_api_request

def deploy_project():
    device_code = load_device_code("9275a91e3f1628b7e45a237e086e743c7de886ae")
    token = get_token(device_code)
    
    # 1. Create Repository
    print("Creating repository 'label_studio_monitor'...")
    url_create = "https://api.github.com/user/repos"
    payload = {
        "name": "label_studio_monitor",
        "description": "LAN Port Scanner and Label Studio detector",
        "private": False,
        "auto_init": True
    }
    
    res = github_api_request("POST", url_create, token, data=payload)
    if not res:
        print("Repository might already exist, proceeding to upload files...")
    else:
        print(f"Repository created: {res.get('html_url')}")
        time.sleep(2) # Wait for git initialization
    
    # 2. Get User Info
    user_res = github_api_request("GET", "https://api.github.com/user", token)
    username = user_res.get("login", "iBubble")
    
    # 3. Upload Files
    files_to_upload = [
        "server.py",
        "static/index.html",
        "static/styles.css",
        "static/app.js",
        "static/logo.png",
        ".gitignore",
        "README.md",
        "github_deploy.py",
        "github_device_auth.py",
        "github_utils.py",
        "push_readme.py",
        "push_icon.py",
        "test_ls.py",
        "test_origin.py",
        "get_device_code.py",
        "task.md",
        "walkthrough.md"
    ]
    
    for file_path in files_to_upload:
        if not os.path.exists(file_path):
            continue
            
        print(f"Uploading {file_path}...")
        with open(file_path, "rb") as f:
            content = f.read()
            
        b64_content = base64.b64encode(content).decode("utf-8")
        
        upload_url = f"https://api.github.com/repos/{username}/label_studio_monitor/contents/{file_path}"
        
        # Check if file exists to get SHA for updating
        existing_file = github_api_request("GET", upload_url, token)
        sha = existing_file.get("sha") if existing_file else None
        
        upload_payload = {
            "message": f"Add {file_path}",
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
