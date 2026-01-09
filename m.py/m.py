from playwright.sync_api import sync_playwright
import json
import sys
import re
import time
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Get player ID from command line argument or use default
if len(sys.argv) > 1:
    player_id = sys.argv[1]
else:
    player_id = '31979530'  # Default player ID

base_url = 'https://ratings.uschess.org'
player_url = f'{base_url}/player/{player_id}'

# Lock for thread-safe printing
print_lock = threading.Lock()

def process_year(player_id, year, player_name, max_workers=3):
    """Process a single year's games in parallel with multiple browser contexts"""
    games = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            with print_lock:
                print(f"Processing year {year}...", file=sys.stderr)
            
            page.goto(player_url, wait_until='networkidle', timeout=60000)  # Increased timeout
            page.wait_for_timeout(5000)  # Increased wait time to avoid rate limiting
            
            # Wait for table to be ready
            try:
                page.wait_for_selector('table, tbody', timeout=10000)
                page.wait_for_timeout(2000)  # Additional wait for content to render
            except:
                pass
            
            # Find the year row - try multiple strategies
            year_tbody = None
            selectors = [
                'tbody.divide-y',
                'tbody',
                'table tbody',
                '[class*="year"] tbody',
                'table:has(thead) tbody'
            ]
            
            for selector in selectors:
                try:
                    tbody_locator = page.locator(selector).first
                    if tbody_locator.count() > 0:
                        rows = tbody_locator.locator('tr').all()
                        if len(rows) > 0:
                            year_tbody = tbody_locator
                            break
                except:
                    continue
            
            if year_tbody is None:
                year_tbody = page.locator('tbody').first
            
            year_rows = year_tbody.locator('tr').all()
            year_row = None
            
            # Find the row for this year
            for row in year_rows:
                year_td = row.locator('td').first
                year_text = year_td.inner_text().strip()
                if year_text == year:
                    year_row = row
                    break
            
            if year_row is None:
                with print_lock:
                    print(f"  Could not find year {year} row", file=sys.stderr)
                browser.close()
                return games
            
            # Find and click the games button
            games_button = year_row.locator('button:has(svg.lucide-games)').first
            if games_button.count() == 0:
                last_td = year_row.locator('td').last
                games_button = last_td.locator('button').first
            
            if games_button.count() == 0:
                with print_lock:
                    print(f"  No games button found for year {year}", file=sys.stderr)
                browser.close()
                return games
            
            # Click the button
            try:
                games_button.evaluate('button => button.click()')
                page.wait_for_timeout(3000)  # Increased wait time to avoid rate limiting
            except Exception as e:
                with print_lock:
                    print(f"  Error clicking button for year {year}: {e}", file=sys.stderr)
                browser.close()
                return games
            
            # Find the games table
            games_table = None
            try:
                page.wait_for_selector('table thead:has-text("Result")', timeout=10000)  # Increased timeout
            except:
                pass
            
            all_tables = page.locator('table').all()
            for table in all_tables:
                thead = table.locator('thead').first
                if thead.count() > 0:
                    thead_text = thead.inner_text().upper()
                    if "RESULT" in thead_text and "OPPONENT" in thead_text:
                        if "YEAR" not in thead_text:
                            games_table = table
                            break
            
            if games_table is None:
                with print_lock:
                    print(f"  No games table found for year {year}", file=sys.stderr)
                browser.close()
                return games
            
            # Click "Load more..." button repeatedly until all games are loaded
            max_clicks = 50  # Safety limit
            clicks = 0
            previous_count = 0
            
            while clicks < max_clicks:
                # Check for "Load more..." button
                load_more_button = page.locator('button:has-text("Load more")').first
                if load_more_button.count() == 0:
                    # Try alternative selector
                    load_more_button = page.locator('button:has-text("Load more...")').first
                
                if load_more_button.count() == 0:
                    # No more button found, all games loaded
                    break
                
                # Check current game count
                current_rows = games_table.locator('tbody tr').all()
                current_count = len(current_rows)
                
                if current_count == previous_count:
                    # No new games loaded, button might be stuck
                    break
                
                # Click the button
                try:
                    load_more_button.click()
                    page.wait_for_timeout(3000)  # Increased wait time to avoid rate limiting
                    clicks += 1
                    previous_count = current_count
                    
                    # Re-find the games table after loading more
                    games_table = None
                    all_tables = page.locator('table').all()
                    for table in all_tables:
                        thead = table.locator('thead').first
                        if thead.count() > 0:
                            thead_text = thead.inner_text().upper()
                            if "RESULT" in thead_text and "OPPONENT" in thead_text:
                                if "YEAR" not in thead_text:
                                    games_table = table
                                    break
                    
                    if games_table is None:
                        break
                except Exception as e:
                    with print_lock:
                        print(f"  Error clicking Load more button: {e}", file=sys.stderr)
                    break
            
            if clicks > 0:
                with print_lock:
                    print(f"  Clicked 'Load more' {clicks} times for year {year}", file=sys.stderr)
            
            # Get all game rows after loading all games
            game_rows = games_table.locator('tbody tr').all()
            with print_lock:
                print(f"  Found {len(game_rows)} total games for year {year}", file=sys.stderr)
            
            # Process games - can parallelize rating extraction
            def extract_game_with_rating(game_row, year, player_name, player_id, context):
                """Extract a single game and its opponent rating"""
                try:
                    cells = game_row.locator('td').all()
                    if len(cells) < 6:
                        return None
                    
                    result = cells[0].inner_text().strip()
                    if result in ["Result", "Year", ""] or not result:
                        return None
                    
                    color_text = cells[1].inner_text().strip()
                    if color_text == "W" or "W" in color_text:
                        color = "White"
                    elif color_text == "B" or "B" in color_text:
                        color = "Black"
                    else:
                        color = "Unknown"
                    
                    opponent_cell = cells[3]
                    opponent_link = opponent_cell.locator('a[href^="/player/"]').first
                    
                    opponent_name = "Unknown"
                    opponent_uscf_id = None
                    opponent_rating = None
                    
                    if opponent_link.count() > 0:
                        name_container = opponent_link.locator('div.font-names').first
                        if name_container.count() > 0:
                            name_text = name_container.inner_text().strip()
                            if name_text:
                                opponent_name = ' '.join(name_text.split())
                        
                        href = opponent_link.get_attribute('href')
                        if href:
                            opponent_uscf_id = href.split('/')[-1]
                    
                    date = cells[4].inner_text().strip()
                    
                    tournament_cell = cells[5]
                    tournament_link = tournament_cell.locator('a[href^="/event/"]').first
                    tournament_name = "Unknown Tournament"
                    tournament_url = None
                    if tournament_link.count() > 0:
                        tournament_name = tournament_link.locator('span').first.inner_text().strip()
                        href = tournament_link.get_attribute('href')
                        if href:
                            tournament_url = urljoin(base_url, href)
                    
                    # Skip opponent rating extraction for speed - can be added back if needed
                    # Rating extraction requires visiting each tournament page which is very slow
                    opponent_rating = None
                    
                    game = {
                        "tournament_name": tournament_name,
                        "round": None,
                        "result": result,
                        "opponent_pairing_number": None,
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
                    
                    return game
                except Exception as e:
                    with print_lock:
                        print(f"  Error extracting game: {e}", file=sys.stderr)
                    return None
            
            # Extract games - can process in parallel for rating extraction
            # But for now, process sequentially to avoid too many browser contexts
            for game_row in game_rows:
                game = extract_game_with_rating(game_row, year, player_name, player_id, context)
                if game:
                    games.append(game)
            
            browser.close()
            return games
            
    except Exception as e:
        with print_lock:
            print(f"Error processing year {year}: {e}", file=sys.stderr)
        return games

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        print(f"Loading player page: {player_url}\n", file=sys.stderr)
        page.goto(player_url, wait_until='networkidle', timeout=60000)  # Increased timeout
        page.wait_for_timeout(5000)  # Increased wait time to avoid rate limiting
        
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
        
        # Find the tbody with year statistics - try multiple strategies with retries
        year_tbody = None
        max_retries = 3
        for retry in range(max_retries):
            try:
                # Wait for any table to appear
                page.wait_for_selector('table, tbody', timeout=10000)
                page.wait_for_timeout(2000)  # Additional wait for content to render
                
                # Try multiple selector strategies
                selectors = [
                    'tbody.divide-y',
                    'tbody',
                    'table tbody',
                    '[class*="year"] tbody',
                    'table:has(thead) tbody'
                ]
                
                for selector in selectors:
                    try:
                        tbody_locator = page.locator(selector).first
                        if tbody_locator.count() > 0:
                            # Verify it has rows
                            rows = tbody_locator.locator('tr').all()
                            if len(rows) > 0:
                                year_tbody = tbody_locator
                                print(f"Found year statistics table using selector: {selector} ({len(rows)} rows)", file=sys.stderr)
                                break
                    except:
                        continue
                
                if year_tbody is not None:
                    break
                    
            except Exception as e:
                print(f"Retry {retry + 1}/{max_retries} failed: {e}", file=sys.stderr)
                if retry < max_retries - 1:
                    page.wait_for_timeout(3000)
                    page.reload(wait_until='networkidle', timeout=30000)
                    page.wait_for_timeout(3000)
        
        if year_tbody is None or year_tbody.count() == 0:
            # Debug: print page content to help diagnose
            try:
                page_title = page.title()
                page_url = page.url
                print(f"Page title: {page_title}", file=sys.stderr)
                print(f"Page URL: {page_url}", file=sys.stderr)
                tables_count = page.locator('table').count()
                tbody_count = page.locator('tbody').count()
                print(f"Found {tables_count} tables and {tbody_count} tbody elements on page", file=sys.stderr)
            except:
                pass
            print("No year statistics table found after retries.", file=sys.stderr)
            browser.close()
            sys.exit(1)
        
        # Get all year rows and extract years
        year_rows = year_tbody.locator('tr').all()
        print(f"Found {len(year_rows)} years of data.\n", file=sys.stderr)
        
        years = []
        for year_row in year_rows:
            year_td = year_row.locator('td').first
            year_text = year_td.inner_text().strip()
            if year_text.isdigit():
                years.append(year_text)
        
        # Sort years in descending order (most recent first)
        years.sort(reverse=True)
        
        browser.close()
        
        # Process all years in parallel
        print(f"Processing {len(years)} years ({', '.join(years)}) in parallel...\n", file=sys.stderr)
        all_games = []
        
        # Use ThreadPoolExecutor to process multiple years in parallel
        # Each year gets its own browser instance
        # Reduced parallelism to avoid rate limiting
        max_workers = min(2, len(years))  # Process up to 2 years in parallel to avoid rate limiting
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all year processing tasks with staggered delays to avoid rate limiting
            future_to_year = {}
            for idx, year in enumerate(years):
                # Add a small delay between starting each year to avoid hitting rate limits
                if idx > 0:
                    time.sleep(2)  # 2 second delay between starting each year
                future_to_year[executor.submit(process_year, player_id, year, player_name)] = year
            
            # Collect results as they complete
            for future in as_completed(future_to_year):
                year = future_to_year[future]
                try:
                    year_games = future.result()
                    all_games.extend(year_games)
                    with print_lock:
                        print(f"Completed year {year}: {len(year_games)} games", file=sys.stderr)
                except Exception as e:
                    with print_lock:
                        print(f"Year {year} generated an exception: {e}", file=sys.stderr)
        
        # Sort games by date (most recent first)
        # Parse dates and sort in descending order
        def get_sort_key(game):
            date_str = game.get('date', '')
            if date_str:
                try:
                    # Date format is YYYY-MM-DD
                    year, month, day = date_str.split('-')
                    return (int(year), int(month), int(day))
                except:
                    # If date parsing fails, use year as fallback
                    year_str = game.get('year', '0')
                    try:
                        return (int(year_str), 0, 0)
                    except:
                        return (0, 0, 0)
            else:
                # Fallback to year if no date
                year_str = game.get('year', '0')
                try:
                    return (int(year_str), 0, 0)
                except:
                    return (0, 0, 0)
        
        # Sort games by date descending (most recent first)
        sorted_games = sorted(all_games, key=get_sort_key, reverse=True)
        
        # Format output
        games_dict = {}
        for idx, game in enumerate(sorted_games, 1):
            games_dict[str(idx)] = game
        
        output = {
            "player": {
                "name": player_name,
                "uscf_id": player_id,
                "rating": None
            },
            "games": games_dict
        }
        
        print(json.dumps(output, indent=2))

except Exception as e:
    error_output = {
        "error": str(e),
        "player_id": player_id
    }
    print(json.dumps(error_output, indent=2), file=sys.stderr)
    sys.exit(1)
