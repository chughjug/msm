#!/usr/bin/env python3
"""
Script to trigger GitHub Actions workflow via GitHub API and wait for completion
Usage: python trigger_workflow.py <player_id> [repo_owner] [repo_name]
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

def trigger_workflow(player_id, repo_owner="chughjug", repo_name="msm"):
    """Trigger the GitHub Actions workflow with a player ID and wait for completion"""
    
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN environment variable is not set", file=sys.stderr)
        print("Set it with: export GITHUB_TOKEN='your_token_here'", file=sys.stderr)
        return None
    
    # Trigger workflow
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows/run_chess_scraper.yml/dispatches"
    
    data = {
        "ref": "main",
        "inputs": {
            "player_id": str(player_id)
        }
    }
    
    print(f"Triggering workflow for player ID: {player_id}...", file=sys.stderr)
    
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
        runs_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows/run_chess_scraper.yml/runs"
        
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
                    return get_artifact_json(repo_owner, repo_name, run_id, player_id)
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

def get_artifact_json(repo_owner, repo_name, run_id, player_id):
    """Get JSON from workflow artifact"""
    try:
        # Get artifacts for this run
        artifacts_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/runs/{run_id}/artifacts"
        response = requests.get(artifacts_url, headers=get_headers())
        
        if response.status_code != 200:
            print(f"Error getting artifacts: {response.status_code}", file=sys.stderr)
            return None
        
        artifacts = response.json().get("artifacts", [])
        artifact_name = f"chess-games-{player_id}"
        
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
    if len(sys.argv) < 2:
        print("Usage: python trigger_workflow.py <player_id> [repo_owner] [repo_name]", file=sys.stderr)
        print("Example: python trigger_workflow.py 31979530", file=sys.stderr)
        sys.exit(1)
    
    player_id = sys.argv[1]
    repo_owner = sys.argv[2] if len(sys.argv) > 2 else "chughjug"
    repo_name = sys.argv[3] if len(sys.argv) > 3 else "msm"
    
    result = trigger_workflow(player_id, repo_owner, repo_name)
    
    if result:
        print(json.dumps(result, indent=2))
    else:
        sys.exit(1)
