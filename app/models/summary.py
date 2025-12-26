"""
Summary models for report generation.
"""
from typing import List
from pydantic import BaseModel


class SummaryOpportunity(BaseModel):
    """Opportunity item for summary."""
    category: str
    platform: str
    gap_score: float
    verdict: str
    avg_demand: float = 0.0
    avg_supply: float = 0.0
    avg_quality: float = 0.0
    avg_price: float = 0.0
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
                "week_start": "2025-12-23",
                "top_opportunities": [
                    {
                        "category": "digital planners",
                        "platform": "etsy",
                        "gap_score": 0.72,
                        "verdict": "high_opportunity",
                        "avg_demand": 0.85,
                        "avg_supply": 0.20,
                        "avg_quality": 0.75,
                        "avg_price": 0.60,
                        "insight": "Gap: 0.72 | D:0.85 S:0.20 Q:0.75 P:0.60"
                    }
                ],
                "saturated_categories": [
                    {
                        "category": "stock photos",
                        "platform": "gumroad",
                        "gap_score": 0.15,
                        "verdict": "saturated",
                        "avg_demand": 0.30,
                        "avg_supply": 0.90,
                        "avg_quality": 0.65,
                        "avg_price": 0.80,
                        "insight": "Gap: 0.15 | D:0.30 S:0.90 Q:0.65 P:0.80"
                    }
                ],
                "market_movement_notes": ""
            }
        }
