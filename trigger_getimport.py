#!/usr/bin/env python3
"""
Script to trigger GitHub Actions getimport workflow via GitHub API and wait for completion
Usage: python trigger_getimport.py <text> [repo_owner] [repo_name]
       python trigger_getimport.py -f <file> [repo_owner] [repo_name]
"""

import sys
import os
import requests
import json
import time
import zipfile
import io

# GitHub token from environment variable or GitHub secrets
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

def get_headers():
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

def trigger_getimport_workflow(text, repo_owner="chughjug", repo_name="msm"):
    """Trigger the GitHub Actions getimport workflow with text and wait for completion"""
    
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN environment variable is not set", file=sys.stderr)
        print("Set it with: export GITHUB_TOKEN='your_token_here'", file=sys.stderr)
        return None
    
    # Trigger workflow
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows/run_getimport.yml/dispatches"
    
    data = {
        "ref": "main",
        "inputs": {
            "text": text
        }
    }
    
    print("Triggering getimport workflow...", file=sys.stderr)
    
    try:
        response = requests.post(url, headers=get_headers(), json=data)
        
        if response.status_code != 204:
            print(f"Error triggering workflow: {response.status_code}", file=sys.stderr)
            print(f"Response: {response.text}", file=sys.stderr)
            return None
        
        print("Workflow triggered. Waiting for completion...", file=sys.stderr)
        
        # Wait a moment for the run to start
        time.sleep(3)
        
        # Get the latest workflow run
        runs_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows/run_getimport.yml/runs"
        
        # Wait for workflow to complete
        max_wait_time = 600  # 10 minutes max
        wait_interval = 5  # Check every 5 seconds
        elapsed = 0
        run_id = None
        
        while elapsed < max_wait_time:
            response = requests.get(runs_url, headers=get_headers(), params={"per_page": 1})
            
            if response.status_code != 200:
                print(f"Error getting workflow runs: {response.status_code}", file=sys.stderr)
                return None
            
            runs = response.json().get("workflow_runs", [])
            
            if not runs:
                time.sleep(wait_interval)
                elapsed += wait_interval
                continue
            
            run = runs[0]
            status = run.get("status")
            conclusion = run.get("conclusion")
            run_id = run.get("id")
            
            if status == "completed":
                if conclusion == "success":
                    print("Workflow completed successfully!", file=sys.stderr)
                    # Get the artifact
                    return get_artifact_json(repo_owner, repo_name, run_id)
                else:
                    print(f"Workflow failed with conclusion: {conclusion}", file=sys.stderr)
                    return None
            elif status in ["queued", "in_progress"]:
                print(f"Workflow {status}... ({elapsed}s elapsed)", file=sys.stderr)
                time.sleep(wait_interval)
                elapsed += wait_interval
            else:
                print(f"Workflow status: {status}", file=sys.stderr)
                time.sleep(wait_interval)
                elapsed += wait_interval
        
        print("Timeout waiting for workflow to complete", file=sys.stderr)
        return None
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None

def get_artifact_json(repo_owner, repo_name, run_id):
    """Get JSON from workflow artifact"""
    try:
        # Get artifacts for this run
        artifacts_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}/artifacts"
        response = requests.get(artifacts_url, headers=get_headers())
        
        if response.status_code != 200:
            print(f"Error getting artifacts: {response.status_code}", file=sys.stderr)
            return None
        
        artifacts = response.json().get("artifacts", [])
        artifact_name = "extracted-players"
        
        for artifact in artifacts:
            if artifact.get("name") == artifact_name:
                # Download artifact
                download_url = artifact.get("archive_download_url")
                if download_url:
                    print("Downloading artifact...", file=sys.stderr)
                    download_response = requests.get(download_url, headers=get_headers(), allow_redirects=True)
                    
                    if download_response.status_code == 200:
                        # Extract zip and read output.json
                        zip_data = io.BytesIO(download_response.content)
                        with zipfile.ZipFile(zip_data, 'r') as zip_ref:
                            # Artifact contains a folder with the file
                            for file_name in zip_ref.namelist():
                                if file_name.endswith('output.json') or file_name == 'output.json':
                                    json_content = zip_ref.read(file_name)
                                    try:
                                        return json.loads(json_content.decode('utf-8'))
                                    except json.JSONDecodeError:
                                        continue
                            # Try reading any JSON file
                            for file_name in zip_ref.namelist():
                                if file_name.endswith('.json'):
                                    json_content = zip_ref.read(file_name)
                                    try:
                                        return json.loads(json_content.decode('utf-8'))
                                    except json.JSONDecodeError:
                                        continue
        
        print("Artifact not found or couldn't extract JSON", file=sys.stderr)
        return None
        
    except Exception as e:
        print(f"Error getting artifact: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    text = None
    repo_owner = "chughjug"
    repo_name = "msm"
    
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python trigger_getimport.py <text> [repo_owner] [repo_name]", file=sys.stderr)
        print("       python trigger_getimport.py -f <file> [repo_owner] [repo_name]", file=sys.stderr)
        print("Example: python trigger_getimport.py \"Player text here...\"", file=sys.stderr)
        print("         python trigger_getimport.py -f input.txt", file=sys.stderr)
        sys.exit(1)
    
    # Check if reading from file
    if sys.argv[1] == "-f" or sys.argv[1] == "--file":
        if len(sys.argv) < 3:
            print("Error: -f requires a filename", file=sys.stderr)
            sys.exit(1)
        try:
            with open(sys.argv[2], 'r', encoding='utf-8') as f:
                text = f.read()
            arg_start = 3
        except FileNotFoundError:
            print(f"Error: File not found: {sys.argv[2]}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        text = sys.argv[1]
        arg_start = 2
    
    # Get optional repo owner and name
    if len(sys.argv) > arg_start:
        repo_owner = sys.argv[arg_start]
    if len(sys.argv) > arg_start + 1:
        repo_name = sys.argv[arg_start + 1]
    
    if not text or not text.strip():
        print("Error: No text provided", file=sys.stderr)
        sys.exit(1)
    
    result = trigger_getimport_workflow(text, repo_owner, repo_name)
    
    if result:
        print(json.dumps(result, indent=2))
    else:
        sys.exit(1)

