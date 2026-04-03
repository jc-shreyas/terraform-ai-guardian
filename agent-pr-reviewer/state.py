"""
State definition for the PR Reviewer Agent.
Plain Python dataclasses that are passed through each processing step.
"""

from dataclasses import dataclass, field


@dataclass
class ReviewFinding:
    """A single review finding."""
    file: str = ""
    line: int = 0
    severity: str = ""           # critical, high, medium, low
    category: str = ""           # security, cost, reliability, best_practice
    title: str = ""
    explanation: str = ""
    suggestion: str = ""
    estimated_cost_impact: str = ""
    source: str = ""             # "tfsec", "checkov", "ai_review"


@dataclass
class PRReviewState:
    """State passed through each step of the PR Reviewer agent."""

    # Input
    repo: str = ""                              # "owner/repo"
    pr_number: int = 0                          # PR number to review

    # Step 1: Fetch diff
    changed_files: list = field(default_factory=list)   # [{filename, status, patch, additions, deletions}]

    # Step 2: Static analysis
    static_findings: list = field(default_factory=list) # Findings from tfsec + checkov

    # Step 3: Context gathering
    file_contents: dict = field(default_factory=dict)   # {filepath: full_content} for AI context

    # Step 4: AI review
    ai_findings: list = field(default_factory=list)     # Findings from Claude analysis

    # Step 5: Synthesis
    all_findings: list = field(default_factory=list)    # Merged + deduplicated + ranked
    review_summary: str = ""                            # Human-readable summary

    # Step 6: Post review
    review_posted: bool = False                         # Whether the review was posted to GitHub

    # Error tracking
    errors: list = field(default_factory=list)          # Any errors encountered during the run
