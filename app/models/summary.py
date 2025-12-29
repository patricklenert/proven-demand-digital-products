"""
Summary models for report generation.
"""
from typing import List, Optional
from pydantic import BaseModel


class ProductStatistics(BaseModel):
    """Detailed product statistics from raw marketplace data."""
    total_products: int = 0
    bestseller_count: int = 0
    bestseller_ratio: float = 0.0

    # Price statistics (in actual currency, e.g., USD)
    avg_price: float = 0.0
    min_price: float = 0.0
    max_price: float = 0.0

    # Rating statistics
    avg_rating: float = 0.0
    min_rating: float = 0.0
    max_rating: float = 0.0

    # Review statistics
    total_reviews: int = 0
    avg_reviews_per_product: float = 0.0

    # Discount statistics
    avg_discount_percent: float = 0.0
    products_with_discount: int = 0


class SummaryOpportunity(BaseModel):
    """Opportunity item for summary."""
    category: str
    platform: str
    gap_score: float
    verdict: str

    # Normalized scores (0-1) for quick comparison
    avg_demand_score: float = 0.0
    avg_supply_score: float = 0.0
    avg_quality_score: float = 0.0
    avg_price_score: float = 0.0

    # Real statistics from raw marketplace data
    stats: ProductStatistics

    # Human-readable insight
    insight: str = ""


class SummaryResponse(BaseModel):
    """Response model for summary endpoint."""
    week_start: str
    top_opportunities: List[SummaryOpportunity]
    saturated_categories: List[SummaryOpportunity]
    market_movement_notes: str

    class Config:
        json_schema_extra = {
            "example": {
                "week_start": "2025-12-29",
                "top_opportunities": [
                    {
                        "category": "wedding planner notion",
                        "platform": "etsy",
                        "gap_score": 0.72,
                        "verdict": "high_opportunity",
                        "avg_demand_score": 0.85,
                        "avg_supply_score": 0.20,
                        "avg_quality_score": 0.75,
                        "avg_price_score": 0.60,
                        "stats": {
                            "total_products": 64,
                            "bestseller_count": 3,
                            "bestseller_ratio": 0.047,
                            "avg_price": 15.47,
                            "min_price": 0.99,
                            "max_price": 49.36,
                            "avg_rating": 4.8,
                            "min_rating": 4.4,
                            "max_rating": 5.0,
                            "total_reviews": 52431,
                            "avg_reviews_per_product": 819,
                            "avg_discount_percent": 35.5,
                            "products_with_discount": 48
                        },
                        "insight": "High demand meets low competition. Average rating of 4.8 indicates quality products. Price range $0.99-$49.36 shows diverse market positioning."
                    }
                ],
                "saturated_categories": [],
                "market_movement_notes": ""
            }
        }
