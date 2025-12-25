"""
Reddit demand signal scraper using Bright Data API.
Extracts demand signals from Reddit discussions and searches.
"""
import asyncio
import httpx
import logging
import os
from datetime import date
from typing import List, Dict, Any, Optional
from app.services.scraping.base import BaseScraper
from app.models.marketplace_metrics import MarketplaceMetrics

# Configure logging
logging.basicConfig(filename='scraping.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Bright Data Configuration for Reddit
BRIGHTDATA_API_TOKEN = os.getenv("BRIGHTDATA_API_TOKEN", "your_brightdata_token_here")
REDDIT_DATASET_ID = os.getenv("REDDIT_DATASET_ID", "gd_ltppk0jdv1jqz25mz")


class RedditScraper(BaseScraper):
    """
    Scraper for Reddit demand signals using Bright Data API.
    
    Demand signals: post frequency, upvote counts, comment engagement
    Supply signals: Not typically available on Reddit (defaults to low values)
    
    Why: Reddit is primarily a demand indicator. People asking for or
    discussing digital products indicates market interest.
    """
    
    @property
    def platform_name(self) -> str:
        return "reddit"
    
    async def extract_metrics(self, category: str, week_start: date) -> tuple[List[MarketplaceMetrics], List[Dict[str, Any]]]:
        """
        Extract Reddit demand metrics using Bright Data API.
        
        Process:
        1. Trigger data collection with search query
        2. Poll progress API until ready
        3. Download snapshot data
        4. Process and aggregate engagement metrics
        
        Returns:
            Tuple of (metrics list, raw data from Bright Data)
        """
        metrics = []
        raw_data = []
        logging.info(f"Starting Reddit extraction for category: {category}")
        
        try:
            # 1. Trigger Data Collection
            snapshot_id = await self._trigger_collection(category)
            if not snapshot_id:
                logging.error(f"Failed to trigger collection for {category}")
                return metrics, raw_data
            
            logging.info(f"Collection triggered. Snapshot ID: {snapshot_id}")
            
            # 2. Wait for completion
            logging.info(f"Waiting for Brightdata to complete data collection...")
            is_ready = await self._wait_for_completion(snapshot_id)
            if not is_ready:
                logging.error(f"Data collection timed out or failed for {snapshot_id}")
                return metrics, raw_data
            
            # 3. Download Snapshot
            logging.info(f"Downloading snapshot data for {snapshot_id}")
            data = await self._get_snapshot(snapshot_id)
            if not data:
                logging.error(f"No data received for snapshot {snapshot_id}")
                return metrics, raw_data
            
            # Log the actual data structure for debugging
            logging.info(f"Received {len(data)} posts from Brightdata")
            if data:
                logging.info(f"First post structure: {data[0] if data else 'empty'}")
                logging.info(f"Data keys in first post: {list(data[0].keys()) if data else []}")
            raw_data = data  # Store raw data for return
            
            # 4. Process Data
            metrics = self._process_data(data, category, week_start)
            logging.info(f"Successfully extracted {len(metrics)} metrics for {category}")
            
        except Exception as e:
            logging.error(f"Error scraping Reddit with Bright Data: {str(e)}", exc_info=True)
            
        return metrics, raw_data

    async def _trigger_collection(self, search_query: str) -> Optional[str]:
        """
        Trigger Brightdata collection for a search query.
        
        Returns snapshot_id for tracking the collection progress.
        
        Request format:
        - keyword: Search term (required)
        - date: Time range filter (e.g., "All time", "Past year", "Past month")
        - sort_by: Sort order (e.g., "Hot", "Top", "New")
        - num_of_posts: Number of posts to collect (optional)
        """
        url = "https://api.brightdata.com/datasets/v3/trigger"
        headers = {
            "Authorization": f"Bearer {BRIGHTDATA_API_TOKEN}",
            "Content-Type": "application/json",
        }
        params = {
            "dataset_id": REDDIT_DATASET_ID,
            "include_errors": "true",
            "type": "discover_new",
            "discover_by": "keyword",
        }
        data = [{
            "keyword": search_query,
            "date": "All time",
            "sort_by": "Hot"
        }]
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, params=params, json=data)
                
                if response.status_code == 200:
                    result = response.json()
                    snapshot_id = result.get("snapshot_id")
                    logging.info(f"Successfully triggered collection for query '{search_query}' - Snapshot ID: {snapshot_id}")
                    return snapshot_id
                else:
                    logging.error(f"Failed to trigger collection. Status: {response.status_code}, Response: {response.text}")
                    return None
        except Exception as e:
            logging.error(f"Error triggering collection for query '{search_query}': {str(e)}", exc_info=True)
            return None

    async def _wait_for_completion(self, snapshot_id: str, timeout: int = 360) -> bool:
        """Poll the progress API until ready. Timeout set to 360 seconds (6 minutes) for Brightdata."""
        url = f"https://api.brightdata.com/datasets/v3/progress/{snapshot_id}"
        headers = {
            "Authorization": f"Bearer {BRIGHTDATA_API_TOKEN}",
        }
        
        start_time = asyncio.get_event_loop().time()
        poll_interval = 10  # Poll every 10 seconds
        
        async with httpx.AsyncClient() as client:
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                try:
                    response = await client.get(url, headers=headers)
                    if response.status_code != 200:
                        logging.warning(f"Progress API returned {response.status_code}: {response.text}")
                        await asyncio.sleep(poll_interval)
                        continue
                    
                    status = response.json().get("status")
                    logging.info(f"Snapshot {snapshot_id} status: {status}")
                    
                    if status == "ready":
                        logging.info(f"Data collection ready for snapshot {snapshot_id}")
                        return True
                    elif status == "failed":
                        logging.error(f"Data collection failed for snapshot {snapshot_id}")
                        return False
                    
                    await asyncio.sleep(poll_interval)
                except Exception as e:
                    logging.error(f"Error polling progress: {str(e)}")
                    await asyncio.sleep(poll_interval)
                
        logging.error(f"Data collection timed out after {timeout} seconds for snapshot {snapshot_id}")
        return False

    async def _get_snapshot(self, snapshot_id: str) -> List[Dict[str, Any]]:
        """
        Download the collected snapshot data from Brightdata.
        
        Returns list of Reddit posts with full details.
        """
        url = f"https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}"
        headers = {
            "Authorization": f"Bearer {BRIGHTDATA_API_TOKEN}",
        }
        params = {"format": "json"}
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        logging.info(f"Successfully downloaded snapshot {snapshot_id} with {len(data)} posts")
                        return data
                    else:
                        logging.error(f"Unexpected response format for snapshot {snapshot_id}: {type(data)}")
                        return []
                else:
                    logging.error(f"Failed to download snapshot {snapshot_id}. Status: {response.status_code}, Response: {response.text}")
                    return []
        except Exception as e:
            logging.error(f"Error downloading snapshot {snapshot_id}: {str(e)}", exc_info=True)
            return []

    def _process_data(self, data: List[Dict[str, Any]], category: str, week_start: date) -> List[MarketplaceMetrics]:
        """
        Calculate metrics from Bright Data Reddit API response.
        
        Demand signals:
        - num_upvotes: Post upvotes (popularity indicator)
        - num_comments: Comment count (engagement indicator)
        - post frequency: Number of posts about the topic
        
        Supply signals:
        - Low baseline since Reddit is not a marketplace
        """
        metrics = []
        
        if not data:
            logging.warning(f"No data to process for category {category}")
            return metrics
        
        try:
            # Debug: Log available fields in first item
            if data:
                first_post = data[0]
                logging.info(f"Available fields in Brightdata Reddit response: {list(first_post.keys())}")
                logging.info(f"First post sample: {first_post}")
            
            # Demand Metrics - Aggregate engagement signals
            total_upvotes = sum(post.get("num_upvotes", 0) or 0 for post in data)
            total_comments = sum(post.get("num_comments", 0) or 0 for post in data)
            post_count = len(data)
            avg_upvotes = total_upvotes / post_count if post_count > 0 else 0
            avg_comments = total_comments / post_count if post_count > 0 else 0
            
            logging.info(f"Processed Reddit data - Posts: {post_count}, Total Upvotes: {total_upvotes}, "
                        f"Total Comments: {total_comments}, Avg Upvotes: {avg_upvotes:.2f}, Avg Comments: {avg_comments:.2f}")
            
            # Demand Metric: Total engagement (upvotes + comments weighted)
            # Upvotes weighted at 1x, comments weighted at 2x (more valuable signal)
            total_engagement = total_upvotes + (total_comments * 2)
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="demand",
                raw_value=float(total_engagement),
                normalized_value=0.0,
                week_start=week_start
            ))
            
            # Supply Metric: Low baseline since Reddit is not a marketplace
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="supply",
                raw_value=50.0,  # Low baseline since Reddit is not a marketplace
                normalized_value=0.0,
                week_start=week_start
            ))
            
            # Additional signal: Post frequency (volume indicator)
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="volume",
                raw_value=float(post_count),
                normalized_value=0.0,
                week_start=week_start
            ))
            
            # Additional signal: Average engagement per post
            metrics.append(MarketplaceMetrics(
                platform=self.platform_name,
                category=category,
                metric_type="engagement",
                raw_value=float(avg_upvotes + (avg_comments * 2)),
                normalized_value=0.0,
                week_start=week_start
            ))
            
        except Exception as e:
            logging.error(f"Error processing Reddit data: {str(e)}", exc_info=True)
            
        return metrics
