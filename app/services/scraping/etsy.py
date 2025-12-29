"""
Etsy marketplace scraper using RapidAPI.
Extracts demand and supply signals from Etsy for digital products.

Uses two Etsy APIs in parallel to maximize data coverage:
1. etsy-api2.p.rapidapi.com
2. etsy-live-data.p.rapidapi.com

Both APIs are called simultaneously and results are merged, removing duplicates.
"""
import asyncio
import httpx
import logging
import re
import os
import sys
from datetime import date
from typing import List, Dict, Any, Optional
from app.services.scraping.base import BaseScraper
from app.models.marketplace_metrics import MarketplaceMetrics

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 10

# Configure logging to both file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraping.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# RapidAPI Configuration for Etsy
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

# API 1: Etsy API 2
API1_HOST = "etsy-api2.p.rapidapi.com"
API1_URL = "https://etsy-api2.p.rapidapi.com/product/search"

# API 2: Etsy Live Data (fallback)
API2_HOST = "etsy-live-data.p.rapidapi.com"
API2_URL = "https://etsy-live-data.p.rapidapi.com/search"

class EtsyScraper(BaseScraper):
    """
    Scraper for Etsy marketplace using RapidAPI.
    
    Demand signals: Review counts, ratings
    Supply signals: Number of listings, Discount rates
    Quality signals: Ratings, Bestseller ratio
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
        logger.info(f"{'='*60}")
        logger.info(f"Starting Etsy extraction for category: '{category}'")
        logger.info(f"Week start: {week_start}")

        # Check API Key
        if not RAPIDAPI_KEY:
            logger.error("RAPIDAPI_KEY environment variable is not set!")
            return metrics, raw_data
        else:
            masked_key = f"{RAPIDAPI_KEY[:8]}...{RAPIDAPI_KEY[-4:]}" if len(RAPIDAPI_KEY) > 12 else "***"
            logger.info(f"API Key configured: {masked_key}")

        try:
            # 1. Search for products in category (tries both APIs)
            logger.info(f"Searching Etsy for category: {category}")
            data = await self._search_products(category)
            if not data:
                logger.error(f"ERROR: No data received for category '{category}'")
                return metrics, raw_data

            # Log the actual data structure for debugging
            logger.info(f"SUCCESS: Received {len(data)} items from RapidAPI")
            if data:
                logger.info(f"First item keys: {list(data[0].keys())}")
                logger.info(f"First item sample: {str(data[0])[:500]}...")
            raw_data = data  # Store raw data for return

            # 2. Process Data
            metrics = self._process_data(data, category, week_start)
            logger.info(f"Successfully extracted {len(metrics)} metrics for '{category}'")
            logger.info(f"{'='*60}")

        except Exception as e:
            logger.error(f"ERROR scraping Etsy: {str(e)}", exc_info=True)
            logger.info(f"{'='*60}")

        return metrics, raw_data

    async def _search_products(self, category: str) -> List[Dict[str, Any]]:
        """
        Search for products using both Etsy APIs in parallel.

        Calls both APIs simultaneously and merges results to maximize data coverage.
        Duplicates are removed based on product ID.

        Returns list of product items with reviews, ratings, and prices.
        """
        logger.info(f"Calling both APIs in parallel for category: {category}")

        # Call both APIs in parallel
        results = await asyncio.gather(
            self._search_products_api1(category),
            self._search_products_api2(category),
            return_exceptions=True
        )

        api1_data = []
        api2_data = []

        # Process API 1 result
        if isinstance(results[0], Exception):
            logger.warning(f"API 1 failed with exception: {results[0]}")
        elif results[0]:
            api1_data = results[0]
            logger.info(f"API 1 returned {len(api1_data)} products")

        # Process API 2 result
        if isinstance(results[1], Exception):
            logger.warning(f"API 2 failed with exception: {results[1]}")
        elif results[1]:
            api2_data = results[1]
            logger.info(f"API 2 returned {len(api2_data)} products")

        # Merge results, removing duplicates by ID
        merged_data = self._merge_results(api1_data, api2_data)

        if not merged_data:
            logger.error("Both APIs failed to return data")
            return []

        logger.info(f"Total unique products after merging: {len(merged_data)}")
        return merged_data

    def _merge_results(self, api1_data: List[Dict[str, Any]], api2_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge results from both APIs, removing duplicates by product ID.

        Prioritizes API 1 data when duplicates exist, as it's the primary API.
        """
        seen_ids = set()
        merged = []

        # Add API 1 data first (higher priority)
        for item in api1_data:
            product_id = item.get("id")
            if product_id and product_id not in seen_ids:
                seen_ids.add(product_id)
                merged.append(item)

        # Add API 2 data that's not already in merged
        for item in api2_data:
            product_id = item.get("id")
            if product_id and product_id not in seen_ids:
                seen_ids.add(product_id)
                merged.append(item)

        return merged

    async def _search_products_api1(self, category: str) -> List[Dict[str, Any]]:
        """
        Search for products using Etsy API 2 (primary).
        Retries up to 3 times with 10 second delay on timeout.

        Returns list of product items with reviews, ratings, and prices.
        """
        url = API1_URL
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": API1_HOST,
        }
        params = {
            "query": category,
            "page": 1,
            "currency": "USD",
            "language": "en-US",
            "country": "US",
            "orderBy": "mostRelevant"
        }

        logger.info(f"API Request URL: {url}")
        logger.info(f"API Request params: {params}")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url, headers=headers, params=params)

                    logger.info(f"API Response status: {response.status_code}")

                    if response.status_code == 200:
                        try:
                            result = response.json()
                            logger.info(f"API Response type: {type(result)}")
                            logger.info(f"API Response keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")

                            # RapidAPI Etsy endpoint returns results in 'response' field
                            data = result.get("response", [])

                            if isinstance(data, list):
                                logger.info(f"SUCCESS: Retrieved {len(data)} products for category '{category}'")
                                return data
                            else:
                                logger.error(f"ERROR: Unexpected 'response' type: {type(data)}. Expected list.")
                                logger.error(f"Full API response: {result}")
                                return []
                        except Exception as json_err:
                            logger.error(f"ERROR: Failed to parse JSON response: {json_err}")
                            logger.error(f"Response text (first 500 chars): {response.text[:500]}")
                            return []
                    else:
                        logger.error(f"ERROR: API returned status {response.status_code}")
                        logger.error(f"Response body: {response.text[:500]}")
                        return []

            except httpx.TimeoutException:
                if attempt < MAX_RETRIES:
                    logger.warning(f"Timeout on attempt {attempt}/{MAX_RETRIES}. Retrying in {RETRY_DELAY_SECONDS} seconds...")
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    logger.error(f"ERROR: API request timed out after {MAX_RETRIES} attempts")
                    raise  # Re-raise the exception after final retry

            except httpx.HTTPStatusError as e:
                logger.error(f"ERROR: HTTP status error: {e}")
                return []
            except Exception as e:
                logger.error(f"ERROR: Unexpected error searching products: {str(e)}", exc_info=True)
                return []

        return []

    async def _search_products_api2(self, category: str) -> List[Dict[str, Any]]:
        """
        Search for products using Etsy Live Data API (fallback).
        Also retries up to 3 times with 10 second delay on timeout.

        NOTE: This API has a different response format.
        Once you provide the response model, we'll need to normalize it to match API 1's format.

        Returns list of product items normalized to match API 1 format.
        """
        url = API2_URL
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": API2_HOST,
        }
        params = {
            "query": category,
            "page": "1",
            "currency": "USD",
            "language": "en-US",
            "region": "US"
        }

        logger.info(f"API Request URL: {url}")
        logger.info(f"API Request params: {params}")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url, headers=headers, params=params)

                    logger.info(f"API Response status: {response.status_code}")

                    if response.status_code == 200:
                        try:
                            result = response.json()
                            logger.info(f"API Response type: {type(result)}")
                            logger.info(f"API Response keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")

                            # TODO: Normalize API 2 response to match API 1 format
                            # API 2 response structure is different - waiting for user to provide response model
                            # For now, return the raw data and we'll normalize in _normalize_api2_response
                            data = result.get("data", []) if isinstance(result, dict) else []

                            if isinstance(data, list):
                                logger.info(f"SUCCESS: Retrieved {len(data)} products from API 2")
                                # Normalize to API 1 format before returning
                                return self._normalize_api2_response(data)
                            else:
                                logger.error(f"ERROR: Unexpected response type: {type(data)}. Expected list.")
                                logger.error(f"Full API response: {result}")
                                return []

                        except Exception as json_err:
                            logger.error(f"ERROR: Failed to parse JSON response: {json_err}")
                            logger.error(f"Response text (first 500 chars): {response.text[:500]}")
                            return []
                    else:
                        logger.error(f"ERROR: API returned status {response.status_code}")
                        logger.error(f"Response body: {response.text[:500]}")
                        return []

            except httpx.TimeoutException:
                if attempt < MAX_RETRIES:
                    logger.warning(f"API 2 Timeout on attempt {attempt}/{MAX_RETRIES}. Retrying in {RETRY_DELAY_SECONDS} seconds...")
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    logger.error(f"ERROR: API 2 request timed out after {MAX_RETRIES} attempts")
                    return []

            except httpx.HTTPStatusError as e:
                logger.error(f"ERROR: API 2 HTTP status error: {e}")
                return []
            except Exception as e:
                logger.error(f"ERROR: API 2 Unexpected error: {str(e)}", exc_info=True)
                return []

        return []

    def _normalize_api2_response(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize API 2 response to match API 1 format.

        API 2 format:
        {
            "id": "1840696953",
            "title": "...",
            "seller": "...",
            "image_url": "...",
            "badge": "Bestseller",
            "rating": "4.9",
            "num_ratings": "890",
            "original_price": "$20.90",
            "discount_price": "$6.27",
            "discount_percent": "70% off",
            ...
        }

        API 1 format (target):
        {
            "id": "...",
            "title": "...",
            "price": {"salePrice": "...", "originalPrice": "...", "discount": "..."},
            "rating": "4.8",
            "reviews": "4.8 star rating with 2.6k reviews",
            "bestseller": false,
            "shopId": 12345,
            "shopName": "...",
            "imageUrl": "..."
        }
        """
        normalized = []

        for item in data:
            try:
                # Parse ratings count (e.g., "890", "3.3k" -> float)
                num_ratings_str = item.get("num_ratings", "0")
                num_ratings = 0
                if isinstance(num_ratings_str, str):
                    if 'k' in num_ratings_str.lower():
                        num_ratings = float(num_ratings_str.lower().replace('k', '')) * 1000
                    else:
                        num_ratings = float(num_ratings_str) if num_ratings_str else 0

                # Create reviews string in API 1 format
                rating_val = item.get("rating", "0")
                reviews_str = f"{rating_val} star rating with {num_ratings:.0f} reviews"

                # Determine if bestseller
                is_bestseller = item.get("badge") == "Bestseller"

                # Build price object
                price_obj = {
                    "salePrice": item.get("discount_price", item.get("original_price", "0")).replace("$", ""),
                    "originalPrice": item.get("original_price", "0").replace("$", ""),
                    "discount": item.get("discount_percent", "").replace(" off", "")
                }

                # Normalize item to API 1 format
                normalized_item = {
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "price": price_obj,
                    "rating": item.get("rating", "0"),
                    "reviews": reviews_str,
                    "bestseller": is_bestseller,
                    "shopId": item.get("seller", ""),  # API 2 uses seller name instead of ID
                    "shopName": item.get("seller", ""),
                    "imageUrl": item.get("image_url", "")
                }

                normalized.append(normalized_item)

            except Exception as e:
                logger.warning(f"Failed to normalize item {item.get('id', 'unknown')}: {e}")

        logger.info(f"Normalized {len(normalized)} items from API 2 to API 1 format")
        return normalized

    def _process_data(self, data: List[Dict[str, Any]], category: str, week_start: date) -> List[MarketplaceMetrics]:
        """
        Calculate metrics from RapidAPI response.

        Demand signals:
        - reviews: Parsed from review string (e.g., "4.8 star rating with 12k reviews")
        - rating: Product rating

        Supply signals:
        - Number of listings returned
        - Average price (market saturation indicator)
        - Average discount (high discounts = high supply pressure)

        Quality signals:
        - Average rating
        - Bestseller ratio (high ratio = strong competitors)
        """
        metrics = []

        if not data:
            logger.warning(f"No data to process for category '{category}'")
            return metrics

        try:
            # Debug: Log available fields in first item
            if data:
                first_item = data[0]
                logger.info(f"Available fields in RapidAPI response: {list(first_item.keys())}")
                logger.info(f"First item sample: {str(first_item)[:500]}...")

            # --- 1. Extract Basic Data Points ---

            # Reviews & Ratings
            total_reviews = 0
            ratings = []
            for item in data:
                # Reviews
                reviews_str = item.get("reviews", "")
                if isinstance(reviews_str, str):
                    match = re.search(r'(\d+(?:\.\d+)?)[kK]?\s*reviews', reviews_str)
                    if match:
                        review_count = float(match.group(1))
                        if 'k' in reviews_str.lower():
                            review_count *= 1000
                        total_reviews += review_count

                # Rating
                rating_str = item.get("rating", "")
                if rating_str:
                    try:
                        ratings.append(float(rating_str))
                    except (ValueError, TypeError):
                        pass

            avg_rating = sum(ratings) / len(ratings) if ratings else 0.0

            # Prices & Discounts
            prices = []
            discounts = []
            for item in data:
                price_obj = item.get("price", {})
                # Price
                if isinstance(price_obj, dict):
                    price_str = price_obj.get("salePrice", "0")
                    discount_str = price_obj.get("discount", "")
                else:
                    price_str = str(price_obj)
                    discount_str = ""

                try:
                    prices.append(float(price_str))
                except (ValueError, TypeError):
                    prices.append(0.0)

                # Discount (e.g., "25%")
                if discount_str and "%" in discount_str:
                    try:
                        discount_val = float(discount_str.replace("%", "").strip())
                        discounts.append(discount_val)
                    except ValueError:
                        pass
                else:
                    discounts.append(0.0)

            avg_price = sum(prices) / len(prices) if prices else 0.0
            avg_discount = sum(discounts) / len(discounts) if discounts else 0.0

            # Bestsellers
            bestseller_count = sum(1 for item in data if item.get("bestseller") is True)
            item_count = len(data)
            bestseller_ratio = bestseller_count / item_count if item_count > 0 else 0.0

            logger.info(f"METRICS - Items: {item_count}, Avg Rating: {avg_rating:.2f}, "
                        f"Total Reviews: {total_reviews:.0f}, Avg Price: ${avg_price:.2f}, "
                        f"Avg Discount: {avg_discount:.1f}%, Bestsellers: {bestseller_count}")

            # --- 2. Construct Metrics ---
            # Store granular metrics with descriptive metric names for detailed statistics
            # Use format "metric_type.detail" for additional statistics

            # Demand Metrics
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="demand",
                raw_value=float(total_reviews),
                normalized_value=0.0,
                week_start=week_start
            ))
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="demand.avg_reviews_per_product",
                raw_value=float(total_reviews / item_count) if item_count > 0 else 0.0,
                normalized_value=0.0,
                week_start=week_start
            ))

            # Supply Metrics
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="supply",
                raw_value=float(item_count),
                normalized_value=0.0,
                week_start=week_start
            ))
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="supply.bestseller_count",
                raw_value=float(bestseller_count),
                normalized_value=0.0,
                week_start=week_start
            ))
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="supply.bestseller_ratio",
                raw_value=float(bestseller_ratio),
                normalized_value=0.0,
                week_start=week_start
            ))

            # Quality Metrics
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="quality",
                raw_value=float(avg_rating),
                normalized_value=0.0,
                week_start=week_start
            ))
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="quality.min_rating",
                raw_value=float(min(ratings)) if ratings else 0.0,
                normalized_value=0.0,
                week_start=week_start
            ))
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="quality.max_rating",
                raw_value=float(max(ratings)) if ratings else 0.0,
                normalized_value=0.0,
                week_start=week_start
            ))

            # Price Metrics
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="price",
                raw_value=float(avg_price),
                normalized_value=0.0,
                week_start=week_start
            ))
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="price.min",
                raw_value=float(min(prices)) if prices else 0.0,
                normalized_value=0.0,
                week_start=week_start
            ))
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="price.max",
                raw_value=float(max(prices)) if prices else 0.0,
                normalized_value=0.0,
                week_start=week_start
            ))

            # Discount Metrics
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="discount.avg_percent",
                raw_value=float(avg_discount),
                normalized_value=0.0,
                week_start=week_start
            ))
            products_with_discount = sum(1 for d in discounts if d > 0)
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="discount.products_with_discount",
                raw_value=float(products_with_discount),
                normalized_value=0.0,
                week_start=week_start
            ))

        except Exception as e:
            logger.error(f"ERROR processing Etsy data: {str(e)}", exc_info=True)

        return metrics
