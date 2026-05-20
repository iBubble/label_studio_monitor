import base64
import os
from github_utils import load_device_code, get_token, github_api_request

def deploy_project():
    device_code = load_device_code("f5abb6ac0b683477fdee2f72f4ed955795954912")
    token = get_token(device_code)
    
    # Get User Info
    user_res = github_api_request("GET", "https://api.github.com/user", token)
    username = user_res.get("login", "iBubble")
    
    # Upload Icon and Index
    files_to_upload = [
        "static/logo.png",
        "static/index.html"
    ]
    
    for file_path in files_to_upload:
        if not os.path.exists(file_path):
            print(f"{file_path} not found!")
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
            "message": f"Add AI generated logo and update HTML",
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
