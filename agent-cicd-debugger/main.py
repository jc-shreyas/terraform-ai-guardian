"""
CI/CD Debugger Agent — diagnoses failed GitHub Actions workflow runs.

Usage:
    python agent-cicd-debugger/main.py --repo owner/repo --run-id 12345678
"""

import argparse
import io
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass

import anthropic
import requests
from dotenv import load_dotenv
from github import Auth, Github

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are a senior DevOps engineer debugging CI/CD pipeline failures.

Given the workflow definition, failure logs, and error context, return ONLY a JSON object with no other text. Use exactly this schema:

{
  "root_cause": "What exactly failed and why — specific about the error, file/command involved, and what triggered it",
  "category": "one of: config_error, dependency_issue, credentials, code_error, infra_issue, flaky_test",
  "failed_step": "The name of the step that failed",
  "fix": "Exact steps or code changes to resolve this. Include concrete commands or YAML snippets.",
  "prevention": "How to prevent this class of failure in the future — tooling, process, or config changes"
}"""

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s*")

ERROR_PATTERN = re.compile(
    r"(error|Error|ERROR|fatal|Fatal|FATAL|failed|Failed|FAILED"
    r"|exception|Exception|EXCEPTION|traceback|Traceback"
    r"|panic|PANIC|exit code [1-9])",
)

CONTEXT_LINES = 50


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class CICDDebugState:
    repo_name: str
    run_id: int
    # Run metadata
    run_name: str = ""
    head_branch: str = ""
    head_sha: str = ""
    conclusion: str = ""
    # Log parsing
    failed_job: str = ""
    failed_job_id: int = 0
    failed_step: str = ""
    error_message: str = ""
    log_context: str = ""
    workflow_yaml: str = ""
    # Diagnosis (populated from Claude JSON)
    root_cause: str = ""
    category: str = ""
    diagnosed_step: str = ""
    fix: str = ""
    prevention: str = ""


# ---------------------------------------------------------------------------
# Step 1: Fetch run metadata
# ---------------------------------------------------------------------------

def fetch_run_metadata(state: CICDDebugState, github_token: str) -> None:
    """Populate run metadata and identify the first failed job/step."""
    gh = Github(auth=Auth.Token(github_token))
    repo = gh.get_repo(state.repo_name)
    run = repo.get_workflow_run(state.run_id)

    state.run_name = run.name or ""
    state.head_branch = run.head_branch or ""
    state.head_sha = run.head_sha or ""
    state.conclusion = run.conclusion or ""

    for job in run.jobs():
        if job.conclusion != "failure":
            continue
        state.failed_job = job.name
        state.failed_job_id = job.id
        for step in job.steps:
            if step.conclusion == "failure":
                state.failed_step = step.name
                break
        break  # stop at first failed job


# ---------------------------------------------------------------------------
# Step 2: Fetch workflow YAML
# ---------------------------------------------------------------------------

def fetch_workflow_yaml(state: CICDDebugState, github_token: str) -> None:
    """Fetch the workflow YAML file that triggered this run."""
    gh = Github(auth=Auth.Token(github_token))
    repo = gh.get_repo(state.repo_name)
    run = repo.get_workflow_run(state.run_id)

    try:
        workflow = repo.get_workflow(run.workflow_id)
        contents = repo.get_contents(workflow.path, ref=state.head_sha)
        state.workflow_yaml = contents.decoded_content.decode("utf-8")
    except Exception:
        state.workflow_yaml = "(workflow YAML unavailable)"


# ---------------------------------------------------------------------------
# Step 3: Download and parse logs
# ---------------------------------------------------------------------------

def fetch_and_parse_logs(state: CICDDebugState, github_token: str) -> None:
    """Download logs for the failed job, extract error + context.

    Uses the per-job logs endpoint when a job ID is available (plain text, no zip),
    falling back to the run-level zip endpoint. GitHub redirects both to a pre-signed
    CDN URL — the Authorization header must NOT be forwarded to the CDN or it 403s.
    """
    auth_headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    log_text = None

    # Prefer per-job endpoint (returns plain text, no zip needed)
    if state.failed_job_id:
        job_url = f"https://api.github.com/repos/{state.repo_name}/actions/jobs/{state.failed_job_id}/logs"
        log_text = _download_following_redirect(job_url, auth_headers)

    # Fall back to run-level zip
    if log_text is None:
        run_url = f"https://api.github.com/repos/{state.repo_name}/actions/runs/{state.run_id}/logs"
        zip_bytes = _download_following_redirect(run_url, auth_headers, binary=True)
        if zip_bytes:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
            target_prefix = state.failed_job.lower().replace(" ", "_") if state.failed_job else ""
            log_text = _pick_best_log(zf, target_prefix)

    if not log_text:
        state.error_message = "(log extraction failed)"
        state.log_context = ""
        return

    lines = [_clean_line(l) for l in log_text.splitlines()]

    error_idx = next(
        (i for i, l in enumerate(lines) if ERROR_PATTERN.search(l)),
        len(lines) - 1,
    )

    state.error_message = lines[error_idx]
    start = max(0, error_idx - 10)
    end = min(len(lines), error_idx + CONTEXT_LINES)
    state.log_context = "\n".join(lines[start:end])


def _download_following_redirect(url: str, auth_headers: dict, binary: bool = False):
    """GET url with auth headers, then follow any redirect WITHOUT auth headers.

    GitHub's log endpoints return a 302 to a pre-signed CDN URL. Sending the
    Authorization header to the CDN causes a 403, so we handle the redirect manually.
    Returns decoded text (or raw bytes if binary=True), or None on failure.
    """
    # Step 1: hit the API endpoint to get the redirect location
    r1 = requests.get(url, headers=auth_headers, allow_redirects=False, timeout=30)
    if r1.status_code not in (301, 302, 303, 307, 308):
        # No redirect — response body is the content itself
        if r1.ok:
            return r1.content if binary else r1.text
        return None

    cdn_url = r1.headers.get("Location")
    if not cdn_url:
        return None

    # Step 2: download from CDN without auth headers
    r2 = requests.get(cdn_url, timeout=180)
    if not r2.ok:
        return None
    return r2.content if binary else r2.text


def _clean_line(line: str) -> str:
    line = ANSI_ESCAPE.sub("", line)
    line = TIMESTAMP.sub("", line)
    return line.rstrip()


def _pick_best_log(zf: zipfile.ZipFile, target_prefix: str) -> str:
    """Return the log text most likely to contain the failure."""
    names = zf.namelist()

    if target_prefix:
        candidates = [n for n in names if n.lower().startswith(target_prefix)]
        if not candidates:
            candidates = [n for n in names if target_prefix in n.lower()]
    else:
        candidates = names

    if not candidates:
        candidates = names

    candidates.sort()
    with zf.open(candidates[-1]) as f:
        return f.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Step 4: Call Claude
# ---------------------------------------------------------------------------

def call_claude(state: CICDDebugState, api_key: str) -> None:
    """Send run context to Claude, parse the JSON diagnosis, and store in state."""
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(state)}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped the JSON
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

    diagnosis = json.loads(raw)
    state.root_cause = diagnosis.get("root_cause", "")
    state.category = diagnosis.get("category", "")
    state.diagnosed_step = diagnosis.get("failed_step", "")
    state.fix = diagnosis.get("fix", "")
    state.prevention = diagnosis.get("prevention", "")


def _build_user_message(state: CICDDebugState) -> str:
    return "\n".join([
        "## Workflow Run",
        f"- **Workflow:** {state.run_name}",
        f"- **Branch:** {state.head_branch}",
        f"- **Conclusion:** {state.conclusion}",
        f"- **Failed job:** {state.failed_job or '(unknown)'}",
        f"- **Failed step:** {state.failed_step or '(unknown)'}",
        "",
        "## Workflow Definition",
        f"```yaml\n{state.workflow_yaml}\n```",
        "",
        "## Error Line",
        f"```\n{state.error_message}\n```",
        "",
        "## Log Context (~50 lines around the error)",
        f"```\n{state.log_context}\n```",
    ])


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

BOLD  = "\033[1m"
RED   = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
CYAN  = "\033[36m"
RESET = "\033[0m"

CATEGORY_COLORS = {
    "config_error":      YELLOW,
    "dependency_issue":  YELLOW,
    "credentials":       RED,
    "code_error":        RED,
    "infra_issue":       YELLOW,
    "flaky_test":        CYAN,
}


def print_diagnosis(state: CICDDebugState) -> None:
    cat_color = CATEGORY_COLORS.get(state.category, CYAN)

    print(f"\n{BOLD}{'=' * 70}{RESET}")
    print(f"{BOLD}  CI/CD Failure Diagnosis{RESET}")
    print(f"  Repo     : {state.repo_name}  |  Run ID: {state.run_id}")
    print(f"  Workflow : {state.run_name}  |  Branch: {state.head_branch}")
    print(f"  Failed job  : {state.failed_job or '(unknown)'}")
    print(f"  Failed step : {state.diagnosed_step or state.failed_step or '(unknown)'}")
    print(f"  Category    : {cat_color}{BOLD}{state.category}{RESET}")
    print(f"{BOLD}{'=' * 70}{RESET}")

    print(f"\n{RED}{BOLD}Root Cause{RESET}")
    print(f"  {state.root_cause}")

    print(f"\n{YELLOW}{BOLD}Fix{RESET}")
    for line in state.fix.splitlines():
        print(f"  {line}")

    print(f"\n{GREEN}{BOLD}Prevention{RESET}")
    for line in state.prevention.splitlines():
        print(f"  {line}")

    print(f"\n{BOLD}{'=' * 70}{RESET}\n")


# ---------------------------------------------------------------------------
# Step 5: Post comment (PR or commit)
# ---------------------------------------------------------------------------

def post_comment_to_pr(state: CICDDebugState, pr_number: int, github_token: str) -> str:
    """Post the diagnosis as a PR comment and return the comment URL."""
    gh = Github(auth=Auth.Token(github_token))
    repo = gh.get_repo(state.repo_name)
    pr = repo.get_pull(pr_number)
    comment = pr.create_issue_comment(_build_comment_body(state))
    return comment.html_url


def post_comment_to_commit(state: CICDDebugState, github_token: str) -> str:
    """Post the diagnosis as a commit comment and return the comment URL."""
    gh = Github(auth=Auth.Token(github_token))
    repo = gh.get_repo(state.repo_name)
    commit = repo.get_commit(state.head_sha)
    comment = commit.create_comment(_build_comment_body(state))
    return comment.html_url


def _build_comment_body(state: CICDDebugState) -> str:
    return "\n".join([
        "## CI/CD Failure Diagnosis",
        "",
        f"**Workflow:** {state.run_name} | **Branch:** `{state.head_branch}`",
        f"**Failed job:** `{state.failed_job or 'unknown'}` | **Failed step:** `{state.diagnosed_step or state.failed_step or 'unknown'}`",
        f"**Category:** `{state.category}`",
        "",
        "### Root Cause",
        state.root_cause,
        "",
        "### Fix",
        state.fix,
        "",
        "### Prevention",
        state.prevention,
        "",
        "<details><summary>Error context</summary>",
        "",
        f"```\n{state.error_message}\n```",
        "",
        "</details>",
        "",
        "---",
        "*Posted by terraform-ai-guardian*",
    ])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI-powered CI/CD failure debugger")
    parser.add_argument("--repo", required=True, help='GitHub repo, e.g. "owner/repo"')
    parser.add_argument("--run-id", required=True, type=int, help="GitHub Actions workflow run ID")
    parser.add_argument("--pr", type=int, default=None, help="PR number to post diagnosis to (falls back to commit comment)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Env vars already set (e.g. GitHub Actions secrets) take priority;
    # load_dotenv() only fills in values that aren't already in the environment.
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    github_token = os.getenv("GITHUB_TOKEN")

    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY is not set. Set it as an env var or add it to .env.")
    if not github_token:
        sys.exit("Error: GITHUB_TOKEN is not set. Set it as an env var or add it to .env.")

    state = CICDDebugState(repo_name=args.repo, run_id=args.run_id)

    print(f"Fetching run metadata for run {args.run_id}...")
    fetch_run_metadata(state, github_token)
    print(f"  Workflow    : {state.run_name}")
    print(f"  Branch      : {state.head_branch}")
    print(f"  Conclusion  : {state.conclusion}")
    print(f"  Failed job  : {state.failed_job or '(unknown)'}")
    print(f"  Failed step : {state.failed_step or '(unknown)'}")

    print("Fetching workflow YAML...")
    fetch_workflow_yaml(state, github_token)

    print("Downloading and parsing logs...")
    fetch_and_parse_logs(state, github_token)

    print("Sending to Claude for diagnosis...")
    call_claude(state, api_key)

    print_diagnosis(state)

    if args.pr:
        print(f"Posting diagnosis to PR #{args.pr}...")
        comment_url = post_comment_to_pr(state, args.pr, github_token)
    else:
        print(f"Posting diagnosis to commit {state.head_sha[:7]}...")
        comment_url = post_comment_to_commit(state, github_token)
    print(f"Comment posted: {comment_url}")


if __name__ == "__main__":
    main()
