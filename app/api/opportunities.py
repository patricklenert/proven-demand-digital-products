"""
Opportunities API endpoint.
Returns top opportunities for weekly report generation.
"""
from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, select
from app.database import get_session
from app.models.gap_scores import GapScore


router = APIRouter(tags=["reports"])


class OpportunityItem(BaseModel):
    """Individual opportunity item."""
    category: str
    platform: str
    gap_score: float
    verdict: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "category": "digital planners",
                "platform": "etsy",
                "gap_score": 0.72,
                "verdict": "high_opportunity"
            }
        }


class OpportunitiesResponse(BaseModel):
    """Response model for opportunities endpoint."""
    week_start: str
    opportunities: List[OpportunityItem]


def get_current_week_start() -> date:
    """
    Get the start date of the current week (Monday).
    
    Returns:
        Date of the Monday of the current week
    """
    today = date.today()
    # Calculate days since Monday (0 = Monday, 6 = Sunday)
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)
    return week_start


@router.get("/opportunities", response_model=OpportunitiesResponse)
async def get_opportunities(
    week_start: Optional[date] = Query(None, description="Week start date (defaults to current week)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of opportunities to return"),
    session: Session = Depends(get_session)
) -> OpportunitiesResponse:
    """
    Get top opportunities for a given week.
    
    Returns opportunities sorted by gap_score (descending).
    Default behavior returns current week's opportunities.
    
    Args:
        week_start: Week identifier (defaults to current week)
        limit: Maximum number of results
        session: Database session
        
    Returns:
        Week date and list of opportunities
        
    Why: This endpoint provides the core data for weekly opportunity reports.
    High gap scores indicate categories with proven demand and low competition.
    """
    # Use current week if not specified
    if week_start is None:
        week_start = get_current_week_start()
    
    # Query gap scores for the week, ordered by gap_score descending
    statement = select(GapScore).where(
        GapScore.week_start == week_start
    ).order_by(
        GapScore.gap_score.desc()
    ).limit(limit)
    
    results = session.exec(statement).all()
    
    # Convert to response model
    opportunities = [
        OpportunityItem(
            category=result.category,
            platform=result.platform,
            gap_score=result.gap_score,
            verdict=result.verdict
        )
        for result in results
    ]
    
    return OpportunitiesResponse(
        week_start=str(week_start),
        opportunities=opportunities
    )
