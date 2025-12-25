"""
Base scraper interface for marketplace data collection.
Defines the contract all platform scrapers must implement.
"""
from abc import ABC, abstractmethod
from datetime import date
from typing import List, Dict, Any
from sqlmodel import Session
from app.models.marketplace_metrics import MarketplaceMetrics


class BaseScraper(ABC):
    """
    Abstract base class for platform scrapers.
    
    Each platform scraper must implement extract_metrics to collect
    raw demand and supply signals from their respective marketplace.
    """
    
    def __init__(self, session: Session):
        """
        Initialize scraper with database session.
        
        Args:
            session: Database session for storing metrics
        """
        self.session = session
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (etsy, gumroad, whop, reddit)."""
        pass
    
    @abstractmethod
    async def extract_metrics(self, category: str, week_start: date) -> List[MarketplaceMetrics]:
        """
        Extract raw metrics for a given category and week.
        
        Must return a list of MarketplaceMetrics objects with:
        - platform: set to self.platform_name
        - category: provided category
        - metric_type: either 'demand' or 'supply'
        - raw_value: numeric signal extracted from marketplace
        - normalized_value: initially set to 0.0 (will be computed later)
        - week_start: provided week_start
        
        Args:
            category: Product category to scrape
            week_start: Week identifier for this data
            
        Returns:
            List of MarketplaceMetrics objects
            
        Why: This interface ensures all scrapers produce consistent data
        that can be normalized and scored uniformly.
        """
        pass
    
    async def scrape_and_store(self, category: str, week_start: date) -> tuple[int, List[Dict[str, Any]]]:
        """
        Execute scraping and store results in database.
        
        Args:
            category: Product category to scrape
            week_start: Week identifier
            
        Returns:
            Tuple of (number of metrics collected, raw data from platform)
            
        Why: This method provides a standard entrypoint for all scrapers,
        handling the full collection and storage pipeline.
        """
        metrics, raw_data = await self.extract_metrics(category, week_start)
        
        for metric in metrics:
            self.session.add(metric)
        
        self.session.commit()
        return len(metrics), raw_data
