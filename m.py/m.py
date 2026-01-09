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
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        print(f"Loading player page: {player_url}\n", file=sys.stderr)
        page.goto(player_url, wait_until='networkidle', timeout=30000)
        
        # Wait for page to fully render
        page.wait_for_timeout(2000)
        
        # Extract player name
        player_name = "Unknown"
        try:
            name_elements = page.locator('h1, h2, [class*="name"], [class*="player"]').all()
            for elem in name_elements[:5]:
                text = elem.inner_text().strip()
                if text and len(text) > 2 and player_id not in text:
                    player_name = ' '.join(text.split())
                    if len(player_name) > 3:
                        break
        except Exception as e:
            print(f"Could not extract player name: {e}", file=sys.stderr)
        
        # Find the tbody with year statistics
        # The tbody has classes: divide-y divide-border bg-background
        year_tbody = page.locator('tbody.divide-y').first
        
        if year_tbody.count() == 0:
            # Try alternative selector
            year_tbody = page.locator('tbody').first
            if year_tbody.count() == 0:
                print("No year statistics table found.", file=sys.stderr)
                browser.close()
                sys.exit(1)
        
        # Get all year rows (tr elements within the tbody)
        year_rows = year_tbody.locator('tr').all()
        print(f"Found {len(year_rows)} years of data.\n", file=sys.stderr)
        
        all_games = []
        game_counter = 1
        
        # Process each year
        for year_idx, year_row in enumerate(year_rows):
            try:
                # Get the year from the first column
                year_td = year_row.locator('td').first
                year_text = year_td.inner_text().strip()
                year = year_text if year_text.isdigit() else None
                
                if not year:
                    continue
                
                print(f"Processing year {year}...", file=sys.stderr)
                
                # Find the button with the games icon (last column)
                # The button contains SVG with class "lucide-games"
                # Try multiple selectors to find the button
                games_button = year_row.locator('button:has(svg.lucide-games)').first
                
                if games_button.count() == 0:
                    # Try alternative: button in last td
                    last_td = year_row.locator('td').last
                    games_button = last_td.locator('button').first
                
                if games_button.count() == 0:
                    print(f"  No games button found for year {year}", file=sys.stderr)
                    continue
                
                # Click the button to open the games table
                try:
                    games_button.evaluate('button => button.click()')
                    page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"  Error clicking button for year {year}: {e}", file=sys.stderr)
                    continue
                
                # Wait for the games table to appear
                # The table should have a thead with "Result" column
                games_table = None
                try:
                    # Wait for table with specific structure to appear
                    page.wait_for_selector('table thead:has-text("Result")', timeout=5000)
                except:
                    pass
                
                # Now look for the games table
                all_tables = page.locator('table').all()
                
                for table in all_tables:
                    thead = table.locator('thead').first
                    if thead.count() > 0:
                        thead_text = thead.inner_text().upper()  # Convert to uppercase for comparison
                        # Games table should have "RESULT" and "OPPONENT" in thead
                        if "RESULT" in thead_text and "OPPONENT" in thead_text:
                            # Make sure this isn't the year statistics table
                            # Year stats table has "YEAR" in thead, games table doesn't
                            if "YEAR" not in thead_text:
                                games_table = table
                                break
                    
                if games_table is None:
                    print(f"  No games table found for year {year}", file=sys.stderr)
                    # Debug: print all table headers found
                    print(f"    Found {len(all_tables)} tables on page", file=sys.stderr)
                    for idx, table in enumerate(all_tables[:3]):  # Print first 3
                        try:
                            thead = table.locator('thead').first
                            if thead.count() > 0:
                                print(f"    Table {idx} thead: {thead.inner_text()[:100]}", file=sys.stderr)
                        except:
                            pass
                    # Try to close any open modals/overlays
                    try:
                        page.keyboard.press('Escape')
                        page.wait_for_timeout(500)
                    except:
                        pass
                    continue
                
                # Get all game rows from tbody (skip header row if present)
                game_rows = games_table.locator('tbody tr').all()
                
                print(f"  Found {len(game_rows)} games for year {year}", file=sys.stderr)
                
                # Extract games from the table
                for game_row in game_rows:
                    try:
                        # Check if browser/page is still valid
                        try:
                            page.title()  # Quick check if page is still valid
                        except:
                            print(f"  Browser/page closed unexpectedly for year {year}", file=sys.stderr)
                            break
                        
                        # Get all cells
                        cells = game_row.locator('td').all()
                        
                        if len(cells) < 6:
                            continue
                        
                        # Extract data from each column
                        # Column 0: Result (W/L/D)
                        try:
                            result = cells[0].inner_text().strip()
                        except Exception as e:
                            print(f"  Error getting result: {e}", file=sys.stderr)
                            continue
                        
                        # Skip if this looks like a header row or invalid data
                        if result in ["Result", "Year", ""] or not result:
                            continue
                        
                        # Column 1: Color (W/B)
                        color_text = cells[1].inner_text().strip()
                        # Handle cases where color might be "--" or empty
                        if color_text == "W" or "W" in color_text:
                            color = "White"
                        elif color_text == "B" or "B" in color_text:
                            color = "Black"
                        else:
                            color = "Unknown"
                        
                        # Column 3: Opponent (contains link with name and USCF ID)
                        opponent_cell = cells[3]
                        opponent_link = opponent_cell.locator('a[href^="/player/"]').first
                        
                        opponent_name = "Unknown"
                        opponent_uscf_id = None
                        opponent_rating = None
                        
                        if opponent_link.count() > 0:
                            # Extract opponent name from nested div structure
                            # Structure: div.font-names > div > span (first name) + span (last name)
                            name_container = opponent_link.locator('div.font-names').first
                            if name_container.count() > 0:
                                # Get all text from the name container
                                name_text = name_container.inner_text().strip()
                                if name_text:
                                    # Clean up the name (remove extra whitespace)
                                    opponent_name = ' '.join(name_text.split())
                            
                            # Extract opponent USCF ID from href
                            href = opponent_link.get_attribute('href')
                            if href:
                                opponent_uscf_id = href.split('/')[-1]
                        
                        # Column 4: Date
                        date = cells[4].inner_text().strip()
                        
                        # Column 5: Tournament name and section
                        tournament_cell = cells[5]
                        tournament_link = tournament_cell.locator('a[href^="/event/"]').first
                        tournament_name = "Unknown Tournament"
                        tournament_url = None
                        if tournament_link.count() > 0:
                            tournament_name = tournament_link.locator('span').first.inner_text().strip()
                            href = tournament_link.get_attribute('href')
                            if href:
                                tournament_url = urljoin(base_url, href)
                        
                        # Extract opponent rating from tournament page if we have the URL and opponent info
                        if tournament_url and opponent_uscf_id:
                            try:
                                print(f"    Extracting rating for opponent {opponent_uscf_id} from tournament...", file=sys.stderr)
                                # Navigate to tournament page in a new page to avoid affecting main page
                                tournament_page = context.new_page()
                                try:
                                    tournament_page.goto(tournament_url, wait_until='networkidle', timeout=30000)
                                    tournament_page.wait_for_timeout(2000)
                                    
                                    # Find the opponent in the tournament pairing table
                                    # Look for a link to the opponent's player page
                                    opponent_row = None
                                    
                                    # Try to find the opponent by their player link
                                    opponent_links = tournament_page.locator(f'a[href="/player/{opponent_uscf_id}"]').all()
                                    
                                    if len(opponent_links) > 0:
                                        # Find the parent row (tr) containing this link
                                        for link in opponent_links:
                                            try:
                                                # Get the parent row
                                                row = link.locator('xpath=ancestor::tr').first
                                                if row.count() > 0:
                                                    # Check if this row has rating information
                                                    cells_in_row = row.locator('td').all()
                                                    if len(cells_in_row) > 0:
                                                        opponent_row = row
                                                        break
                                            except:
                                                continue
                                    
                                    # Extract rating from the row
                                    if opponent_row:
                                        try:
                                            # Rating is typically in one of the cells
                                            # Look for numeric rating values in the row
                                            row_text = opponent_row.inner_text()
                                            # Try to find rating pattern (usually 4 digits)
                                            rating_match = re.search(r'\b(\d{3,4})\b', row_text)
                                            if rating_match:
                                                potential_rating = rating_match.group(1)
                                                # Check if it's a reasonable rating (between 100 and 3000)
                                                rating_int = int(potential_rating)
                                                if 100 <= rating_int <= 3000:
                                                    opponent_rating = rating_int
                                                    print(f"      Found rating: {opponent_rating}", file=sys.stderr)
                                            
                                            # Alternative: look for rating in specific cell positions
                                            # Tournament tables vary, so try multiple approaches
                                            if opponent_rating is None:
                                                cells_in_row = opponent_row.locator('td').all()
                                                for cell in cells_in_row:
                                                    cell_text = cell.inner_text().strip()
                                                    # Check if cell contains a 3-4 digit number
                                                    cell_rating_match = re.search(r'\b(\d{3,4})\b', cell_text)
                                                    if cell_rating_match:
                                                        potential_rating = int(cell_rating_match.group(1))
                                                        if 100 <= potential_rating <= 3000:
                                                            opponent_rating = potential_rating
                                                            print(f"      Found rating: {opponent_rating}", file=sys.stderr)
                                                            break
                                        except Exception as e:
                                            print(f"      Error extracting rating from row: {e}", file=sys.stderr)
                                finally:
                                    # Always close the tournament page
                                    try:
                                        tournament_page.close()
                                    except:
                                        pass
                                
                            except Exception as e:
                                print(f"    Error navigating to tournament page: {e}", file=sys.stderr)
                                # Continue without rating
                        
                        # Create game object
                        game = {
                            "tournament_name": tournament_name,
                            "round": None,  # Round info not available in this view
                            "result": result,
                            "opponent_pairing_number": None,  # Not available in this view
                            "opponent_name": opponent_name,
                            "opponent_uscf_id": opponent_uscf_id,
                            "opponent_rating": opponent_rating,
                            "color": color,
                            "player_name": player_name,
                            "player_uscf_id": player_id,
                            "player_rating": None,
                            "date": date,
                            "year": year
                        }
                        
                        all_games.append(game)
                        game_counter += 1
                        
                    except Exception as e:
                        print(f"  Error extracting game from row: {e}", file=sys.stderr)
                        continue
                
                # Close the games table by pressing Escape or clicking outside
                # Try to find and click a close button, or press Escape
                # Check if page is still valid first
                try:
                    page.title()  # Quick check if page is still valid
                    try:
                        page.keyboard.press('Escape')
                        page.wait_for_timeout(500)
                    except:
                        pass
                    
                    # Also try clicking outside the table to close it
                    try:
                        # Click on a neutral area (like the page background)
                        page.click('body', position={'x': 10, 'y': 10})
                        page.wait_for_timeout(500)
                    except:
                        pass
                except:
                    # Page is closed or invalid, skip closing the table
                    print(f"  Warning: Page became invalid, skipping table close for year {year}", file=sys.stderr)
                    pass
                
            except Exception as e:
                print(f"Error processing year {year if 'year' in locals() else 'unknown'}: {e}", file=sys.stderr)
                continue
            
            # Format output as numbered games 1 to n
            games_dict = {}
            for idx, game in enumerate(all_games, 1):
                games_dict[str(idx)] = game
            
            # Create final output with player info and games
            output = {
                "player": {
                    "name": player_name,
                    "uscf_id": player_id,
                "rating": None
                },
                "games": games_dict
            }
            
            # Output the JSON
            print(json.dumps(output, indent=2))
            
            browser.close()

except Exception as e:
    error_output = {
        "error": str(e),
        "player_id": player_id
    }
    print(json.dumps(error_output, indent=2), file=sys.stderr)
    sys.exit(1)
