from playwright.sync_api import sync_playwright
import json
import sys
from urllib.parse import urljoin

# Get player ID from command line argument or use default
if len(sys.argv) > 1:
    player_id = sys.argv[1]
else:
    player_id = '31979530'  # Default player ID

base_url = 'https://ratings.uschess.org'
player_url = f'{base_url}/player/{player_id}'

try:
    with sync_playwright() as p:
        # Launch browser - Playwright is faster than Selenium
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        print(f"Loading player page: {player_url}\n", file=sys.stderr)
        page.goto(player_url, wait_until='networkidle', timeout=30000)
        
        # Wait for tournament links to appear
        page.wait_for_selector('a[href^="/event/"]', timeout=10000)
        
        # Get all tournament links
        tournament_link_elements = page.locator('a[href^="/event/"]').all()
        
        if len(tournament_link_elements) == 0:
            print("No tournaments found on the player page.", file=sys.stderr)
        else:
            print(f"Found {len(tournament_link_elements)} tournaments. Processing first 10 tournaments...\n", file=sys.stderr)
            
            all_games = []
            max_tournaments = 10
            
            # Collect tournament links and URLs upfront, deduplicating by URL
            tournament_data = []
            seen_urls = set()
            for link in tournament_link_elements:
                if len(tournament_data) >= max_tournaments:
                    break
                tournament_title = link.inner_text().strip()
                event_url = urljoin(base_url, link.get_attribute('href'))
                # Deduplicate by full URL to avoid processing same tournament multiple times
                if event_url not in seen_urls:
                    seen_urls.add(event_url)
                    tournament_data.append((tournament_title, event_url))
            
            for idx, (tournament_title, event_url) in enumerate(tournament_data):
                print(f"Processing tournament {idx+1}/{len(tournament_data)} (games: {len(all_games)}): {tournament_title[:50]}...", file=sys.stderr)
                
                # Navigate to tournament page with smarter waiting
                try:
                    page.goto(event_url, wait_until='networkidle', timeout=20000)
                    # Wait for standings table to appear
                    page.wait_for_selector('tr.group\\/tr', timeout=5000)
                except:
                    # Skip if page doesn't load quickly
                    continue
                
                try:
                    # Find player row using XPath equivalent
                    player_row = page.locator(f'//a[@href="/player/{player_id}"]/ancestor::tr').first
                    
                    # Check if element exists
                    if player_row.count() == 0:
                        continue  # Skip tournaments where player not found
                    
                    # Get player name
                    name_div = player_row.locator('div.font-names').first
                    player_name = name_div.inner_text().strip() if name_div.count() > 0 else "Unknown"
                    
                    # Build pairing → opponent dict from all rows
                    pairing_to_opponent = {}
                    # Use CSS selector with escaped class name
                    all_rows = page.locator('tr.group\\/tr').all()
                    
                    for row in all_rows:
                        try:
                            # Get pairing number: .//td[1]//div[contains(@class, "grid-rows-2")]//div[1]/div
                            first_td = row.locator('td').first
                            grid_div = first_td.locator('div.grid-rows-2').first
                            if grid_div.count() > 0:
                                first_inner_div = grid_div.locator('div').first
                                if first_inner_div.count() > 0:
                                    pairing_num_elem = first_inner_div.locator('div').first
                                    if pairing_num_elem.count() > 0:
                                        pairing_num = pairing_num_elem.inner_text().strip()
                                        
                                        if pairing_num:
                                            # Get opponent name
                                            opp_name_div = row.locator('div.font-names').first
                                            opp_name = opp_name_div.inner_text().strip() if opp_name_div.count() > 0 else "Unknown"
                                            
                                            # Get opponent ID
                                            id_link = row.locator('a[href^="/player/"]').first
                                            href = id_link.get_attribute('href') if id_link.count() > 0 else None
                                            opp_id = href.split('/')[-1] if href else None
                                            
                                            pairing_to_opponent[pairing_num] = {
                                                "name": opp_name,
                                                "uscf_id": opp_id
                                            }
                        except:
                            continue
                    
                    # Extract games from rounds
                    all_tds = player_row.locator('td').all()
                    if len(all_tds) > 4:
                        round_tds = all_tds[3:-1]
                    elif len(all_tds) > 3:
                        round_tds = all_tds[3:]
                    else:
                        round_tds = []
                    
                    for i, cell in enumerate(round_tds, 1):
                        try:
                            # Find grid-rows-2 div
                            grid_div = cell.locator('div.grid-rows-2').first
                            if grid_div.count() > 0:
                                grid_rows = grid_div.locator('> div').all()
                                if len(grid_rows) >= 2:
                                    top_row = grid_rows[0]
                                    bottom_row = grid_rows[1]
                                    
                                    # Get result and opponent number from top row: ./div[1] and ./div[2]
                                    top_divs = top_row.locator('> div').all()
                                    result = top_divs[0].inner_text().strip() if len(top_divs) > 0 else None
                                    opp_num = top_divs[1].inner_text().strip() if len(top_divs) > 1 else None
                                    
                                    # Only add games with valid results
                                    if result and result.strip():
                                        # Get color from bottom row: ./div[1]
                                        bottom_divs = bottom_row.locator('> div').all()
                                        color_ind = bottom_divs[0].inner_text().strip() if len(bottom_divs) > 0 else None
                                        color = "White" if color_ind == "⚪️" else "Black" if color_ind == "⚫️" else "Unknown"
                                        
                                        opponent = pairing_to_opponent.get(opp_num, {"name": "Unknown", "uscf_id": None})
                                        
                                        # Add game to the flat list with only requested fields
                                        game = {
                                            "tournament_name": tournament_title,
                                            "round": i,
                                            "result": result,
                                            "opponent_pairing_number": opp_num,
                                            "opponent_name": opponent["name"],
                                            "opponent_uscf_id": opponent["uscf_id"],
                                            "color": color,
                                            "player_name": player_name,
                                            "player_uscf_id": player_id
                                        }
                                        all_games.append(game)
                        except:
                            continue
                except:
                    continue  # Skip tournaments with errors
            
            # Format output as numbered games 1 to n
            games_dict = {}
            for idx, game in enumerate(all_games, 1):
                games_dict[str(idx)] = game
            
            # Output the games as JSON with numbered keys
            print(json.dumps(games_dict, indent=2))
        
        browser.close()

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
