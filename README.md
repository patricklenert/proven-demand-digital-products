# Proven Demand Backend

Intelligence engine for computing **Supply vs Demand Gap Scores** across digital product marketplaces.

## Overview

Proven Demand is a research-driven product that identifies digital product categories with proven demand and low competition. It computes a **Gap Score** (0-1) representing how much demand exceeds supply for each category+platform combination.

### Key Features

- **Deterministic scoring**: Transparent, explainable gap score computation
- **Multi-platform support**: Etsy, Gumroad, Whop, and Reddit
- **Windmill.dev integration**: Designed for scheduled orchestration
- **Weekly reports**: Read-only API for Notion/email report generation

### Gap Score Formula

```
gap_score = (normalized_demand - normalized_supply + 1) / 2
```

**Verdicts:**
- `gap_score >= 0.6`: High opportunity (clear market gap)
- `0.3 <= gap_score < 0.6`: Competitive (balanced market)
- `gap_score < 0.3`: Saturated (supply exceeds demand)

## Architecture

```
app/
├── main.py                  # FastAPI application
├── config.py               # Configuration management
├── database.py             # Database connection
├── models/                 # SQLModel database models
│   ├── marketplace_metrics.py
│   └── gap_scores.py
├── services/              # Business logic
│   ├── normalization.py   # Deterministic normalization
│   ├── scoring.py         # Gap score computation
│   └── scraping/          # Platform scrapers
└── api/                   # API endpoints
    ├── windmill.py        # Windmill triggers
    ├── opportunities.py   # GET /opportunities
    └── summary.py         # GET /summary
```

## Marketplace Scrapers

### Etsy Scraper (RapidAPI)
Extracts demand and supply signals from Etsy marketplace.

**Demand signals:**
- Total product reviews (primary demand indicator)
- Average product rating (quality indicator)

**Supply signals:**
- Number of listings (market saturation)
- Average price (market saturation indicator)

**API:** [RapidAPI Etsy API](https://rapidapi.com/apidojo/api/etsy)
**Endpoint:** `https://etsy-api2.p.rapidapi.com/product/search`

### Reddit Scraper (Bright Data)
Extracts demand signals from Reddit discussions and searches.

**Demand signals:**
- Post upvotes (popularity indicator)
- Comment counts (engagement indicator)
- Post frequency (volume indicator)
- Weighted engagement (upvotes + 2x comments)

**Supply signals:**
- Low baseline (50.0) since Reddit is not a marketplace

**API:** [Bright Data Reddit Dataset](https://brightdata.com)
**Endpoints:**
- Trigger: `https://api.brightdata.com/datasets/v3/trigger`
- Progress: `https://api.brightdata.com/datasets/v3/progress/{snapshot_id}`
- Download: `https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}`

**Request format:**
```json
[{
  "keyword": "search_term",
  "date": "All time",
  "sort_by": "Hot"
}]
```

## Setup

### 1. Prerequisites

- Python 3.11 or newer
- PostgreSQL 12 or newer

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Copy `.env.example` to `.env` and update with your credentials:

```bash
cp .env.example .env
```

**Required environment variables:**
- Database: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`
- Notion: `NOTION_API_KEY`, `NOTION_PARENT_PAGE_ID`
- Etsy (RapidAPI): `RAPIDAPI_KEY`
- Reddit (Bright Data): `BRIGHTDATA_API_TOKEN`, `REDDIT_DATASET_ID` - Get from [Bright Data](https://brightdata.com)

### 4. Initialize Database

The application automatically creates tables on startup. Ensure PostgreSQL is running:

```bash
# Start PostgreSQL (if using Homebrew on macOS)
brew services start postgresql@14

# Create database
createdb proven_demand
```

### 5. Run Application

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

## API Endpoints

### Windmill Integration

**POST /windmill/scrape/{platform}**
Trigger scraping for a specific platform and category.

```bash
curl -X POST http://localhost:8000/scrape/etsy \
  -H "Content-Type: application/json" \
  -d '{"category": "digital planners", "week_start": "2025-12-23"}'
```

**POST /windmill/compute**
Trigger full computation pipeline for a week.

```bash
curl -X POST http://localhost:8000/compute \
  -H "Content-Type: application/json" \
  -d '{"week_start": "2025-12-23"}'
```

### Report Generation

**GET /opportunities**
Get top opportunities for weekly reports.

```bash
curl http://localhost:8000/opportunities?limit=20
```

**GET /summary**
Get comprehensive weekly summary.

```bash
curl http://localhost:8000/summary
```

### Health Check

**GET /** or **GET /health**
Check API status.

```bash
curl http://localhost:8000/health
```

## Database Schema

### marketplace_metrics
Stores raw and normalized metrics from marketplaces.

| Column | Type | Description |
|--------|------|-------------|
| id | int | Primary key |
| platform | str | etsy, gumroad, whop, reddit |
| category | str | Product category |
| metric_type | str | demand or supply |
| raw_value | float | Raw extracted value |
| normalized_value | float | Normalized score (0-1) |
| week_start | date | Week identifier |
| created_at | datetime | Creation timestamp |

### gap_scores
Stores computed weekly gap scores.

| Column | Type | Description |
|--------|------|-------------|
| id | int | Primary key |
| category | str | Product category |
| platform | str | Platform identifier |
| gap_score | float | Gap score (0-1) |
| verdict | str | high_opportunity, competitive, saturated |
| week_start | date | Week identifier |
| created_at | datetime | Creation timestamp |