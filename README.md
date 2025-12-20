# US Chess Game Scraper

A Python script to scrape chess game history from US Chess ratings website using Playwright.

## Features

- Scrapes the past 10 tournaments for a given player
- Returns all games in JSON format
- Fast and efficient using Playwright browser automation
- Deduplicates tournaments to avoid processing duplicates

## Local Usage

### Prerequisites

- Python 3.11+
- pip

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Running the Script

```bash
# Run with a player ID as argument
python m.py/m.py <player_id>

# Example
python m.py/m.py 31979530
```

The script will output a JSON object with numbered games (1, 2, 3, ...) containing:
- Tournament name
- Round number
- Result (W/L/D)
- Opponent information (name, USCF ID, pairing number)
- Color played (White/Black)
- Player information (name, USCF ID)

## GitHub Actions

This repository includes a GitHub Actions workflow that can be triggered manually with a player ID.

### How to Use

#### Option 1: Trigger via GitHub UI

1. Go to the "Actions" tab in your GitHub repository
2. Select "Run Chess Game Scraper" workflow
3. Click "Run workflow"
4. Enter the US Chess Player ID you want to scrape
5. Click "Run workflow"

#### Option 2: Trigger via Command Line Script

Use the provided Python script to trigger the workflow programmatically:

```bash
# Set your GitHub token as an environment variable
export GITHUB_TOKEN='your_github_token_here'

# Trigger the workflow with a player ID
python trigger_workflow.py <player_id>

# Example
python trigger_workflow.py 31979530
```

The script will trigger the workflow and provide a link to view the run status.

### Workflow Output

The workflow will:
- Run the scraper with your provided player ID
- Output the JSON result in the workflow logs
- Create an artifact file (`chess-games-<player_id>.json`) that you can download

### Output

The JSON output will be available:
1. In the workflow logs (scroll down to "Output JSON result")
2. As a downloadable artifact (available for 7 days)

## Output Format

```json
{
  "1": {
    "tournament_name": "Tournament Name",
    "round": 1,
    "result": "W",
    "opponent_pairing_number": "5",
    "opponent_name": "Opponent Name",
    "opponent_uscf_id": "12345678",
    "color": "White",
    "player_name": "Player Name",
    "player_uscf_id": "31979530"
  },
  "2": {
    ...
  }
}
```

## License

MIT

