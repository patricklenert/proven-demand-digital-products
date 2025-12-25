"""
Notion integration service for publishing reports.
"""
import os
from typing import List, Dict, Any
from notion_client import AsyncClient
from app.models.summary import SummaryResponse, SummaryOpportunity


class NotionService:
    """Service for interacting with Notion API."""
    
    def __init__(self):
        self.api_key = os.getenv("NOTION_API_KEY")
        self.parent_page_id = os.getenv("NOTION_PARENT_PAGE_ID")
        
        if not self.api_key:
            raise ValueError("NOTION_API_KEY is not set")
        if not self.parent_page_id:
            raise ValueError("NOTION_PARENT_PAGE_ID is not set")
            
        self.client = AsyncClient(auth=self.api_key)

    async def create_weekly_report(self, summary: SummaryResponse) -> str:
        """
        Create a new weekly report page in Notion.
        
        Args:
            summary: The summary data to publish
            
        Returns:
            URL of the created page
        """
        title = f"Weekly Demand Report - {summary.week_start}"
        
        # 1. Create the page
        new_page = await self.client.pages.create(
            parent={"page_id": self.parent_page_id},
            properties={
                "title": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }
            },
            children=self._generate_report_content(summary)
        )
        
        return new_page["url"]

    def _generate_report_content(self, summary: SummaryResponse) -> List[Dict[str, Any]]:
        """Generate the block structure for the report."""
        blocks = []
        
        # Executive Summary / Intro
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": f"Report for the week starting {summary.week_start}. This report highlights high-demand opportunities and saturated markets based on platform data."
                        }
                    }
                ]
            }
        })
        
        # Top Opportunities Section
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "🚀 Top Opportunities"}}]
            }
        })
        
        if summary.top_opportunities:
            blocks.append(self._create_table(summary.top_opportunities))
        else:
            blocks.append(self._create_text_block("No high opportunities found this week."))

        # Saturated Categories Section
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "⚠️ Saturated Categories"}}]
            }
        })
        
        if summary.saturated_categories:
            blocks.append(self._create_table(summary.saturated_categories))
        else:
            blocks.append(self._create_text_block("No saturated categories found this week."))

        # Market Movement Section
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "📉 Market Movement"}}]
            }
        })
        
        notes = summary.market_movement_notes or "No specific market movement notes for this week."
        blocks.append(self._create_text_block(notes))
        
        return blocks

    def _create_text_block(self, content: str) -> Dict[str, Any]:
        """Helper to create a simple paragraph block."""
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": content}}]
            }
        }

    def _create_table(self, items: List[SummaryOpportunity]) -> Dict[str, Any]:
        """Create a Notion table block from a list of opportunities."""
        table_rows = []
        
        # Header Row
        table_rows.append({
            "type": "table_row",
            "table_row": {
                "cells": [
                    [{"type": "text", "text": {"content": "Category"}}],
                    [{"type": "text", "text": {"content": "Platform"}}],
                    [{"type": "text", "text": {"content": "Gap Score"}}],
                    [{"type": "text", "text": {"content": "Verdict"}}]
                ]
            }
        })
        
        # Data Rows
        for item in items:
            table_rows.append({
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": item.category}}],
                        [{"type": "text", "text": {"content": item.platform}}],
                        [{"type": "text", "text": {"content": f"{item.gap_score:.2f}"}}],
                        [{"type": "text", "text": {"content": item.verdict}}]
                    ]
                }
            })
            
        return {
            "object": "block",
            "type": "table",
            "table": {
                "table_width": 4,
                "has_column_header": True,
                "has_row_header": False,
                "children": table_rows
            }
        }
