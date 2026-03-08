"""
Quiz Please Game Stats Collector Lambda Function

Periodically checks for new quiz games from yerevan.quizplease.ru and stores
their data in PostgreSQL database.
"""
import logging
import os
import re
from functools import wraps
from time import sleep
from typing import List, Dict, Optional, Tuple

import psycopg2
import requests as req
from bs4 import BeautifulSoup

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Constants
MAIN_URL = 'https://yerevan.quizplease.ru/schedule-past'
GAME_URL_TEMPLATE = 'https://yerevan.quizplease.ru/schedule-past?page={}'
GAME_PAGE_URL_TEMPLATE = 'https://yerevan.quizplease.ru/game-page?id={}'

# Month translation dictionary (Russian to numeric)
MONTH_TRANSLATION = {
    'января': '01',
    'февраля': '02',
    'марта': '03',
    'апреля': '04',
    'мая': '05',
    'июня': '06',
    'июля': '07',
    'августа': '08',
    'сентября': '09',
    'октября': '10',
    'ноября': '11',
    'декабря': '12',
}

# Headers to mimic a real browser (helps avoid CAPTCHA)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
    'Referer': 'https://yerevan.quizplease.ru/schedule',
}

# Create a persistent session to maintain cookies (helps avoid CAPTCHA)
session = req.Session()
session.headers.update(HEADERS)

# Flag to track if we've visited the schedule page (for session establishment)
_schedule_visited = False


def retry_on_failure(max_attempts=3, delay_seconds=20):
    """
    Decorator that retries a function up to max_attempts times with a delay between attempts.
    Useful for handling transient network errors and CAPTCHA issues.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f'{func.__name__} failed on attempt {attempt}/{max_attempts}: {e}. '
                            f'Retrying in {delay_seconds}s...'
                        )
                        sleep(delay_seconds)
                    else:
                        logger.error(f'{func.__name__} failed after {max_attempts} attempts: {e}')
            raise last_exception
        return wrapper
    return decorator


def get_db_connection():
    """
    Creates and returns a PostgreSQL database connection using environment variables.
    """
    return psycopg2.connect(
        host=os.environ['DB_HOST'],
        port=os.environ.get('DB_PORT', '5432'),
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )


def ensure_schedule_visited():
    """
    Ensures the schedule page has been visited to establish a proper session.
    This helps avoid CAPTCHA on game pages by establishing cookies and session.
    """
    global _schedule_visited
    if not _schedule_visited:
        try:
            logger.info('Visiting schedule page to establish session and avoid CAPTCHA...')
            session.get(MAIN_URL)
            _schedule_visited = True
            sleep(2)  # Small delay to appear more human-like
            logger.info('Session established successfully')
        except Exception as e:
            logger.warning(f'Failed to pre-visit schedule page: {e}')


def get_last_processed_game_id() -> int:
    """
    Retrieves the highest game ID from the database.
    Returns 0 if no games exist yet.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(id), 0) FROM quizplease.games")
                result = cur.fetchone()
                last_id = result[0] if result else 0
                logger.info(f"Last processed game ID: {last_id}")
                return last_id
    except Exception as e:
        logger.error(f"Failed to get last game ID: {e}")
        raise


def get_games_without_results() -> List[int]:
    """
    Retrieves game IDs that exist in the games table but have no team participation data.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT g.id
                    FROM quizplease.games g
                    LEFT JOIN quizplease.team_game_participations p ON g.id = p.game_id
                    WHERE p.id IS NULL
                    ORDER BY g.id
                """)
                game_ids = [row[0] for row in cur.fetchall()]
                if game_ids:
                    logger.info(f"Found {len(game_ids)} games without results: {game_ids}")
                return game_ids
    except Exception as e:
        logger.error(f"Failed to get games without results: {e}")
        raise


def get_game_ids(last_game_id: int) -> List[int]:
    """
    Fetches new game IDs from the website that are greater than last_game_id.
    """
    global _schedule_visited
    try:
        # Ensure we've visited the schedule page first to avoid CAPTCHA
        ensure_schedule_visited()

        main_page = session.get(MAIN_URL)
        main_page.raise_for_status()
        _schedule_visited = True  # Mark as visited
        sleep(2)  # Small delay to appear more human-like

        main_soup = BeautifulSoup(main_page.content, 'html.parser')

        # Find pagination to determine number of pages
        # Extract the maximum page number from pagination links
        pagination = main_soup.find('ul', class_='pagination')
        game_page_counter = 1
        if pagination:
            # Find all page numbers in the pagination
            page_numbers = []
            for li in pagination.find_all('li'):
                text = li.get_text(strip=True)
                if text.isdigit():
                    page_numbers.append(int(text))

            # Use the maximum page number found
            if page_numbers:
                game_page_counter = max(page_numbers)
                logger.info(f"Found pagination with max page: {game_page_counter}")
            else:
                # Fallback to counting li elements if no numbers found
                game_page_counter = len(pagination.find_all('li')) - 2
                logger.warning(f"No page numbers found in pagination, using fallback: {game_page_counter}")
        else:
            logger.warning("No pagination found, assuming single page")

        game_ids = []
        for page in range(1, game_page_counter + 1):
            games_url = GAME_URL_TEMPLATE.format(page)
            games_page = session.get(games_url)
            games_page.raise_for_status()
            sleep(2)  # Delay between page requests

            games_soup = BeautifulSoup(games_page.content, 'html.parser')

            # Extract game IDs from the available game buttons
            game_buttons = games_soup.find_all("div", class_='game-buttons available')
            page_game_ids = [
                int(re.findall(r'id=(\d+)', str(button))[0])
                for button in game_buttons
                if re.findall(r'id=(\d+)', str(button))
            ]

            # Filter out game IDs that are not greater than the last game ID
            new_game_ids = [game_id for game_id in page_game_ids if game_id > last_game_id]

            if not new_game_ids:
                # If there are no new game IDs on this page, stop fetching more pages
                break

            game_ids.extend(new_game_ids)

        # Return in chronological order (oldest first)
        return sorted(game_ids)
    except Exception as e:
        logger.error(f"Failed to get game IDs: {e}")
        return []


def parse_date_from_game_page(soup: BeautifulSoup, game_id: int) -> Tuple[str, Optional[str]]:
    """
    Parses date and time from game page.
    Returns tuple of (date in YYYY-MM-DD format, time).
    """
    info_columns = soup.find_all("div", class_="game-info-column")

    # Find the column with date (contains a month name)
    date_text = None
    time_text = None

    for col in info_columns:
        text_elem = col.find('div', class_='text')
        if text_elem:
            text_content = text_elem.get_text(strip=True)
            # Check if this contains a month name
            if any(month in text_content for month in MONTH_TRANSLATION.keys()):
                date_text = text_content.split()
                # Try to find time
                time_elem = col.find('div', class_='text text-grey')
                if time_elem:
                    time_parts = time_elem.text.split()
                    if time_parts and ':' in time_parts[-1]:
                        time_text = time_parts[-1]
                break

    if not date_text:
        logger.warning(f"Could not parse date for game {game_id}, using placeholder")
        return "2025-01-01", None

    # Parse date: [day, month_name] or [day, month_name, time]
    day = date_text[0].zfill(2)
    month = MONTH_TRANSLATION.get(date_text[1], '01')

    # Determine year based on game ID
    if game_id < 49999:
        year = "2022"
    elif game_id < 69919:
        year = "2023"
    elif game_id < 93630:
        year = "2024"
    elif game_id < 119884:
        year = "2025"
    else:
        year = "2026"

    full_date = f"{year}-{month}-{day}"
    return full_date, time_text


@retry_on_failure(max_attempts=5, delay_seconds=60)
def parse_game_data(game_id: int) -> Optional[Dict]:
    """
    Fetches and parses data for a single game.
    Returns a dictionary with game metadata and team results.
    """
    try:
        # Ensure we've visited the schedule page first to avoid CAPTCHA
        ensure_schedule_visited()

        game_url = GAME_PAGE_URL_TEMPLATE.format(game_id)
        page = session.get(game_url)
        page.raise_for_status()
        sleep(2)  # Small delay after request to avoid rate limiting

        soup = BeautifulSoup(page.content, 'html.parser')

        # Parse game metadata
        game_heading = soup.find("div", class_="game-heading-info")
        game_attrs = game_heading.find_all("h1") if game_heading else []

        # Parse date and time
        game_date, game_time = parse_date_from_game_page(soup, game_id)

        # Parse venue
        venue = None
        info_columns = soup.find_all('div', class_='game-info-column')
        for col in info_columns:
            grey_elem = col.find('div', class_='text text-grey')
            if grey_elem and ('ул' in grey_elem.text or 'Ереван' in grey_elem.text):
                venue_elem = col.find('div', class_='text')
                if venue_elem:
                    venue = venue_elem.text.strip().replace(' Yerevan', '')
                break

        # Parse category
        category_elem = soup.find("div", class_="game-tag")
        category = category_elem.get_text(strip=True) if category_elem else "Классическая игра"

        # Parse game name and number
        game_name = ""
        game_number = ""
        if game_attrs:
            if len(game_attrs) > 0:
                match = re.findall(r".+(?=\sY)", game_attrs[0].get_text(strip=True))
                if match:
                    game_name = match[0]
                else:
                    game_name = game_attrs[0].get_text(strip=True).replace(' YEREVAN', '')
            if len(game_attrs) > 1:
                game_number = game_attrs[1].get_text(strip=True)[1:]

        # Parse results table
        table_tag = soup.find("table")
        if not table_tag:
            logger.warning(f"No results table found for game {game_id}")
            return {
                'id': game_id,
                'date': game_date,
                'time': game_time,
                'venue': venue,
                'category': category,
                'game_name': game_name,
                'game_number': game_number,
                'teams': []
            }

        # Extract headers
        headers = []
        thead = table_tag.find("thead")
        if thead:
            header_row = thead.find("tr")
            headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
        else:
            first_tr = table_tag.find("tr")
            if first_tr:
                headers = [cell.get_text(strip=True) for cell in first_tr.find_all(["th", "td"])]

        # Find columns: team name (Название), rank (Место), and rounds (Раунд)
        team_name_idx = None
        rank_idx = None
        round_indices = []

        for i, header in enumerate(headers):
            header_lower = header.lower()
            if 'название' in header_lower or 'команда' in header_lower:
                team_name_idx = i
            elif 'место' in header_lower:
                rank_idx = i
            elif 'раунд' in header_lower or re.match(r'^\d+$', header):
                # Normalize round name to English format
                # Extract round number from header like "Раунд 1" or just "1"
                round_match = re.search(r'\d+', header)
                if round_match:
                    normalized_name = f"round {round_match.group()}"
                else:
                    normalized_name = header
                round_indices.append((i, normalized_name))

        # Extract data rows
        teams_data = []
        tbody = table_tag.find("tbody")
        rows = tbody.find_all("tr") if tbody else table_tag.find_all("tr")[1:]

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            team_name = cells[team_name_idx].get_text(strip=True).upper() if team_name_idx is not None else ""
            rank = cells[rank_idx].get_text(strip=True) if rank_idx is not None and rank_idx < len(cells) else None

            # Parse rank as integer
            try:
                rank = int(rank) if rank and rank.isdigit() else None
            except:
                rank = None

            # Extract round scores
            rounds = {}
            total_score = 0.0
            for idx, round_name in round_indices:
                if idx < len(cells):
                    score_text = cells[idx].get_text(strip=True)
                    try:
                        score = float(score_text.replace(',', '.')) if score_text else 0.0
                        rounds[round_name] = score
                        total_score += score
                    except ValueError:
                        rounds[round_name] = 0.0

            if team_name:
                teams_data.append({
                    'name': team_name,
                    'rank': rank,
                    'total_score': total_score,
                    'rounds': rounds
                })

        return {
            'id': game_id,
            'date': game_date,
            'time': game_time,
            'venue': venue,
            'category': category,
            'game_name': game_name,
            'game_number': game_number,
            'teams': teams_data
        }

    except Exception as e:
        logger.error(f"Failed to parse game {game_id}: {e}")
        return None


def get_or_create_team(cur, team_name: str) -> int:
    """
    Gets team_id for a team name, creating the team if it doesn't exist.
    """
    # Try to get existing team
    cur.execute("SELECT id FROM quizplease.teams WHERE name = %s", (team_name,))
    result = cur.fetchone()

    if result:
        return result[0]

    # Create new team
    cur.execute(
        "INSERT INTO quizplease.teams (name) VALUES (%s) RETURNING id",
        (team_name,)
    )
    return cur.fetchone()[0]


def save_game_to_db(game_data: Dict):
    """
    Saves game data to the database with proper transaction handling.
    All operations are atomic - either everything succeeds or nothing is saved.
    This prevents partial game data (game without teams) from being stored.
    """
    conn = None
    try:
        conn = get_db_connection()
        # Set autocommit to False to ensure explicit transaction control
        conn.autocommit = False

        with conn.cursor() as cur:
            # BEGIN transaction (explicit for clarity, though autocommit=False already does this)
            cur.execute("BEGIN")

            try:
                # Insert or update game
                cur.execute("""
                    INSERT INTO quizplease.games (id, game_date, game_time, venue, category, game_name, game_number)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        game_date = EXCLUDED.game_date,
                        game_time = EXCLUDED.game_time,
                        venue = EXCLUDED.venue,
                        category = EXCLUDED.category,
                        game_name = EXCLUDED.game_name,
                        game_number = EXCLUDED.game_number,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    game_data['id'],
                    game_data['date'],
                    game_data['time'],
                    game_data['venue'],
                    game_data['category'],
                    game_data['game_name'],
                    game_data['game_number']
                ))

                # Process each team
                for team in game_data['teams']:
                    # Get or create team
                    team_id = get_or_create_team(cur, team['name'])

                    # Insert or update participation
                    cur.execute("""
                        INSERT INTO quizplease.team_game_participations (game_id, team_id, rank, total_score)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (game_id, team_id) DO UPDATE SET
                            rank = EXCLUDED.rank,
                            total_score = EXCLUDED.total_score
                        RETURNING id
                    """, (
                        game_data['id'],
                        team_id,
                        team['rank'],
                        team['total_score']
                    ))
                    participation_id = cur.fetchone()[0]

                    # Insert round scores
                    for round_name, score in team['rounds'].items():
                        cur.execute("""
                            INSERT INTO quizplease.round_scores (participation_id, round_name, score)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (participation_id, round_name) DO UPDATE SET
                                score = EXCLUDED.score
                        """, (participation_id, round_name, score))

                # COMMIT transaction - all operations succeeded
                conn.commit()
                logger.info(f"Successfully saved game {game_data['id']} with {len(game_data['teams'])} teams")

            except Exception as e:
                # ROLLBACK transaction - revert all changes including the game row
                conn.rollback()
                logger.error(f"Failed to save game {game_data['id']}, rolling back transaction: {e}")
                raise

    except Exception as e:
        logger.error(f"Failed to establish database connection for game {game_data['id']}: {e}")
        raise
    finally:
        # Ensure connection is closed
        if conn:
            conn.close()


def lambda_handler(event, context):
    """
    Main Lambda handler function.
    """
    try:
        logger.info("Starting quiz game stats collection")

        # Get the last processed game ID
        last_game_id = get_last_processed_game_id()

        # Fetch new game IDs from the website
        new_game_ids = get_game_ids(last_game_id)
        logger.info(f"Found {len(new_game_ids)} new games on the website")

        # Also find games already in DB but without results (pre-created by another function)
        games_without_results = get_games_without_results()

        # Merge and deduplicate, keeping sorted order
        all_game_ids = sorted(set(new_game_ids + games_without_results))
        logger.info(f"Total games to process: {len(all_game_ids)} "
                     f"({len(new_game_ids)} new, {len(games_without_results)} without results)")

        if not all_game_ids:
            logger.info("No games to process")
            return {
                'statusCode': 200,
                'body': 'No new games to process'
            }

        # Process each game
        processed_count = 0
        failed_count = 0

        for game_id in all_game_ids:
            try:
                logger.info(f"Processing game {game_id}")
                game_data = parse_game_data(game_id)

                if game_data:
                    save_game_to_db(game_data)
                    processed_count += 1
                else:
                    failed_count += 1
                    logger.warning(f"Failed to parse game {game_id}")

            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing game {game_id}: {e}")
                # Continue with next game instead of failing completely

        logger.info(f"Completed: {processed_count} games processed, {failed_count} failed")

        return {
            'statusCode': 200,
            'body': f'Processed {processed_count} games, {failed_count} failed'
        }

    except Exception as e:
        logger.error(f"Lambda execution failed: {e}")
        raise


if __name__ == "__main__":
    # For local testing
    lambda_handler({}, {})
