from playwright.sync_api import sync_playwright
import json
import sys
import re
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
            
            # Get rating - look for rating numbers on the page
            page_text = page.evaluate('() => document.body.innerText')
            # Look for rating patterns (3-4 digit numbers, often near "Rating" text)
            rating_patterns = [
                r'Rating[:\s]+(\d{3,4})',
                r'(\d{3,4})\s*Rating',
                r'Regular[:\s]+(\d{3,4})',
                r'Quick[:\s]+(\d{3,4})',
                r'Blitz[:\s]+(\d{3,4})',
            ]
            
            for pattern in rating_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    try:
                        rating = int(match.group(1))
                        if 100 <= rating <= 3000:  # Valid rating range
                            player_rating = rating
                            break
                    except:
                        continue
            
            # If no rating found with patterns, look for any 3-4 digit number
            if player_rating is None:
                numbers = re.findall(r'\b(\d{3,4})\b', page_text)
                for num_str in numbers:
                    try:
                        num = int(num_str)
                        if 100 <= num <= 3000:
                            player_rating = num
                            break
                    except:
                        continue
                        
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
                                            
                                            # Get opponent rating from the row
                                            opp_rating = None
                                            try:
                                                # Ratings are typically in table cells - look for 3-4 digit numbers
                                                row_text = row.inner_text()
                                                # Look for rating patterns in the row
                                                rating_match = re.search(r'\b(\d{3,4})\b', row_text)
                                                if rating_match:
                                                    # Check if it's a valid rating (not pairing number, not year, etc.)
                                                    potential_rating = int(rating_match.group(1))
                                                    if 100 <= potential_rating <= 3000:
                                                        # Make sure it's not the pairing number
                                                        if str(potential_rating) != pairing_num:
                                                            opp_rating = potential_rating
                                                # Alternative: look for rating in specific cells (usually 2nd or 3rd td)
                                                if opp_rating is None:
                                                    row_tds = row.locator('td').all()
                                                    # Rating is often in the 2nd or 3rd column
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
                                            except Exception as e:
                                                pass  # Rating extraction failed, continue without it
                                            
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
                                        
                                        opponent = pairing_to_opponent.get(opp_num, {"name": "Unknown", "uscf_id": None, "rating": None})
                                        
                                        # Add game to the flat list with only requested fields
                                        game = {
                                            "tournament_name": tournament_title,
                                            "round": i,
                                            "result": result,
                                            "opponent_pairing_number": opp_num,
                                            "opponent_name": opponent["name"],
                                            "opponent_uscf_id": opponent["uscf_id"],
                                            "opponent_rating": opponent.get("rating"),
                                            "color": color,
                                            "player_name": player_name,
                                            "player_uscf_id": player_id,
                                            "player_rating": player_rating
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
        
        browser.close()

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
