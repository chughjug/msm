from playwright.sync_api import sync_playwright
import json
import sys
import re
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# Get player ID from command line argument or use default
if len(sys.argv) > 1:
    player_id = sys.argv[1]
else:
    player_id = '31979530'  # Default player ID

base_url = 'https://ratings.uschess.org'

def process_single_tournament(tournament_data):
    """
    Process a single tournament in a separate process.
    Each process creates its own Playwright browser instance.
    Args:
        tournament_data: tuple of (tournament_title, event_url, player_id, player_name, player_rating)
    Returns:
        tuple of (list of game dictionaries, player_rating)
    """
    tournament_title, event_url, player_id, player_name, player_rating = tournament_data
    games = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            # Navigate to tournament page
            try:
                page.goto(event_url, wait_until='networkidle', timeout=20000)
                page.wait_for_selector('tr.group\\/tr', timeout=5000)
            except:
                browser.close()
                return (games, None)  # Return empty list and no rating if page doesn't load
            
            try:
                # Find player row
                player_row = page.locator(f'//a[@href="/player/{player_id}"]/ancestor::tr').first
                
                if player_row.count() == 0:
                    browser.close()
                    return (games, None)  # Skip tournaments where player not found
                
                # Get player name from tournament page (in case it's different/more accurate)
                name_div = player_row.locator('div.font-names').first
                tournament_player_name = name_div.inner_text().strip() if name_div.count() > 0 else player_name
                
                # Get player rating from the table row (rating is in the 3rd column, index 2)
                # Rating column is typically the 3rd column (index 2) based on table structure
                if player_rating is None:
                    row_tds = player_row.locator('td').all()
                    # Try columns 2, 1, 3 in that order (rating is usually in column 2)
                    for td_idx in [2, 1, 3]:
                        if len(row_tds) > td_idx:
                            rating_td = row_tds[td_idx]
                            rating_text = rating_td.inner_text().strip()
                            # Look for rating number (3-4 digits)
                            rating_matches = re.findall(r'\b(\d{3,4})\b', rating_text)
                            for match in rating_matches:
                                try:
                                    rating_val = int(match)
                                    if 100 <= rating_val <= 3000:
                                        # Make sure it's not a pairing number or other identifier
                                        # Pairing numbers are usually smaller or in first column
                                        player_rating = rating_val
                                        break
                                except:
                                    continue
                            if player_rating:
                                break
                
                # Build pairing → opponent dict from all rows
                pairing_to_opponent = {}
                all_rows = page.locator('tr.group\\/tr').all()
                
                for row in all_rows:
                    try:
                        first_td = row.locator('td').first
                        grid_div = first_td.locator('div.grid-rows-2').first
                        if grid_div.count() > 0:
                            first_inner_div = grid_div.locator('div').first
                            if first_inner_div.count() > 0:
                                pairing_num_elem = first_inner_div.locator('div').first
                                if pairing_num_elem.count() > 0:
                                    pairing_num = pairing_num_elem.inner_text().strip()
                                    
                                    if pairing_num:
                                        opp_name_div = row.locator('div.font-names').first
                                        opp_name = opp_name_div.inner_text().strip() if opp_name_div.count() > 0 else "Unknown"
                                        
                                        id_link = row.locator('a[href^="/player/"]').first
                                        href = id_link.get_attribute('href') if id_link.count() > 0 else None
                                        opp_id = href.split('/')[-1] if href else None
                                        
                                        opp_rating = None
                                        try:
                                            row_text = row.inner_text()
                                            rating_match = re.search(r'\b(\d{3,4})\b', row_text)
                                            if rating_match:
                                                potential_rating = int(rating_match.group(1))
                                                if 100 <= potential_rating <= 3000:
                                                    if str(potential_rating) != pairing_num:
                                                        opp_rating = potential_rating
                                            if opp_rating is None:
                                                row_tds = row.locator('td').all()
                                                for td_idx in [1, 2]:
                                                    if len(row_tds) > td_idx:
                                                        td_text = row_tds[td_idx].inner_text().strip()
                                                        rating_matches = re.findall(r'\b(\d{3,4})\b', td_text)
                                                        for match in rating_matches:
                                                            try:
                                                                rating_val = int(match)
                                                                if 100 <= rating_val <= 3000 and str(rating_val) != pairing_num:
                                                                    opp_rating = rating_val
                                                                    break
                                                            except:
                                                                continue
                                                        if opp_rating:
                                                            break
                                        except:
                                            pass
                                        
                                        pairing_to_opponent[pairing_num] = {
                                            "name": opp_name,
                                            "uscf_id": opp_id,
                                            "rating": opp_rating
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
                        grid_div = cell.locator('div.grid-rows-2').first
                        if grid_div.count() > 0:
                            grid_rows = grid_div.locator('> div').all()
                            if len(grid_rows) >= 2:
                                top_row = grid_rows[0]
                                bottom_row = grid_rows[1]
                                
                                top_divs = top_row.locator('> div').all()
                                result = top_divs[0].inner_text().strip() if len(top_divs) > 0 else None
                                opp_num = top_divs[1].inner_text().strip() if len(top_divs) > 1 else None
                                
                                if result and result.strip():
                                    bottom_divs = bottom_row.locator('> div').all()
                                    color_ind = bottom_divs[0].inner_text().strip() if len(bottom_divs) > 0 else None
                                    color = "White" if color_ind == "⚪️" else "Black" if color_ind == "⚫️" else "Unknown"
                                    
                                    opponent = pairing_to_opponent.get(opp_num, {"name": "Unknown", "uscf_id": None, "rating": None})
                                    
                                    game = {
                                        "tournament_name": tournament_title,
                                        "round": i,
                                        "result": result,
                                        "opponent_pairing_number": opp_num,
                                        "opponent_name": opponent["name"],
                                        "opponent_uscf_id": opponent["uscf_id"],
                                        "opponent_rating": opponent.get("rating"),
                                        "color": color,
                                        "player_name": tournament_player_name,
                                        "player_uscf_id": player_id,
                                        "player_rating": player_rating
                                    }
                                    games.append(game)
                    except:
                        continue
            except:
                pass
            
            browser.close()
    except Exception as e:
        print(f"Error processing tournament {tournament_title}: {e}", file=sys.stderr)
    
    return (games, player_rating)

player_url = f'{base_url}/player/{player_id}'

try:
    with sync_playwright() as p:
        # Launch browser - Playwright is faster than Selenium
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        print(f"Loading player page: {player_url}\n", file=sys.stderr)
        page.goto(player_url, wait_until='networkidle', timeout=30000)
        
        # Wait for page to load
        page.wait_for_selector('a[href^="/event/"]', timeout=10000)
        
        # Extract player name and rating from the player page
        player_name = "Unknown"
        player_rating = None
        
        try:
            # Get player name - look for name in various locations
            # Try common selectors for player name
            name_elements = page.locator('h1, h2, [class*="name"], [class*="player"]').all()
            for elem in name_elements[:5]:  # Check first few elements
                text = elem.inner_text().strip()
                if text and len(text) > 2 and player_id not in text:
                    # Clean up the name (remove extra whitespace, newlines)
                    player_name = ' '.join(text.split())
                    if len(player_name) > 3:  # Valid name
                        break
            
            # Get rating from the most recent tournament table (more accurate)
            # We'll extract it from the tournament table where the player row shows the rating
                        
        except Exception as e:
            print(f"Could not extract player info: {e}", file=sys.stderr)
        
        # Get all tournament links
        tournament_link_elements = page.locator('a[href^="/event/"]').all()
        
        if len(tournament_link_elements) == 0:
            print("No tournaments found on the player page.", file=sys.stderr)
        else:
            print(f"Found {len(tournament_link_elements)} tournaments. Processing first 10 tournaments...\n", file=sys.stderr)
            
            all_games = []
            max_tournaments = 10
            
            # Collect tournament links and URLs upfront, deduplicating by URL
            tournament_list = []
            seen_urls = set()
            for link in tournament_link_elements:
                if len(tournament_list) >= max_tournaments:
                    break
                tournament_title = link.inner_text().strip()
                event_url = urljoin(base_url, link.get_attribute('href'))
                # Deduplicate by full URL to avoid processing same tournament multiple times
                if event_url not in seen_urls:
                    seen_urls.add(event_url)
                    tournament_list.append((tournament_title, event_url))
            
            # Extract rating from first tournament (most recent) to get current rating
            if player_rating is None and len(tournament_list) > 0:
                try:
                    first_title, first_url = tournament_list[0]
                    print(f"Extracting rating from most recent tournament...", file=sys.stderr)
                    page.goto(first_url, wait_until='networkidle', timeout=20000)
                    page.wait_for_selector('tr.group\\/tr', timeout=5000)
                    
                    first_player_row = page.locator(f'//a[@href="/player/{player_id}"]/ancestor::tr').first
                    if first_player_row.count() > 0:
                        row_tds = first_player_row.locator('td').all()
                        for td_idx in [2, 1, 3]:
                            if len(row_tds) > td_idx:
                                rating_td = row_tds[td_idx]
                                rating_text = rating_td.inner_text().strip()
                                rating_matches = re.findall(r'\b(\d{3,4})\b', rating_text)
                                for match in rating_matches:
                                    try:
                                        rating_val = int(match)
                                        if 100 <= rating_val <= 3000:
                                            player_rating = rating_val
                                            break
                                    except:
                                        continue
                                if player_rating:
                                    break
                    
                    # Go back to player page
                    page.goto(player_url, wait_until='networkidle', timeout=30000)
                    page.wait_for_selector('a[href^="/event/"]', timeout=10000)
                except Exception as e:
                    print(f"Could not extract rating from first tournament: {e}", file=sys.stderr)
            
            # Prepare tournament data with player info for parallel processing
            tournament_data = [
                (title, url, player_id, player_name, player_rating)
                for title, url in tournament_list
            ]
            
            print(f"Processing {len(tournament_data)} tournaments in parallel...\n", file=sys.stderr)
            
            # Process tournaments in parallel
            # Use ThreadPoolExecutor with 5 workers for optimal performance
            max_workers = min(5, len(tournament_data))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tournament processing tasks
                future_to_tournament = {
                    executor.submit(process_single_tournament, data): data[0]
                    for data in tournament_data
                }
                
                # Collect results as they complete
                completed = 0
                for future in as_completed(future_to_tournament):
                    tournament_title = future_to_tournament[future]
                    completed += 1
                    try:
                        games, extracted_rating = future.result()
                        # Update all games to use the consistent player_rating (from first tournament)
                        for game in games:
                            game["player_rating"] = player_rating
                        all_games.extend(games)
                        print(f"Completed {completed}/{len(tournament_data)}: {tournament_title[:50]}... ({len(games)} games)", file=sys.stderr)
                    except Exception as e:
                        print(f"Error processing tournament {tournament_title}: {e}", file=sys.stderr)
            
            # Format output as numbered games 1 to n
            games_dict = {}
            for idx, game in enumerate(all_games, 1):
                games_dict[str(idx)] = game
            
            # Create final output with player info and games
            output = {
                "player": {
                    "name": player_name,
                    "uscf_id": player_id,
                    "rating": player_rating
                },
                "games": games_dict
            }
            
            # Output the JSON
            print(json.dumps(output, indent=2))
            
            # Close browser (tournament processing is done in separate processes)
            browser.close()

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
