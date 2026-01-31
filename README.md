# Quiz Please Game Stats Collector

Automated system for collecting quiz game results from [Quiz Please Yerevan](https://yerevan.quizplease.ru) and storing them in PostgreSQL for analytics.

## Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  EventBridge     │────▶│  Lambda Function │────▶│   PostgreSQL     │
│  (Daily Schedule)│     │  (Web Scraper)   │     │   (Database)     │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

## Features

- **Automated Collection**: Daily Lambda function checks for new games
- **Incremental Loading**: Only processes new games since last run
- **Historical Import**: Supports importing from CSV backup files
- **Transaction Safety**: Atomic operations ensure data integrity

## Database Schema

All tables are in the `quizplease` schema:

| Table | Description |
|-------|-------------|
| `games` | Game metadata (id, date, venue, category, etc.) |
| `teams` | Unique team names |
| `team_game_participations` | Team rankings and scores per game |
| `round_scores` | Individual round scores per participation |

## Project Structure

```
├── src/
│   ├── lambda_function.py    # Main Lambda handler
│   └── requirements.txt      # Python dependencies
├── sql/
│   └── 001_create_tables.sql # Database schema
├── terraform/                # Infrastructure as Code
├── build.sh                  # Build Lambda package
├── deploy.sh                 # Deploy to AWS
├── init_db.sh               # Initialize database
├── test_local.py            # Local testing
├── delete_game.py           # Delete a game by ID
└── import_csv_backup.py     # Import from CSV backup
```

## Setup

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env with your database credentials
source .env
```

### 2. Initialize Database

```bash
./init_db.sh
```

### 3. Deploy Lambda

```bash
./build.sh
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your settings
terraform init
terraform apply
```

## Local Testing

```bash
source .env

# Test database connection
python test_local.py connection

# Test parsing a specific game
python test_local.py game 121358

# Test web scraping
python test_local.py parsing

# Run full Lambda locally
python test_local.py full
```

## Utility Scripts

### Delete a game
```bash
python delete_game.py 121358 --dry-run  # Preview
python delete_game.py 121358            # Delete with confirmation
```

### Import from CSV backup
```bash
python import_csv_backup.py --dry-run   # Preview
python import_csv_backup.py             # Import
```

## Updating the Lambda

```bash
# 1. Edit src/lambda_function.py
# 2. Build and deploy
./build.sh
cd terraform && terraform apply
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | PostgreSQL port (default: 5432) |
| `DB_NAME` | Database name |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |
