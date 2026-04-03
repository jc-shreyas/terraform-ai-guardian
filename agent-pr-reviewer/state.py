"""
State definition for the PR Reviewer Agent.
This TypedDict flows through every node in the LangGraph state machine.
Each node reads what it needs and returns only the fields it updates.
"""

from typing import TypedDict


class ReviewFinding(TypedDict):
    """A single review finding."""
    file: str
    line: int
    severity: str           # critical, high, medium, low
    category: str           # security, cost, reliability, best_practice
    title: str
    explanation: str
    suggestion: str
    estimated_cost_impact: str
    source: str             # "tfsec", "checkov", "ai_review"


class PRReviewState(TypedDict):
    """State that flows through the PR Reviewer LangGraph."""

    # Input
    repo: str                               # "owner/repo"
    pr_number: int                          # PR number to review

    # Step 1: Fetch diff
    changed_files: list[dict]               # [{filename, status, patch, additions, deletions}]

    # Step 2: Static analysis
    static_findings: list[ReviewFinding]    # Findings from tfsec + checkov

    # Step 3: Context gathering
    file_contents: dict                     # {filepath: full_content} for AI context

    # Step 4: AI review
    ai_findings: list[ReviewFinding]        # Findings from Claude analysis

    # Step 5: Synthesis
    all_findings: list[ReviewFinding]       # Merged + deduplicated + ranked
    review_summary: str                     # Human-readable summary

    # Step 6: Post review
    review_posted: bool                     # Whether the review was posted to GitHub

    # Error tracking
    errors: list[str]                       # Any errors encountered during the run
