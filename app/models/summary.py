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
                        "verdict": "high_opportunity"
                    }
                ],
                "saturated_categories": [
                    {
                        "category": "stock photos",
                        "platform": "gumroad",
                        "gap_score": 0.15,
                        "verdict": "saturated"
                    }
                ],
                "market_movement_notes": ""
            }
        }
