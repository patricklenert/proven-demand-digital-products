"""
Gumroad marketplace scraper.
Extracts demand and supply signals from Gumroad for digital products.
"""
import logging
import re
import sys
from datetime import date
from typing import List, Dict, Any
from crawl4ai import AsyncWebCrawler
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy, LLMExtractionStrategy
import json
from app.services.scraping.base import BaseScraper
from app.models.marketplace_metrics import MarketplaceMetrics

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


class GumroadScraper(BaseScraper):
    """
    Scraper for Gumroad marketplace.

    Demand signals: product rating counts, average ratings
    Supply signals: active product count in search results
    Quality signals: average rating
    Price signals: average, min, max prices
    """

    @property
    def platform_name(self) -> str:
        return "gumroad"

    async def extract_metrics(self, category: str, week_start: date) -> tuple[List[MarketplaceMetrics], List[Dict[str, Any]]]:
        """
        Extract Gumroad metrics using Crawl4AI.

        Process:
        1. Search for products in category using Crawl4AI
        2. Extract product data (ratings, rating counts, prices)
        3. Process and normalize metrics

        Returns:
            Tuple of (metrics list, raw data from platform)
        """
        metrics = []
        raw_data = []
        logger.info(f"{'='*60}")
        logger.info(f"Starting Gumroad extraction for category: '{category}'")
        logger.info(f"Week start: {week_start}")

        try:
            # 1. Search for products in category
            logger.info(f"Searching Gumroad for category: {category}")
            products = await self._search_products(category)
            if not products:
                logger.error(f"ERROR: No data received for category '{category}'")
                return metrics, raw_data

            logger.info(f"SUCCESS: Received {len(products)} items from Gumroad")
            if products:
                logger.info(f"First item keys: {list(products[0].keys())}")
                logger.info(f"First item sample: {str(products[0])[:500]}...")
            raw_data = products  # Store raw data for return

            # 2. Process Data
            metrics = self._process_data(products, category, week_start)
            logger.info(f"Successfully extracted {len(metrics)} metrics for '{category}'")
            logger.info(f"{'='*60}")

        except Exception as e:
            logger.error(f"ERROR scraping Gumroad: {str(e)}", exc_info=True)
            logger.info(f"{'='*60}")

        return metrics, raw_data

    async def _search_products(self, category: str) -> List[Dict[str, Any]]:
        """
        Search for products using Crawl4AI with CSS Extraction Strategy.

        Uses JsonCssExtractionStrategy to directly extract structured product data
        from Gumroad's DOM using CSS selectors.

        Implements multi-step scraping to click "Load more" button multiple times
        to collect more than the initial 36 products.

        Returns list of product items with ratings, rating counts, and prices.
        """
        logger.info(f"[DEBUG] Crawling Gumroad discover page for category: {category}")

        # URL encode the category for safe URL usage
        encoded_category = category.replace(" ", "+")
        discover_url = f"https://gumroad.com/discover?query={encoded_category}&sort=curated"
        logger.info(f"[DEBUG] Crawling URL: {discover_url}")

        # Define CSS extraction schema for Gumroad products
        # Based on actual HTML structure:
        # - Articles: <article class="relative flex flex-col...">
        # - Title: <h2 itemprop="name"> or <h4 itemprop="name">
        # - Rating: <span class="rating-average">
        # - Rating Count: <span title="*ratings">(1.6K)</span>
        # - Price: <div itemprop="price">

        schema = {
            "name": "Gumroad Products",
            "baseSelector": "article",
            "fields": [
                {
                    "name": "title",
                    "selector": "h2[itemprop='name'], h4[itemprop='name']",
                    "type": "text",
                    "transform": "strip"
                },
                {
                    "name": "rating",
                    "selector": ".rating-average",
                    "type": "text",
                    "transform": "strip"
                },
                {
                    "name": "rating_count_raw",
                    "selector": "span[title*='ratings']",
                    "type": "text",
                    "transform": "strip"
                },
                {
                    "name": "price",
                    "selector": "div[itemprop='price']",
                    "type": "text",
                    "transform": "strip"
                }
            ]
        }

        extraction_strategy = JsonCssExtractionStrategy(schema)

        # JavaScript code to find and click the "Load more" button
        load_more_js = """
        const buttons = Array.from(document.querySelectorAll('button, a, div[role="button"], [class*="button"]'));
        const loadMoreBtn = buttons.find(btn => btn.textContent.trim() === 'Load more');
        if (loadMoreBtn) {
            loadMoreBtn.click();
            true;
        } else {
            false;
        }
        """

        session_id = f"gumroad_{category.replace(' ', '_')}"
        all_products = []
        max_clicks = 10  # Konfigurierbar: 10 Klicks für ~400 Produkte

        try:
            async with AsyncWebCrawler(verbose=True, headless=True) as crawler:
                logger.info(f"[DEBUG] Starting crawler with session: {session_id}")

                # Step 1: Load initial page
                logger.info(f"[DEBUG] Step 1: Loading initial page...")
                result = await crawler.arun(
                    url=discover_url,
                    word_count_threshold=10,
                    bypass_cache=True,
                    extraction_strategy=extraction_strategy,
                    wait_for="css:article",
                    session_id=session_id,
                    page_timeout=60000,
                )

                logger.info(f"[DEBUG] Initial crawl completed. Success: {result.success}")

                if result.success and result.extracted_content:
                    try:
                        extracted_data = json.loads(result.extracted_content)
                        all_products = self._process_extracted_data(extracted_data, category)
                        logger.info(f"[DEBUG] Initial load: {len(all_products)} products")
                    except json.JSONDecodeError as e:
                        logger.error(f"[ERROR] Failed to parse extracted JSON: {e}")
                        return self._parse_html_fallback(result.html, category)
                else:
                    logger.warning(f"[WARNING] No extracted content from initial load")
                    return self._parse_html_fallback(result.html, category)

                # Step 2: Click "Load more" multiple times
                for i in range(max_clicks):
                    logger.info(f"[DEBUG] Step 2.{i+1}: Clicking 'Load more'...")

                    result = await crawler.arun(
                        url=discover_url,
                        word_count_threshold=10,
                        bypass_cache=True,
                        extraction_strategy=extraction_strategy,
                        js_code=[
                            "window.scrollTo(0, document.body.scrollHeight);",
                            "await new Promise(r => setTimeout(r, 1000));",
                            load_more_js,
                            "await new Promise(r => setTimeout(r, 2000));"
                        ],
                        wait_for="css:article",
                        session_id=session_id,
                        js_only=True,  # WICHTIG: Keine neue Navigation
                        page_timeout=60000,
                    )

                    if result.success and result.extracted_content:
                        try:
                            extracted_data = json.loads(result.extracted_content)
                            new_products = self._process_extracted_data(extracted_data, category)
                            logger.info(f"[DEBUG] Click {i+1}: Got {len(new_products)} products")
                            all_products.extend(new_products)
                        except json.JSONDecodeError as e:
                            logger.error(f"[ERROR] Failed to parse JSON on click {i+1}: {e}")
                            continue
                    else:
                        logger.warning(f"[DEBUG] Click {i+1}: No new products or button disabled, stopping")
                        break  # Stop if button no longer works

                # Remove duplicates
                seen_titles = set()
                unique_products = []
                for product in all_products:
                    if product["title"] not in seen_titles:
                        seen_titles.add(product["title"])
                        unique_products.append(product)

                logger.info(f"[DEBUG] Total unique products: {len(unique_products)}")
                return unique_products

        except Exception as e:
            logger.error(f"[ERROR] Exception during crawling: {str(e)}", exc_info=True)
            return []

    def _process_extracted_data(self, extracted_data: Dict, category: str) -> List[Dict[str, Any]]:
        """
        Process the extracted data from CssExtractionStrategy into product format.

        Args:
            extracted_data: JSON data from CSS extraction
            category: Product category

        Returns:
            List of product dictionaries
        """
        products = []

        # The extracted data typically comes as a list of items
        if isinstance(extracted_data, list):
            items = extracted_data
        elif isinstance(extracted_data, dict) and 'list' in extracted_data:
            items = extracted_data['list']
        else:
            items = []

        logger.info(f"[DEBUG] Processing {len(items)} extracted items")

        for item in items:
            try:
                title = item.get('title', '').strip()
                rating_str = item.get('rating', '0').strip()
                rating_count_raw = item.get('rating_count_raw', '').strip()
                price_str = item.get('price', '$0').strip()

                if not title or len(title) <= 3:
                    continue

                # Parse rating
                try:
                    rating = float(rating_str)
                except (ValueError, TypeError):
                    rating = 0.0

                # Parse rating count from format "(1.6K)" or "(643)"
                rating_count = 0
                match = re.search(r'\(([\d.]+[kK]?)\)', rating_count_raw)
                if match:
                    rating_count = self._parse_rating_count(match.group(1))

                # Parse price from "$0+" or "$29.99"
                price = 0.0
                match = re.search(r'\$(\d+\.?\d*)', price_str)
                if match:
                    price = float(match.group(1))

                products.append({
                    "title": title,
                    "rating": rating,
                    "rating_count": rating_count,
                    "price": price
                })

            except Exception as e:
                logger.warning(f"[WARNING] Failed to process item: {e}")

        # Remove duplicates based on title
        seen_titles = set()
        unique_products = []
        for product in products:
            if product["title"] not in seen_titles:
                seen_titles.add(product["title"])
                unique_products.append(product)

        logger.info(f"[DEBUG] Processed {len(unique_products)} unique products")

        return unique_products

    def _parse_html_fallback(self, html: str, category: str) -> List[Dict[str, Any]]:
        """
        Fallback method to parse HTML using regex if CSS extraction fails.

        This is a simple fallback that tries to extract products using regex patterns.
        """
        logger.info(f"[DEBUG] Using regex fallback parsing...")
        products = []

        # Rating patterns
        rating_patterns = [
            re.compile(r'(\d+\.?\d*)\s*\(\s*([\d.]+[kK]?)\s*\)'),
            re.compile(r'(\d+\.?\d*)\s*\(([\d,]+[kK]?)\)'),
        ]

        # Price pattern
        price_pattern = re.compile(r'\$(\d+\.?\d*)')

        # Find all price matches
        price_matches = list(price_pattern.finditer(html))
        logger.info(f"[DEBUG] Found {len(price_matches)} price matches in HTML")

        for price_match in price_matches[:50]:
            price = float(price_match.group(1))

            # Get window around price
            start = max(0, price_match.start() - 1000)
            end = min(len(html), price_match.end() + 500)
            window = html[start:end]

            # Try to find rating
            rating = 0.0
            rating_count = 0
            for rating_pattern in rating_patterns:
                rating_match = rating_pattern.search(window)
                if rating_match:
                    rating = float(rating_match.group(1))
                    rating_count_str = rating_match.group(2) if len(rating_match.groups()) >= 2 else "0"
                    rating_count = self._parse_rating_count(rating_count_str)
                    break

            # Try to find title
            text_window = re.sub(r'<[^>]+>', ' ', window)
            words = text_window.strip().split()
            skip_words = ['add', 'cart', 'buy', 'now', 'free', 'get', 'click', 'rating', 'usd']

            if words:
                title = ' '.join(words[:5])
                title = re.sub(r'\s+', ' ', title).strip()
                if len(title) > 3 and not any(word in title.lower() for word in skip_words):
                    products.append({
                        "title": title,
                        "rating": rating,
                        "rating_count": rating_count,
                        "price": price
                    })

        # Remove duplicates
        seen = set()
        unique = []
        for p in products:
            key = (p["title"], p["price"])
            if key not in seen:
                seen.add(key)
                unique.append(p)

        logger.info(f"[DEBUG] Fallback parsed {len(unique)} unique products")
        return unique

    def _parse_rating_count(self, rating_count_str: str) -> int:
        """
        Parse rating count string to integer.

        Examples:
        - "1.7K" -> 1700
        - "2" -> 2
        - "500" -> 500
        - "1,700" -> 1700

        Args:
            rating_count_str: Rating count string from Gumroad

        Returns:
            Integer rating count
        """
        if not rating_count_str:
            return 0

        rating_count_str = rating_count_str.strip().upper()

        # Remove commas
        rating_count_str = rating_count_str.replace(',', '')

        # Handle K suffix (thousands)
        if 'K' in rating_count_str:
            num_str = rating_count_str.replace('K', '').replace(' ', '')
            try:
                return int(float(num_str) * 1000)
            except (ValueError, TypeError):
                return 0

        # Handle plain numbers
        try:
            return int(rating_count_str)
        except (ValueError, TypeError):
            return 0

    def _process_data(self, products: List[Dict[str, Any]], category: str, week_start: date) -> List[MarketplaceMetrics]:
        """
        Calculate metrics from scraped product data.

        Demand signals:
        - rating_count: Total number of ratings across all products
        - avg_rating: Average product rating

        Supply signals:
        - Number of products returned

        Quality signals:
        - Average rating
        - Min/max ratings

        Price signals:
        - Average price
        - Min/max prices
        """
        metrics = []

        if not products:
            logger.warning(f"[WARNING] No data to process for category '{category}'")
            return metrics

        try:
            # Debug: Log available fields in first item
            first_product = products[0]
            logger.info(f"[DEBUG] Available fields in product response: {list(first_product.keys())}")
            logger.info(f"[DEBUG] First product sample: {str(first_product)[:500]}...")

            # --- 1. Extract Basic Data Points ---

            # Ratings & Rating Counts
            total_rating_count = 0
            ratings = []
            for product in products:
                # Rating count
                rating_count = product.get("rating_count", 0)
                if isinstance(rating_count, (int, float)):
                    total_rating_count += int(rating_count)
                elif isinstance(rating_count, str):
                    total_rating_count += self._parse_rating_count(rating_count)

                # Rating
                rating = product.get("rating", 0.0)
                if isinstance(rating, (int, float)) and rating > 0:
                    ratings.append(float(rating))

            avg_rating = sum(ratings) / len(ratings) if ratings else 0.0

            # Prices
            prices = []
            for product in products:
                price = product.get("price", 0.0)
                if isinstance(price, str):
                    price_match = re.search(r'(\d+\.?\d*)', price.replace(',', ''))
                    if price_match:
                        prices.append(float(price_match.group(1)))
                elif isinstance(price, (int, float)) and price > 0:
                    prices.append(float(price))

            avg_price = sum(prices) / len(prices) if prices else 0.0

            product_count = len(products)

            logger.info(f"[METRICS] Products: {product_count}, Avg Rating: {avg_rating:.2f}, "
                        f"Total Ratings: {total_rating_count:.0f}, Avg Price: ${avg_price:.2f}")

            # --- 2. Construct Metrics ---

            # Demand Metrics
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="demand",
                raw_value=float(total_rating_count),
                normalized_value=0.0,
                week_start=week_start
            ))
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="demand.avg_ratings_per_product",
                raw_value=float(total_rating_count / product_count) if product_count > 0 else 0.0,
                normalized_value=0.0,
                week_start=week_start
            ))

            # Supply Metrics
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="supply",
                raw_value=float(product_count),
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

        except Exception as e:
            logger.error(f"[ERROR] Error processing Gumroad data: {str(e)}", exc_info=True)

        return metrics
