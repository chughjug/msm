#!/usr/bin/env python3
"""
Test script to run chess scraper for multiple USCF IDs in parallel
"""
import subprocess
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# USCF IDs from the test data
TEST_IDS = [
    "30522189",  # Kaushik, Shlok
    "16576086",  # LeMaisonett, Isabella
    "31177829",  # Mani, Advik Subhav
    "31334125",  # Pamidimukkala, Sriyan
    "30386430",  # Baskar, Sai Krishna
    "32632600",  # Hernandez, Donovin
    "3258372",   # Houser, Caleb
    "30529452",  # Mamidipally, Saketh
    "30721819",  # Mani, Anirudh Subhav
    "31741338",  # Pamidimukkala, Sri Saanvi
    "32639793",  # Stevens, Uriah
]

def scrape_player_id(player_id):
    """Run the scraper for a single player ID"""
    output_file = f"outputs/chess-games-{player_id}.json"
    try:
        print(f"Processing Player ID: {player_id}...")
        result = subprocess.run(
            [sys.executable, "m.py/m.py", player_id],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout per player
        )
        
        # Write output to file
        os.makedirs("outputs", exist_ok=True)
        with open(output_file, 'w') as f:
            if result.returncode == 0:
                f.write(result.stdout)
            else:
                error_json = {
                    "error": f"Failed to scrape games for player ID {player_id}",
                    "player_id": player_id,
                    "stderr": result.stderr
                }
                f.write(json.dumps(error_json, indent=2))
        
        print(f"✓ Completed: {player_id}")
        return {"player_id": player_id, "success": result.returncode == 0, "file": output_file}
    except subprocess.TimeoutExpired:
        error_json = {
            "error": f"Timeout processing player ID {player_id}",
            "player_id": player_id
        }
        with open(output_file, 'w') as f:
            f.write(json.dumps(error_json, indent=2))
        print(f"✗ Timeout: {player_id}")
        return {"player_id": player_id, "success": False, "file": output_file}
    except Exception as e:
        error_json = {
            "error": f"Exception processing player ID {player_id}: {str(e)}",
            "player_id": player_id
        }
        with open(output_file, 'w') as f:
            f.write(json.dumps(error_json, indent=2))
        print(f"✗ Error: {player_id} - {str(e)}")
        return {"player_id": player_id, "success": False, "file": output_file}

def create_summary():
    """Create a summary JSON with all results"""
    summary = {}
    outputs_dir = "outputs"
    
    if not os.path.exists(outputs_dir):
        print("No outputs directory found")
        return
    
    json_files = [f for f in os.listdir(outputs_dir) if f.startswith("chess-games-") and f.endswith(".json")]
    
    for filename in sorted(json_files):
        player_id = filename.replace("chess-games-", "").replace(".json", "")
        file_path = os.path.join(outputs_dir, filename)
        
        try:
            with open(file_path, 'r') as f:
                content = f.read().strip()
                try:
                    data = json.loads(content)
                    summary[player_id] = data
                except json.JSONDecodeError:
                    summary[player_id] = {"raw_output": content}
        except Exception as e:
            summary[player_id] = {"error": f"Failed to read file: {str(e)}"}
    
    summary_file = os.path.join(outputs_dir, "summary.json")
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n=== Summary ===")
    print(f"Total players processed: {len(summary)}")
    print(f"Summary saved to: {summary_file}")
    return summary_file

def main():
    # Use IDs from command line if provided, otherwise use test IDs
    if len(sys.argv) > 1:
        player_ids = [id.strip() for id in sys.argv[1].split(',')]
    else:
        player_ids = TEST_IDS
    
    print(f"Processing {len(player_ids)} player IDs in parallel...")
    print(f"IDs: {', '.join(player_ids)}\n")
    
    # Create outputs directory
    os.makedirs("outputs", exist_ok=True)
    
    # Process all IDs in parallel
    results = []
    with ThreadPoolExecutor(max_workers=min(10, len(player_ids))) as executor:
        future_to_id = {executor.submit(scrape_player_id, pid): pid for pid in player_ids}
        
        for future in as_completed(future_to_id):
            result = future.result()
            results.append(result)
    
    # Create summary
    summary_file = create_summary()
    
    # Print results summary
    successful = sum(1 for r in results if r["success"])
    failed = len(results) - successful
    
    print(f"\n=== Final Results ===")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"\nAll files saved in: outputs/")
    print(f"Summary file: {summary_file}")

if __name__ == "__main__":
    main()

