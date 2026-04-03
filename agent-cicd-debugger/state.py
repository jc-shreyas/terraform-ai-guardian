"""
State definition for the CI/CD Debugger Agent.
This TypedDict flows through every node in the LangGraph state machine.
"""

from typing import TypedDict


class FileFix(TypedDict):
    """A fix to apply to a single file."""
    path: str
    change_description: str
    before: str
    after: str


class CICDDebugState(TypedDict):
    """State that flows through the CI/CD Debugger LangGraph."""

    # Input
    repo: str                       # "owner/repo"
    run_id: int                     # GitHub Actions workflow run ID

    # Step 1: Fetch logs
    raw_logs: str                   # Full log output from the failed run
    workflow_file: str              # The .yml workflow definition

    # Step 2: Parse failure
    failing_job: str                # Which job failed
    failing_step: str               # Which step within the job
    error_message: str              # Extracted error message
    error_context: str              # ~50 lines around the error

    # Step 3: Identify context
    related_files: dict             # {filepath: content} for files the step touches

    # Step 4: Root cause analysis
    root_cause: str                 # Claude's diagnosis
    error_type: str                 # syntax_error, config_error, auth_error, etc.
    confidence: str                 # high, medium, low

    # Step 5: Generate fix
    fix_description: str            # What needs to change
    files_to_fix: list[FileFix]     # Concrete file changes
    prevention: str                 # How to prevent recurrence

    # Step 6: Apply fix (optional)
    fix_branch: str                 # Branch name if fix PR was created
    fix_pr_url: str                 # URL of the fix PR (empty if not created)

    # Error tracking
    errors: list[str]
