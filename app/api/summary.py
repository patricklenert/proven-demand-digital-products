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
from app.models.marketplace_metrics import MarketplaceMetrics
from app.models.summary import SummaryResponse, SummaryOpportunity, ProductStatistics
from app.services.notion import NotionService
from sqlmodel import select


router = APIRouter(tags=["reports"])


def get_current_week_start() -> date:
    """Get the start date of the current week (Monday)."""
    today = date.today()
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)
    return week_start


def get_raw_metric_value(session: Session, category: str, platform: str, week_start: date, metric_type: str) -> Optional[float]:
    """Get raw value for a specific metric type."""
    stmt = select(MarketplaceMetrics.raw_value).where(
        MarketplaceMetrics.category == category,
        MarketplaceMetrics.platform == platform,
        MarketplaceMetrics.week_start == week_start,
        MarketplaceMetrics.metric_type == metric_type
    )
    result = session.exec(stmt).first()
    return result


def get_normalized_metric_value(session: Session, category: str, platform: str, week_start: date, metric_type: str) -> float:
    """Get normalized value for a core metric type."""
    stmt = select(MarketplaceMetrics.normalized_value).where(
        MarketplaceMetrics.category == category,
        MarketplaceMetrics.platform == platform,
        MarketplaceMetrics.week_start == week_start,
        MarketplaceMetrics.metric_type == metric_type
    )
    result = session.exec(stmt).first()
    return result or 0.0


def build_product_statistics(session: Session, category: str, platform: str, week_start: date) -> ProductStatistics:
    """
    Build detailed product statistics from raw marketplace metrics.

    Fetches granular metrics like:
    - Total products (supply)
    - Bestseller count and ratio
    - Price statistics (avg, min, max)
    - Rating statistics (avg, min, max)
    - Review statistics (total, avg per product)
    - Discount statistics (avg percent, products with discount)
    """
    stats = ProductStatistics()

    # Total products
    total_products = get_raw_metric_value(session, category, platform, week_start, "supply")
    if total_products is not None:
        stats.total_products = int(total_products)

    # Bestseller metrics
    bestseller_count = get_raw_metric_value(session, category, platform, week_start, "supply.bestseller_count")
    if bestseller_count is not None:
        stats.bestseller_count = int(bestseller_count)

    bestseller_ratio = get_raw_metric_value(session, category, platform, week_start, "supply.bestseller_ratio")
    if bestseller_ratio is not None:
        stats.bestseller_ratio = float(bestseller_ratio)

    # Price metrics
    avg_price = get_raw_metric_value(session, category, platform, week_start, "price")
    if avg_price is not None:
        stats.avg_price = round(float(avg_price), 2)

    min_price = get_raw_metric_value(session, category, platform, week_start, "price.min")
    if min_price is not None:
        stats.min_price = round(float(min_price), 2)

    max_price = get_raw_metric_value(session, category, platform, week_start, "price.max")
    if max_price is not None:
        stats.max_price = round(float(max_price), 2)

    # Rating metrics
    avg_rating = get_raw_metric_value(session, category, platform, week_start, "quality")
    if avg_rating is not None:
        stats.avg_rating = round(float(avg_rating), 2)

    min_rating = get_raw_metric_value(session, category, platform, week_start, "quality.min_rating")
    if min_rating is not None:
        stats.min_rating = round(float(min_rating), 2)

    max_rating = get_raw_metric_value(session, category, platform, week_start, "quality.max_rating")
    if max_rating is not None:
        stats.max_rating = round(float(max_rating), 2)

    # Review metrics
    total_reviews = get_raw_metric_value(session, category, platform, week_start, "demand")
    if total_reviews is not None:
        stats.total_reviews = int(total_reviews)

    avg_reviews = get_raw_metric_value(session, category, platform, week_start, "demand.avg_reviews_per_product")
    if avg_reviews is not None:
        stats.avg_reviews_per_product = round(float(avg_reviews), 1)

    # Discount metrics
    avg_discount = get_raw_metric_value(session, category, platform, week_start, "discount.avg_percent")
    if avg_discount is not None:
        stats.avg_discount_percent = round(float(avg_discount), 1)

    products_with_discount = get_raw_metric_value(session, category, platform, week_start, "discount.products_with_discount")
    if products_with_discount is not None:
        stats.products_with_discount = int(products_with_discount)

    return stats


def generate_detailed_insight(stats: ProductStatistics) -> str:
    """
    Generate a detailed human-readable insight based on real market statistics.

    Uses actual values from the marketplace data to provide actionable insights.
    """
    # Core market dynamics
    if stats.avg_rating > 0.0 and stats.total_reviews > 0:
        if stats.avg_rating >= 4.8 and stats.total_reviews > 10000:
            core_msg = f"Strong demand with {stats.total_reviews:,} total reviews and excellent {stats.avg_rating} avg rating."
        elif stats.avg_rating >= 4.8:
            core_msg = f"High quality market with {stats.avg_rating} avg rating across {stats.total_products} products."
        elif stats.total_reviews > 5000:
            core_msg = f"High interest category with {stats.total_reviews:,} total reviews."
        else:
            core_msg = f"Active market with {stats.total_products} products and {stats.total_reviews:,} reviews."
    elif stats.total_products > 0:
        core_msg = f"{stats.total_products} products available in this category."
    else:
        core_msg = "Limited market data available."

    # Add price insights
    price_msg = ""
    if stats.avg_price > 0:
        if stats.min_price > 0 and stats.max_price > 0:
            price_range = f"${stats.min_price:.2f}-${stats.max_price:.2f}"
            price_msg = f" Price range {price_range}, avg ${stats.avg_price:.2f}."
        else:
            price_msg = f" Average price ${stats.avg_price:.2f}."

    # Add competition insights
    competition_msg = ""
    if stats.bestseller_count > 0:
        ratio_pct = stats.bestseller_ratio * 100
        competition_msg = f" {stats.bestseller_count} bestsellers ({ratio_pct:.1f}% of products)."

    # Add discount insights
    discount_msg = ""
    if stats.avg_discount_percent > 0:
        if stats.avg_discount_percent > 40:
            discount_msg = f" High discounting ({stats.avg_discount_percent:.0f}% avg) suggests competitive pressure."
        elif stats.avg_discount_percent > 20:
            discount_msg = f" Moderate discounting ({stats.avg_discount_percent:.0f}% avg)."
        else:
            discount_msg = f" Low discounting ({stats.avg_discount_percent:.0f}% avg) indicates stable pricing."

    # Combine all insights
    full_insight = f"{core_msg}{price_msg}{competition_msg}{discount_msg}"
    return full_insight


def build_opportunity_from_gap_score(session: Session, gap_score: GapScore) -> SummaryOpportunity:
    """
    Build a SummaryOpportunity from a GapScore using detailed market statistics.
    """
    stats = build_product_statistics(session, gap_score.category, gap_score.platform, gap_score.week_start)

    # Get normalized scores for quick comparison
    avg_demand_score = get_normalized_metric_value(session, gap_score.category, gap_score.platform, gap_score.week_start, "demand")
    avg_supply_score = get_normalized_metric_value(session, gap_score.category, gap_score.platform, gap_score.week_start, "supply")
    avg_quality_score = get_normalized_metric_value(session, gap_score.category, gap_score.platform, gap_score.week_start, "quality")
    avg_price_score = get_normalized_metric_value(session, gap_score.category, gap_score.platform, gap_score.week_start, "price")

    insight = generate_detailed_insight(stats)

    return SummaryOpportunity(
        category=gap_score.category,
        platform=gap_score.platform,
        gap_score=gap_score.gap_score,
        verdict=gap_score.verdict.value if hasattr(gap_score.verdict, 'value') else gap_score.verdict,
        avg_demand_score=avg_demand_score,
        avg_supply_score=avg_supply_score,
        avg_quality_score=avg_quality_score,
        avg_price_score=avg_price_score,
        stats=stats,
        insight=insight
    )


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
    - Detailed statistics for each category including:
      * Product counts and bestseller information
      * Price ranges (min, max, average)
      * Rating statistics
      * Review counts
      * Discount information

    Args:
        week_start: Week identifier (defaults to current week)
        session: Database session

    Returns:
        Complete weekly summary suitable for Notion/email reports
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
    top_opportunities = [
        build_opportunity_from_gap_score(session, result)
        for result in top_results
    ]

    # Get top 5 saturated categories (lowest gap scores)
    saturated_statement = select(GapScore).where(
        GapScore.week_start == week_start
    ).order_by(
        GapScore.gap_score.asc()
    ).limit(5)

    saturated_results = session.exec(saturated_statement).all()
    saturated_categories = [
        build_opportunity_from_gap_score(session, result)
        for result in saturated_results
    ]

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
