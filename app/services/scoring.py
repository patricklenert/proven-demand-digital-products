"""
Gap score computation service.
Computes Supply vs Demand Gap Scores and assigns verdicts.
"""
from datetime import date
from typing import Literal
from sqlmodel import Session, select, func
from app.models.marketplace_metrics import MarketplaceMetrics
from app.models.gap_scores import GapScore


# Configurable thresholds for verdict assignment
HIGH_OPPORTUNITY_THRESHOLD = 0.6
COMPETITIVE_THRESHOLD = 0.3


def compute_gap_score(demand_score: float, supply_score: float) -> float:
    """
    Pure function to compute gap score from demand and supply aggregates.
    
    Formula: gap_score = demand_score - supply_score (clamped to 0-1)
    
    Args:
        demand_score: Aggregated demand score (0-1)
        supply_score: Aggregated supply score (0-1)
        
    Returns:
        Gap score between 0 and 1
        
    Why: A positive gap (demand > supply) indicates opportunity.
    The score is clamped to [0, 1] to ensure consistent interpretation.
    When demand equals supply, gap is 0.5, representing neutral market.
    """
    gap = demand_score - supply_score
    # Map from [-1, 1] to [0, 1]: (gap + 1) / 2
    normalized_gap = (gap + 1) / 2
    return max(0.0, min(1.0, normalized_gap))


def assign_verdict(gap_score: float) -> Literal["high_opportunity", "competitive", "saturated"]:
    """
    Pure function to assign verdict based on gap score.
    
    Thresholds:
    - gap_score >= 0.6: high_opportunity
    - 0.3 <= gap_score < 0.6: competitive
    - gap_score < 0.3: saturated
    
    Args:
        gap_score: Computed gap score (0-1)
        
    Returns:
        Verdict string
        
    Why: These thresholds segment the market into actionable categories.
    High opportunity means demand significantly exceeds supply (clear opportunity).
    Competitive means demand and supply are balanced (requires differentiation).
    Saturated means supply exceeds demand (difficult market entry).
    """
    if gap_score >= HIGH_OPPORTUNITY_THRESHOLD:
        return "high_opportunity"
    elif gap_score >= COMPETITIVE_THRESHOLD:
        return "competitive"
    else:
        return "saturated"


def compute_gap_score_for_category(
    session: Session,
    category: str,
    platform: str,
    week_start: date
) -> GapScore | None:
    """
    Compute gap score for a specific category+platform+week combination.
    
    Process:
    1. Aggregate all demand signals (average normalized_value)
    2. Aggregate all supply signals (average normalized_value)
    3. Compute gap_score = demand - supply (normalized to 0-1)
    4. Assign verdict based on thresholds
    
    Args:
        session: Database session
        category: Product category
        platform: Platform identifier
        week_start: Week identifier
        
    Returns:
        GapScore object or None if no metrics found
        
    Why: Averaging normalized values provides a stable aggregate score that
    represents overall demand/supply position for the category.
    """
    # Aggregate demand signals
    demand_statement = select(
        func.avg(MarketplaceMetrics.normalized_value)
    ).where(
        MarketplaceMetrics.category == category,
        MarketplaceMetrics.platform == platform,
        MarketplaceMetrics.week_start == week_start,
        MarketplaceMetrics.metric_type == "demand"
    )
    demand_score = session.exec(demand_statement).first() or 0.0
    
    # Aggregate supply signals
    supply_statement = select(
        func.avg(MarketplaceMetrics.normalized_value)
    ).where(
        MarketplaceMetrics.category == category,
        MarketplaceMetrics.platform == platform,
        MarketplaceMetrics.week_start == week_start,
        MarketplaceMetrics.metric_type == "supply"
    )
    supply_score = session.exec(supply_statement).first() or 0.0
    
    # If no metrics exist, skip
    if demand_score == 0.0 and supply_score == 0.0:
        return None
    
    # Compute gap score and verdict
    gap = compute_gap_score(demand_score, supply_score)
    verdict = assign_verdict(gap)
    
    # Create and return GapScore object
    return GapScore(
        category=category,
        platform=platform,
        gap_score=gap,
        verdict=verdict,
        week_start=week_start
    )


def compute_all_gap_scores_for_week(session: Session, week_start: date) -> int:
    """
    Compute gap scores for all category+platform combinations for a given week.
    
    This is the main entry point called by the Windmill compute pipeline.
    
    Args:
        session: Database session
        week_start: Week identifier
        
    Returns:
        Number of gap scores computed and stored
        
    Why: This function ensures all opportunities are identified in a single
    operation. It's idempotent and can be re-run safely.
    """
    # Get all unique category+platform combinations for this week
    statement = select(
        MarketplaceMetrics.category,
        MarketplaceMetrics.platform
    ).where(
        MarketplaceMetrics.week_start == week_start
    ).distinct()
    
    combinations = session.exec(statement).all()
    
    # Delete existing gap scores for this week to ensure idempotency
    delete_statement = select(GapScore).where(GapScore.week_start == week_start)
    existing_scores = session.exec(delete_statement).all()
    for score in existing_scores:
        session.delete(score)
    session.commit()
    
    # Compute gap score for each combination
    computed_count = 0
    for category, platform in combinations:
        gap_score = compute_gap_score_for_category(
            session, category, platform, week_start
        )
        if gap_score:
            session.add(gap_score)
            computed_count += 1
    
    session.commit()
    return computed_count
