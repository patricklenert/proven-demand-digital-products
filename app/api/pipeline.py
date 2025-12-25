"""
Pipeline orchestration endpoints.
These endpoints trigger scraping and computation operations.
Scraping and computation run as background Celery tasks.
"""
from datetime import date
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session
from app.database import get_session
from app.services.tasks import scrape_platform_task, compute_pipeline_task


router = APIRouter(tags=["pipeline"])


class ComputeRequest(BaseModel):
    """Request model for compute endpoint."""
    week_start: date
    
    class Config:
        json_schema_extra = {
            "example": {
                "week_start": "2025-12-23"
            }
        }


class ScrapeRequest(BaseModel):
    """Request model for scrape endpoint."""
    category: str
    week_start: date
    
    class Config:
        json_schema_extra = {
            "example": {
                "category": "digital planners",
                "week_start": "2025-12-23"
            }
        }


@router.post("/compute")
async def compute_pipeline(
    request: ComputeRequest,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """
    Trigger full computation pipeline for a given week.
    
    This endpoint returns immediately and runs the computation in the background.
    
    Pipeline steps (run asynchronously):
    1. Fetch all raw metrics for the week
    2. Normalize all metrics
    3. Compute gap scores for all category+platform combinations
    4. Write results to gap_scores table
    
    Args:
        request: Contains week_start date
        session: Database session
        
    Returns:
        Task ID for tracking progress
    """
    try:
        # Trigger background task
        task = compute_pipeline_task.delay(str(request.week_start))
        
        return {
            "status": "queued",
            "task_id": task.id,
            "week_start": str(request.week_start),
            "message": "Computation pipeline started in background. Use task_id to check status."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue pipeline: {str(e)}")


@router.post("/scrape/{platform}")
async def scrape_platform(
    platform: str,
    request: ScrapeRequest,
    session: Session = Depends(get_session)
) -> Dict[str, Any]:
    """
    Trigger scraping for a specific platform and category.
    
    This endpoint returns immediately and runs the scraping in the background.
    For Etsy with Brightdata API, this can take up to 6 minutes.
    
    Collect raw metrics from marketplaces.
    Each platform can be scraped independently, allowing parallel execution.
    
    Args:
        platform: Platform identifier (etsy, gumroad, whop, reddit)
        request: Contains category and week_start
        session: Database session
        
    Returns:
        Task ID for tracking progress
    """
    # Validate platform
    valid_platforms = ["etsy", "gumroad", "whop", "reddit"]
    
    if platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform: {platform}. Must be one of: {valid_platforms}"
        )
    
    try:
        # Trigger background task
        task = scrape_platform_task.delay(
            platform=platform,
            category=request.category,
            week_start=str(request.week_start)
        )
        
        return {
            "status": "queued",
            "task_id": task.id,
            "platform": platform,
            "category": request.category,
            "week_start": str(request.week_start),
            "message": f"Scraping {platform} started in background. Use task_id to check status."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue scraping task: {str(e)}")


@router.get("/task/{task_id}")
async def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get the status of a background task.
    
    Args:
        task_id: Celery task ID
        
    Returns:
        Task status and result (if completed)
    """
    from app.celery_app import celery_app
    
    try:
        task_result = celery_app.AsyncResult(task_id)
        
        if task_result.state == 'PENDING':
            return {
                "task_id": task_id,
                "status": "pending",
                "message": "Task is waiting to be executed"
            }
        elif task_result.state == 'PROGRESS':
            return {
                "task_id": task_id,
                "status": "in_progress",
                "progress": task_result.info
            }
        elif task_result.state == 'SUCCESS':
            return {
                "task_id": task_id,
                "status": "completed",
                "result": task_result.result
            }
        elif task_result.state == 'FAILURE':
            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(task_result.info)
            }
        else:
            return {
                "task_id": task_id,
                "status": task_result.state,
                "info": str(task_result.info)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")
