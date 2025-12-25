"""
SQLModel for marketplace_metrics table.
Stores normalized weekly signals from marketplaces.
"""
from datetime import date, datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class MetricType(str, Enum):
    DEMAND = "demand"
    SUPPLY = "supply"
    QUALITY = "quality"
    PRICE = "price"


class MarketplaceMetrics(SQLModel, table=True):
    """
    Stores raw and normalized metrics for demand/supply signals.
    Each record represents a single metric observation for a category+platform+week.
    """
    __tablename__ = "marketplace_metrics"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str = Field(index=True)  # etsy, gumroad, whop, reddit
    category: str = Field(index=True)
    metric_type: MetricType = Field(index=True)
    raw_value: float
    normalized_value: float = Field(ge=0.0, le=1.0)  # Must be between 0 and 1
    week_start: date = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "platform": "etsy",
                "category": "digital planners",
                "metric_type": "demand",
                "raw_value": 15000.0,
                "normalized_value": 0.75,
                "week_start": "2025-12-23"
            }
        }
