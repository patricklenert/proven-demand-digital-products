"""
Deterministic normalization service for marketplace metrics.
Converts raw values to normalized scores (0-1 range) for fair comparison.
"""
from datetime import date
from typing import List
from sqlmodel import Session, select
from app.models.marketplace_metrics import MarketplaceMetrics


def normalize_min_max(value: float, min_val: float, max_val: float) -> float:
    """
    Pure min-max normalization function.
    
    Formula: (value - min) / (max - min)
    
    Args:
        value: The value to normalize
        min_val: Minimum value in the dataset
        max_val: Maximum value in the dataset
        
    Returns:
        Normalized value between 0 and 1
        
    Why: Min-max normalization ensures all values are scaled to 0-1 range
    while preserving relative distances. This allows cross-category comparison
    within the same platform and metric type.
    """
    if max_val == min_val:
        # All values are identical, return midpoint
        return 0.5
    
    normalized = (value - min_val) / (max_val - min_val)
    # Clamp to [0, 1] to handle edge cases
    return max(0.0, min(1.0, normalized))


def normalize_metrics_for_week(
    session: Session,
    platform: str,
    metric_type: str,
    week_start: date
) -> int:
    """
    Normalize all raw metrics for a given platform, metric_type, and week.
    
    This function is idempotent - it updates normalized_value for all matching
    metrics based on their raw_value using min-max normalization within the cohort.
    
    Args:
        session: Database session
        platform: Platform identifier (etsy, gumroad, whop, reddit)
        metric_type: Either 'demand' or 'supply'
        week_start: Week identifier
        
    Returns:
        Number of metrics normalized
        
    Why: Normalizing within platform+metric_type+week cohorts ensures that
    scores reflect relative position within comparable data. A high raw demand
    on Etsy should be normalized relative to other Etsy demand signals, not
    relative to Gumroad signals.
    """
    # Fetch all metrics for this cohort
    statement = select(MarketplaceMetrics).where(
        MarketplaceMetrics.platform == platform,
        MarketplaceMetrics.metric_type == metric_type,
        MarketplaceMetrics.week_start == week_start
    )
    metrics = session.exec(statement).all()
    
    if not metrics:
        return 0
    
    # Extract raw values and compute min/max
    raw_values = [m.raw_value for m in metrics]
    min_val = min(raw_values)
    max_val = max(raw_values)
    
    # Update each metric with normalized value
    for metric in metrics:
        metric.normalized_value = normalize_min_max(metric.raw_value, min_val, max_val)
    
    session.commit()
    return len(metrics)


def normalize_all_metrics_for_week(session: Session, week_start: date) -> int:
    """
    Normalize all metrics across all platforms and metric types for a given week.
    
    This is the main entry point called by the Windmill compute pipeline.
    
    Args:
        session: Database session
        week_start: Week identifier
        
    Returns:
        Total number of metrics normalized
        
    Why: This function ensures the entire week's data is normalized in a single
    operation, maintaining consistency across all cohorts.
    """
    platforms = ["etsy", "gumroad", "whop", "reddit"]
    metric_types = ["demand", "supply"]
    
    total_normalized = 0
    
    for platform in platforms:
        for metric_type in metric_types:
            count = normalize_metrics_for_week(
                session, platform, metric_type, week_start
            )
            total_normalized += count
    
    return total_normalized
