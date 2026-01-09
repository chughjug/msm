#!/usr/bin/env python3
"""
AI Text Import Service - Uses Ollama (local) to extract chess player information
"""
import sys
import json
import os
import requests
import re

# Ollama settings - can be overridden via environment variables for GitHub Actions
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

def extract_players_from_text(text):
    system_prompt = """You are a JSON extraction assistant. Extract chess player information from text and return ONLY a valid JSON array.

CRITICAL JSON FORMAT REQUIREMENTS:
1. Return ONLY a valid JSON array - no explanations, no markdown, no code blocks, no text before or after
2. Start with [ and end with ]
3. Use double quotes for all strings and keys
4. Separate objects with commas
5. No trailing commas after the last item
6. All string values must be properly quoted
7. Numbers should not be quoted (except in strings)
8. If a field is missing or empty, use null or omit it entirely

Each player object must have:
- name (required, string): Player's full name - MUST be a quoted string
- uscf_id (optional, string or null): US Chess Federation ID, use null if "00000", "0000", "0", or empty
- fide_id (optional, string or null): FIDE player ID
- section (optional, string or null): Tournament section name (e.g., "Open", "Reserve", "U1200")
- city (optional, string or null): Player's city
- state (optional, string or null): Player's state/province
- rating (optional, number or null): Player's chess rating (0-3000) - must be a number, not a string
- status (optional, string): Player status, default "active" (options: "active", "withdrawn", "bye")
- team (optional, string or null): Player's team or school name (use "team" not "school")
- school (optional, string or null): Player's school name (alternative to team)
- grade (optional, number or null): Player's grade level (e.g., 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12) - must be a number, not a string
- byes (optional, array of numbers or null): Round numbers where player has intentional byes (e.g., [1,3]). IMPORTANT: If the Bye column shows "0", use null or omit the byes field entirely
- email (optional, string or null): Player's email address
- phone (optional, string or null): Player's phone number
- notes (optional, string or null): Additional notes or comments about the player

Remember: Return ONLY the JSON array, nothing else."""

    user_prompt = f"""Extract chess players from this text and return ONLY a valid JSON array following the exact format specified:

{text}

Return ONLY a JSON array starting with [ and ending with ]. No other text."""

    try:
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_ctx": 8192
            }
        }

        response = requests.post(OLLAMA_URL, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()

        generated_text = data["message"]["content"].strip()

        # === Same robust JSON extraction & cleaning logic as your original ===
        # (Kept identical for reliability)

        generated_text = re.sub(r'```json\s*', '', generated_text, flags=re.IGNORECASE)
        generated_text = re.sub(r'```\s*', '', generated_text)
        generated_text = generated_text.strip()

        json_match = re.search(r'\[[\s\S]*\]', generated_text)
        if json_match:
            generated_text = json_match.group(0)

        first_bracket = generated_text.find('[')
        last_bracket = generated_text.rfind(']')
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            generated_text = generated_text[first_bracket:last_bracket + 1]

        # Handle incomplete JSON
        if generated_text.count('[') > generated_text.count(']'):
            last_brace = generated_text.rfind('}')
            if last_brace != -1:
                partial = generated_text[:last_brace + 1]
                partial = re.sub(r',\s*$', '', partial.rstrip())
                generated_text = partial + ']'

        # Parse attempts (same as original)
        players = None
        parse_attempts = [
            lambda t: json.loads(t),
            lambda t: json.loads(re.sub(r',(\s*[}\]])', r'\1', t)),
            lambda t: json.loads(re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', t)),
            lambda t: json.loads(t.replace("'", '"')),
            lambda t: json.loads(re.sub(r',(\s*[}\]])', r'\1', re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', t))),
            lambda t: json.loads(re.sub(r',(\s*[}\]])', r'\1', re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', t.replace("'", '"')))),
        ]

        last_error = None
        for parse_func in parse_attempts:
            try:
                players = parse_func(generated_text)
                break
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e

        if players is None:
            raise ValueError(f"Failed to parse JSON. Last error: {last_error}")

        if not isinstance(players, list):
            raise ValueError("Response is not a JSON array")

        # === Normalization, validation, deduplication (same as your code) ===
        # (Keeping the full robust logic you wrote – it's excellent)

        validated_players = []
        seen_players = set()

        for player in players:
            if not isinstance(player, dict) or not player.get('name') or not str(player['name']).strip():
                continue

            name = str(player['name']).strip()
            uscf_id = player.get('uscf_id')
            if uscf_id:
                uscf_id = str(uscf_id).strip()
                if uscf_id in ['00000', '0000', '0', '']:
                    uscf_id = None

            normalized_name = ' '.join(name.split()).lower()
            normalized_name = re.sub(r'[.,-]', ' ', normalized_name)
            normalized_name = ' '.join(normalized_name.split())

            player_key = f"{normalized_name}|{uscf_id}" if uscf_id else normalized_name
            if player_key in seen_players:
                continue
            seen_players.add(player_key)

            byes = player.get('byes')
            intentional_bye_rounds = None
            if byes and byes not in [None, "0", 0]:
                if isinstance(byes, list):
                    rounds = [int(r) for r in byes if str(r).strip().isdigit() and int(str(r).strip()) > 0]
                elif isinstance(byes, str):
                    rounds = [int(r.strip()) for r in byes.split(',') if r.strip().isdigit() and int(r.strip()) > 0]
                else:
                    rounds = [int(byes)] if int(byes) > 0 else []
                intentional_bye_rounds = ','.join(map(str, rounds)) if rounds else None

            rating = player.get('rating')
            if rating is not None:
                try:
                    rating = int(rating)
                    if not (0 <= rating <= 3000):
                        rating = None
                except:
                    rating = None

            grade = player.get('grade')
            if grade is not None:
                try:
                    grade = int(grade) if str(grade).strip() not in ['0', ''] else None
                except:
                    grade = None

            validated_player = {
                'name': name,
                'status': player.get('status', 'active'),
                'section': player.get('section') or None,
                'rating': rating,
                'uscf_id': uscf_id,
                'fide_id': str(player.get('fide_id')).strip() if player.get('fide_id') else None,
                'state': player.get('state') or None,
                'city': player.get('city') or None,
                'email': player.get('email') or None,
                'phone': player.get('phone') or None,
                'team_name': player.get('team') or player.get('team_name') or None,
                'school': player.get('school') or None,
                'grade': grade,
                'intentional_bye_rounds': intentional_bye_rounds,
                'notes': player.get('notes') or None
            }

            validated_players.append(validated_player)

        # Final deduplication by flexible name matching
        final_players = []
        final_seen = set()
        for player in validated_players:
            name_parts = re.sub(r'[.,]', ' ', player['name'].lower()).split()
            sorted_parts = sorted([p for p in name_parts if len(p) > 1])
            key = ' '.join(sorted_parts)
            if player['uscf_id']:
                key += f"|{player['uscf_id']}"
            if key in final_seen:
                continue
            final_seen.add(key)
            final_players.append(player)

        result = {
            'success': True,
            'data': {
                'players': final_players,
                'count': len(final_players)
            }
        }

        duplicates_removed = len(players) - len(final_players)
        if duplicates_removed > 0:
            result['data']['duplicatesRemoved'] = duplicates_removed
            result['data']['message'] = f"Extracted {len(final_players)} unique players (removed {duplicates_removed} duplicates)"

        return result

    except requests.exceptions.ConnectionError:
        return {'success': False, 'error': 'Could not connect to Ollama. Is it running?'}
    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'Ollama request timed out'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': 'Usage: python getimport.py <text>'}, indent=2))
        sys.exit(1)
    
    text = sys.argv[1]
    
    if not text.strip():
        result = {'success': False, 'error': 'No input text provided'}
    else:
        result = extract_players_from_text(text)

    print(json.dumps(result, indent=2))