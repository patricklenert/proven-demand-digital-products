"""
Etsy marketplace scraper using RapidAPI.
Extracts demand and supply signals from Etsy for digital products.
"""
import asyncio
import httpx
import logging
import re
import os
from datetime import date
from typing import List, Dict, Any, Optional
from app.services.scraping.base import BaseScraper
from app.models.marketplace_metrics import MarketplaceMetrics

# Configure logging
logging.basicConfig(filename='scraping.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# RapidAPI Configuration for Etsy
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = "etsy-api2.p.rapidapi.com"

class EtsyScraper(BaseScraper):
    """
    Scraper for Etsy marketplace using RapidAPI.
    
    Demand signals: Review counts, ratings
    Supply signals: Number of listings
    """
    
    @property
    def platform_name(self) -> str:
        return "etsy"
    
    async def extract_metrics(self, category: str, week_start: date) -> tuple[List[MarketplaceMetrics], List[Dict[str, Any]]]:
        """
        Extract Etsy metrics using RapidAPI.
        
        Process:
        1. Search for products in category using RapidAPI
        2. Collect product data (reviews, ratings, prices)
        3. Process and normalize metrics
        
        Returns:
            Tuple of (metrics list, raw data from RapidAPI)
        """
        metrics = []
        raw_data = []
        logging.info(f"Starting Etsy extraction for category: {category}")
        
        try:
            # 1. Search for products in category
            logging.info(f"Searching Etsy for category: {category}")
            data = await self._search_products(category)
            if not data:
                logging.error(f"No data received for category {category}")
                return metrics, raw_data
            
            # Log the actual data structure for debugging
            logging.info(f"Received {len(data)} items from RapidAPI")
            if data:
                logging.info(f"First item structure: {data[0] if data else 'empty'}")
                logging.info(f"Data keys in first item: {list(data[0].keys()) if data else []}")
            raw_data = data  # Store raw data for return
            
            # 2. Process Data
            metrics = self._process_data(data, category, week_start)
            logging.info(f"Successfully extracted {len(metrics)} metrics for {category}")
            
        except Exception as e:
            logging.error(f"Error scraping Etsy with RapidAPI: {str(e)}", exc_info=True)
            
        return metrics, raw_data

    async def _search_products(self, category: str) -> List[Dict[str, Any]]:
        """
        Search for products in a category using RapidAPI.
        
        Returns list of product items with reviews, ratings, and prices.
        """
        url = "https://etsy-api2.p.rapidapi.com/product/search"
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "etsy-api2.p.rapidapi.com",
        }
        params = {
            "query": category,
            "page": 1,
            "currency": "USD",
            "language": "en-US",
            "country": "US",
            "orderBy": "mostRelevant"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    result = response.json()
                    # RapidAPI Etsy endpoint returns results in 'response' field
                    data = result.get("response", [])
                    if isinstance(data, list):
                        logging.info(f"Successfully retrieved {len(data)} products for category '{category}'")
                        return data
                    else:
                        logging.error(f"Unexpected response format for category '{category}': {type(data)}")
                        return []
                else:
                    logging.error(f"Failed to search products. Status: {response.status_code}, Response: {response.text}")
                    return []
        except Exception as e:
            logging.error(f"Error searching products for category '{category}': {str(e)}", exc_info=True)
            return []

    def _process_data(self, data: List[Dict[str, Any]], category: str, week_start: date) -> List[MarketplaceMetrics]:
        """
        Calculate metrics from RapidAPI response.
        
        Demand signals:
        - reviews: Parsed from review string (e.g., "4.8 star rating with 12k reviews")
        - rating: Product rating
        
        Supply signals:
        - Number of listings returned
        - Average price (market saturation indicator)
        """
        metrics = []
        
        if not data:
            logging.warning(f"No data to process for category {category}")
            return metrics
        
        try:
            # Debug: Log available fields in first item
            if data:
                first_item = data[0]
                logging.info(f"Available fields in RapidAPI response: {list(first_item.keys())}")
                logging.info(f"First item sample: {first_item}")
            
            # Demand Metrics - Parse reviews from string format
            total_reviews = 0
            for item in data:
                reviews_str = item.get("reviews", "")
                if isinstance(reviews_str, str):
                    # Extract number from strings like "4.8 star rating with 12k reviews"
                    match = re.search(r'(\d+(?:\.\d+)?)[kK]?\s*reviews', reviews_str)
                    if match:
                        review_count = float(match.group(1))
                        # Handle 'k' suffix (e.g., "12k" = 12000)
                        if 'k' in reviews_str.lower():
                            review_count *= 1000
                        total_reviews += review_count
            
            # Parse rating - convert string to float
            avg_rating = 0.0
            rating_count = 0
            for item in data:
                rating_str = item.get("rating", "")
                if rating_str:
                    try:
                        rating_val = float(rating_str)
                        avg_rating += rating_val
                        rating_count += 1
                    except (ValueError, TypeError):
                        pass
            avg_rating = avg_rating / rating_count if rating_count > 0 else 0.0
            
            # Supply Metrics
            item_count = len(data)
            # Handle price field - nested in 'price' object with 'salePrice' field
            prices = []
            for item in data:
                price_obj = item.get("price", {})
                if isinstance(price_obj, dict):
                    price_str = price_obj.get("salePrice", "0")
                else:
                    price_str = str(price_obj)
                try:
                    price = float(price_str)
                    prices.append(price)
                except (ValueError, TypeError):
                    prices.append(0.0)
            avg_price = sum(prices) / len(prices) if prices else 0.0
            
            logging.info(f"Processed data - Items: {item_count}, Avg Rating: {avg_rating:.2f}, "
                        f"Total Reviews: {total_reviews:.0f}, Avg Price: ${avg_price:.2f}")
            
            # Demand Metric: Item Reviews (primary demand signal)
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="demand",
                raw_value=float(total_reviews),
                normalized_value=0.0,
                week_start=week_start
            ))
            
            # Supply Metric: Number of listings
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="supply",
                raw_value=float(item_count),
                normalized_value=0.0,
                week_start=week_start
            ))
            
            # Additional signal: Average rating (quality indicator)
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="quality",
                raw_value=float(avg_rating),
                normalized_value=0.0,
                week_start=week_start
            ))
            
            # Additional signal: Average price (market saturation)
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="price",
                raw_value=float(avg_price),
                normalized_value=0.0,
                week_start=week_start
            ))
            
        except Exception as e:
            logging.error(f"Error processing Etsy data: {str(e)}", exc_info=True)
            
        return metrics
