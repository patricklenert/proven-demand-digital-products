"""
SQLModel for gap_scores table.
Stores computed weekly gap scores and verdicts.
"""
from datetime import date, datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class VerdictType(str, Enum):
    HIGH_OPPORTUNITY = "high_opportunity"
    COMPETITIVE = "competitive"
    SATURATED = "saturated"


class GapScore(SQLModel, table=True):
    """
    Stores computed gap scores for each category+platform+week combination.
    Gap score represents how much demand exceeds supply (0-1 range).
    """
    __tablename__ = "gap_scores"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    category: str = Field(index=True)
    platform: str = Field(index=True)
    gap_score: float = Field(ge=0.0, le=1.0)  # Must be between 0 and 1
    verdict: VerdictType = Field(index=True)
    week_start: date = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "category": "digital planners",
                "platform": "etsy",
                "gap_score": 0.72,
                "verdict": "high_opportunity",
                "week_start": "2025-12-23"
            }
        }
