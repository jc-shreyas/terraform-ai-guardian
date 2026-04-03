"""
State definition for the CI/CD Debugger Agent.
Plain Python dataclasses that are passed through each processing step.
"""

from dataclasses import dataclass, field


@dataclass
class FileFix:
    """A fix to apply to a single file."""
    path: str = ""
    change_description: str = ""
    before: str = ""
    after: str = ""


@dataclass
class CICDDebugState:
    """State passed through each step of the CI/CD Debugger agent."""

    # Input
    repo: str = ""                  # "owner/repo"
    run_id: int = 0                 # GitHub Actions workflow run ID

    # Step 1: Fetch logs
    raw_logs: str = ""              # Full log output from the failed run
    workflow_file: str = ""         # The .yml workflow definition

    # Step 2: Parse failure
    failing_job: str = ""           # Which job failed
    failing_step: str = ""          # Which step within the job
    error_message: str = ""         # Extracted error message
    error_context: str = ""         # ~50 lines around the error

    # Step 3: Identify context
    related_files: dict = field(default_factory=dict)   # {filepath: content} for files the step touches

    # Step 4: Root cause analysis
    root_cause: str = ""            # Claude's diagnosis
    error_type: str = ""            # syntax_error, config_error, auth_error, etc.
    confidence: str = ""            # high, medium, low

    # Step 5: Generate fix
    fix_description: str = ""       # What needs to change
    files_to_fix: list = field(default_factory=list)    # Concrete file changes (list of FileFix)
    prevention: str = ""            # How to prevent recurrence

    # Step 6: Apply fix (optional)
    fix_branch: str = ""            # Branch name if fix PR was created
    fix_pr_url: str = ""            # URL of the fix PR (empty if not created)

    # Error tracking
    errors: list = field(default_factory=list)
