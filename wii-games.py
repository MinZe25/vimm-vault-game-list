from flask import Flask, render_template_string, request, jsonify, render_template
import requests
from bs4 import BeautifulSoup
import logging
import time  # For adding delays during scraping
import string  # For iterating A-Z
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def path(base_path: str):
    return os.path.join(BASE_DIR, base_path)


requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
# Get the directory of the current script

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__,
            template_folder=path("templates"))


# This dictionary would ideally be populated by a one-time scraping script.
# For Vimm's Lair, game names are keys, and the values are their unique IDs from the URL.
# Example: "Super Mario Galaxy" might have an ID like "17953" from vimm.net/vault/17953


def load_hardcoded_platform_games(platform="wii"):
    """Loads the Wii games dictionary from a JSON file."""
    platform_path = f"{platform.lower()}_games.json";
    if not os.path.exists(path(platform_path)):
        data = scrape_all_platform_games_from_vimm(platform)
        logger.info(f"{platform_path} not found, creating it now.")
        with open(path(platform_path), "w") as json_file:
            json.dump(data, json_file)
    with open(path(platform_path), "r") as json_file:
        return json.load(json_file)


@app.route('/')
def index():
    # all_wii = load_hardcoded_platform_games("Wii")
    # all_gamecube = load_hardcoded_platform_games("GameCube")
    # all = {'Wii': all_wii, 'Gamecube': all_gamecube}
    all_platforms = {}
    for platform in platforms:
        all_platforms[platform] = load_hardcoded_platform_games(platform)
    return render_template('index.html', all_games_dict=all_platforms)


@app.route('/get_game_size', methods=['POST'])
def get_game_size_route():
    """
    Fetches the game size from Vimm.net for a given game ID.
    Expects JSON: {"game_id": "some_id"}
    Returns JSON: {"size": "X.XX GB"} or {"error": "message"}
    """
    data = request.get_json()
    if not data or 'game_id' not in data:
        logger.warning("Get game size request with no game_id")
        return jsonify({'error': 'Game ID is required'}), 400

    game_id = data['game_id']
    game_url = f"https://vimm.net/vault/{game_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 GameListApp/1.0'
    }

    logger.info(f"Fetching size for game ID: {game_id} from {game_url}")
    size_text = "N/A"

    try:
        response = requests.get(game_url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        size_element = soup.find(id='dl_size')

        if size_element:
            size_text = size_element.get_text(strip=True)
            if not size_text:
                size_text = "Not specified"
            logger.info(f"Found size for {game_id}: {size_text}")
        else:
            size_text = "Not found"
            logger.warning(f"Size element 'download_size' not found for game ID: {game_id}")

    except requests.exceptions.Timeout:
        logger.error(f"Timeout when fetching size for game ID: {game_id}")
        return jsonify({'error': 'Timeout fetching size'}), 504
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error fetching size for game ID: {game_id} - {http_err}")
        return jsonify({'error': f'HTTP {http_err.response.status_code}'}), http_err.response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception fetching size for game ID: {game_id} - {e}")
        return jsonify({'error': 'Failed to fetch size due to network issue'}), 500

    return jsonify({'size': size_text})


def scrape_all_platform_games_from_vimm(platform="Wii"):
    """
    Scrapes all Wii game names and their IDs from Vimm.net by iterating through letter pages.
    Returns a dictionary: {"Game Name": "Game ID"}
    """
    base_url = "https://vimm.net/vault/?p=list&system={system}&section={section}"
    all_games = {}
    headers = {
        # 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 VimmScraper/1.0'
    }

    # Iterate from 'A' to 'Z' and also include '#' for games starting with numbers/symbols
    # Vimm's Lair uses 'Num' for the numeric/symbol page.
    letters_and_num = list(string.ascii_uppercase) + ['number']

    for letter in letters_and_num:
        page_url = base_url.format(system=platform, section=letter)
        print(f"Scraping page: {page_url}")

        try:
            response = requests.get(page_url, headers=headers, timeout=20, verify=False)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find the main table containing games. This selector might need adjustment
            # if Vimm's Lair changes its layout.
            # Looking for <table class="rounded">, then <tr>, then <td> with an <a> tag.
            # A more specific selector for game links:
            # Games are usually in <td> elements that have an onclick attribute starting with "window.location="
            # and contain an <a> tag with href like "/vault/xxxxx"
            game_links = soup.select('td[onclick^="window.location="] a[href^="/vault/"]')

            if not game_links:
                logger.warning(f"No game links found on page: {page_url} with the current selector.")
                # Fallback: try to find links directly within common table structures
                # This is a broader search if the specific one fails
                potential_tables = soup.find_all('table', class_='rounded')
                for table in potential_tables:
                    links_in_table = table.select('tr > td > a[href^="/vault/"]')
                    for link in links_in_table:
                        # Check if this link looks like a game link (has a numeric ID)
                        href = link.get('href')
                        game_id_part = href.split('/')[-1]
                        if game_id_part.isdigit():
                            game_links.append(link)  # Add to process
                if game_links:  # Remove duplicates if any were added
                    game_links = list(set(game_links))

            for link in game_links:
                game_name = link.get_text(strip=True)
                href = link.get('href')

                if href and game_name:
                    # Extract ID from href like "/vault/12345"
                    parts = href.split('/')
                    if len(parts) > 0 and parts[-1].isdigit():
                        game_id = parts[-1]
                        if game_name not in all_games:  # Avoid duplicates if a game is listed weirdly
                            all_games[game_name] = game_id
                            logger.info(f"Found: {game_name} - {game_id}")
                        # else:
                        #     logger.info(f"Duplicate game name found and skipped: {game_name}")
                    # else:
                    #     logger.warning(f"Could not parse game ID from href: {href} for game: {game_name}")

            logger.info(f"Finished scraping {page_url}. Total games found so far: {len(all_games)}")
            time.sleep(1)  # Be respectful to the server, wait 1 second between page loads

        except requests.exceptions.Timeout:
            logger.error(f"Timeout when scraping page: {page_url}")
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error scraping page: {page_url} - {http_err}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception for page: {page_url} - {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while scraping {page_url}: {e}")

    logger.info(f"Scraping complete. Total unique games found: {len(all_games)}")
    return all_games


# Example of how to use the scraper function (e.g., in a Colab notebook):
# if __name__ == '__main__':
# To populate your HARDCODED_WII_GAMES:
# print("Starting to scrape Vimm's Lair for Wii games...")


# print(f"\nScraped {len(wii_games_data)} games.")
# 
# # You can then print it in a format easy to copy-paste:
# print("\nCopy the following dictionary into your HARDCODED_WII_GAMES variable:")
# print("HARDCODED_WII_GAMES = {")
# for i, (name, game_id) in enumerate(sorted(wii_games_data.items())):
#     print(f'    "{name}": "{game_id}",')
# print("}")
#
# # To run the Flask app (if not using a dedicated WSGI server like Gunicorn for Colab):
# # Note: Flask's built-in server is not for production.
# # For Colab, you might need to expose the port using ngrok or similar if you want to access it externally.
platforms = ["Wii", "GameCube", "PSP", "DS", "GBA", "N64", "PS2", "Xbox360"]

if __name__ == '__main__':
    # Save scraped data to a JSON file
    logger.info(f"Loading hardcoded games for platforms: {platforms}")
    for platform in platforms:
        load_hardcoded_platform_games(platform)
    app.run(host='0.0.0.0', port=5000)  # Runs the Flask app
