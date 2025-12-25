"""
Celery background tasks for long-running operations.
Handles scraping and computation tasks asynchronously.
"""
import asyncio
import logging
from datetime import date
from app.celery_app import celery_app
from app.database import SessionLocal
from app.services.scraping.etsy import EtsyScraper
from app.services.scraping.gumroad import GumroadScraper
from app.services.scraping.whop import WhopScraper
from app.services.scraping.reddit import RedditScraper
from app.services.normalization import normalize_all_metrics_for_week
from app.services.scoring import compute_all_gap_scores_for_week

# Configure logging
logging.basicConfig(filename='tasks.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


@celery_app.task(bind=True, name="scrape_platform_task")
def scrape_platform_task(self, platform: str, category: str, week_start: str):
    """
    Background task to scrape a platform.
    Runs asynchronously without blocking FastAPI.
    
    Args:
        platform: Platform identifier (etsy, gumroad, whop, reddit)
        category: Product category to scrape
        week_start: Week start date as string (YYYY-MM-DD)
        
    Returns:
        Dictionary with task status and metrics count
    """
    scrapers = {
        "etsy": EtsyScraper,
        "gumroad": GumroadScraper,
        "whop": WhopScraper,
        "reddit": RedditScraper
    }
    
    if platform not in scrapers:
        raise ValueError(f"Invalid platform: {platform}")
    
    try:
        logging.info(f"Starting background scrape task for {platform}/{category}")
        
        # Parse date
        week_start_date = date.fromisoformat(week_start)
        
        # Get database session
        session = SessionLocal()
        
        try:
            # Initialize scraper and execute
            scraper_class = scrapers[platform]
            scraper = scraper_class(session)
            
            # Update task state
            self.update_state(state='PROGRESS', meta={'status': 'scraping', 'platform': platform})
            
            # Execute scraping using asyncio
            metrics_count, raw_data = asyncio.run(scraper.scrape_and_store(
                category=category,
                week_start=week_start_date
            ))
            
            logging.info(f"Successfully scraped {platform}/{category}: {metrics_count} metrics")
            
            # Create a summary of the raw data for the API response
            data_summary = None
            if raw_data:
                first_item = raw_data[0] if raw_data else None
                data_summary = {
                    "item_count": len(raw_data),
                    "fields": list(first_item.keys()) if first_item else [],
                    "sample_item": first_item
                }
            
            return {
                "status": "success",
                "platform": platform,
                "category": category,
                "metrics_collected": metrics_count,
                "raw_data": raw_data,
                "data_summary": data_summary
            }
        finally:
            session.close()
            
    except Exception as e:
        logging.error(f"Error in scrape task for {platform}/{category}: {str(e)}", exc_info=True)
        raise


@celery_app.task(bind=True, name="compute_pipeline_task")
def compute_pipeline_task(self, week_start: str):
    """
    Background task to compute the full pipeline.
    Runs asynchronously without blocking FastAPI.
    
    Args:
        week_start: Week start date as string (YYYY-MM-DD)
        
    Returns:
        Dictionary with computation results
    """
    try:
        logging.info(f"Starting background compute task for week {week_start}")
        
        # Parse date
        week_start_date = date.fromisoformat(week_start)
        
        # Get database session
        session = SessionLocal()
        
        try:
            # Step 1: Normalize metrics
            self.update_state(state='PROGRESS', meta={'status': 'normalizing'})
            normalized_count = normalize_all_metrics_for_week(session, week_start_date)
            logging.info(f"Normalized {normalized_count} metrics")
            
            # Step 2: Compute gap scores
            self.update_state(state='PROGRESS', meta={'status': 'computing_scores'})
            computed_count = compute_all_gap_scores_for_week(session, week_start_date)
            logging.info(f"Computed {computed_count} gap scores")
            
            return {
                "status": "success",
                "week_start": week_start,
                "normalized_metrics": normalized_count,
                "computed_gap_scores": computed_count
            }
        finally:
            session.close()
            
    except Exception as e:
        logging.error(f"Error in compute task for week {week_start}: {str(e)}", exc_info=True)
        raise
