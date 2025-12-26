"""
Summary API endpoint.
Returns comprehensive weekly summary for report generation.
"""
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from app.database import get_session
from app.models.gap_scores import GapScore
from app.models.marketplace_metrics import MarketplaceMetrics, MetricType
from app.models.summary import SummaryResponse, SummaryOpportunity
from app.services.notion import NotionService
from sqlmodel import select


router = APIRouter(tags=["reports"])


def get_current_week_start() -> date:
    """Get the start date of the current week (Monday)."""
    today = date.today()
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)
    return week_start


def get_metric_avg(session: Session, category: str, platform: str, week_start: date, metric_type: MetricType) -> float:
    """Get average normalized value for a specific metric."""
    stmt = select(MarketplaceMetrics.normalized_value).where(
        MarketplaceMetrics.category == category,
        MarketplaceMetrics.platform == platform,
        MarketplaceMetrics.week_start == week_start,
        MarketplaceMetrics.metric_type == metric_type
    )
    result = session.exec(stmt).first()
    return result or 0.0


@router.get("/summary", response_model=SummaryResponse)
async def get_summary(
    week_start: Optional[date] = Query(None, description="Week start date (defaults to current week)"),
    session: Session = Depends(get_session)
) -> SummaryResponse:
    """
    Get comprehensive weekly summary for report generation.
    
    Returns:
    - Top 5 high-opportunity categories (highest gap scores)
    - Top 5 saturated categories (lowest gap scores)
    - Market movement notes (placeholder for future enhancement)
    
    Args:
        week_start: Week identifier (defaults to current week)
        session: Database session
        
    Returns:
        Complete weekly summary suitable for Notion/email reports
        
    Why: This endpoint provides a ready-to-use summary for weekly reports,
    highlighting both opportunities and markets to avoid.
    """
    # Use current week if not specified
    if week_start is None:
        week_start = get_current_week_start()
    
    # Get top 5 opportunities (highest gap scores)
    top_statement = select(GapScore).where(
        GapScore.week_start == week_start
    ).order_by(
        GapScore.gap_score.desc()
    ).limit(5)
    
    top_results = session.exec(top_statement).all()
    top_opportunities = []
    for result in top_results:
        avg_demand = get_metric_avg(session, result.category, result.platform, week_start, MetricType.DEMAND)
        avg_supply = get_metric_avg(session, result.category, result.platform, week_start, MetricType.SUPPLY)
        avg_quality = get_metric_avg(session, result.category, result.platform, week_start, MetricType.QUALITY)
        avg_price = get_metric_avg(session, result.category, result.platform, week_start, MetricType.PRICE)
        insight = f"Gap: {result.gap_score:.2f} | D:{avg_demand:.2f} S:{avg_supply:.2f} Q:{avg_quality:.2f} P:{avg_price:.2f}"
        top_opportunities.append(
            SummaryOpportunity(
                category=result.category,
                platform=result.platform,
                gap_score=result.gap_score,
                verdict=result.verdict.value if hasattr(result.verdict, 'value') else result.verdict,
                avg_demand=avg_demand,
                avg_supply=avg_supply,
                avg_quality=avg_quality,
                avg_price=avg_price,
                insight=insight
            )
        )
    
    # Get top 5 saturated categories (lowest gap scores)
    saturated_statement = select(GapScore).where(
        GapScore.week_start == week_start
    ).order_by(
        GapScore.gap_score.asc()
    ).limit(5)
    
    saturated_results = session.exec(saturated_statement).all()
    saturated_categories = []
    for result in saturated_results:
        avg_demand = get_metric_avg(session, result.category, result.platform, week_start, MetricType.DEMAND)
        avg_supply = get_metric_avg(session, result.category, result.platform, week_start, MetricType.SUPPLY)
        avg_quality = get_metric_avg(session, result.category, result.platform, week_start, MetricType.QUALITY)
        avg_price = get_metric_avg(session, result.category, result.platform, week_start, MetricType.PRICE)
        insight = f"Gap: {result.gap_score:.2f} | D:{avg_demand:.2f} S:{avg_supply:.2f} Q:{avg_quality:.2f} P:{avg_price:.2f}"
        saturated_categories.append(
            SummaryOpportunity(
                category=result.category,
                platform=result.platform,
                gap_score=result.gap_score,
                verdict=result.verdict.value if hasattr(result.verdict, 'value') else result.verdict,
                avg_demand=avg_demand,
                avg_supply=avg_supply,
                avg_quality=avg_quality,
                avg_price=avg_price,
                insight=insight
            )
        )
    
    return SummaryResponse(
        week_start=str(week_start),
        top_opportunities=top_opportunities,
        saturated_categories=saturated_categories,
        market_movement_notes=""  # Placeholder for future enhancement
    )


@router.post("/summary/publish")
async def publish_summary(
    week_start: Optional[date] = Query(None, description="Week start date (defaults to current week)"),
    session: Session = Depends(get_session)
):
    """
    Generate and publish the weekly summary to Notion.
    """
    # 1. Get the summary data
    summary_data = await get_summary(week_start, session)
    
    # 2. Initialize Notion Service
    notion_service = NotionService()
    
    # 3. Create the report
    page_url = await notion_service.create_weekly_report(summary_data)
    
    return {"message": "Report published successfully", "url": page_url}
