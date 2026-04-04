"""
CI/CD Debugger Agent — diagnoses failed GitHub Actions workflow runs.

Usage:
    python agent-cicd-debugger/main.py --repo owner/repo --run-id 12345678
"""

import argparse
import io
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field

import anthropic
import requests
from dotenv import load_dotenv
from github import Auth, Github

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are a senior DevOps engineer debugging CI/CD pipeline failures.

Given the workflow definition, failure logs, and error context, provide a structured diagnosis with exactly these four sections:

**Root cause:** What exactly failed and why — be specific about the error, the file or command involved, and what triggered it.

**Category:** One of: config_error, dependency_issue, credentials, code_error, infra_issue, flaky_test — with a one-line justification.

**Fix:** Exact steps or code changes to resolve this. Include concrete commands or YAML snippets where relevant.

**Prevention:** How to prevent this class of failure in the future — tooling, process, or config changes."""

ERROR_PATTERN = re.compile(
    r"(error|Error|ERROR|fatal|Fatal|FATAL|failed|Failed|FAILED"
    r"|exception|Exception|EXCEPTION|traceback|Traceback"
    r"|panic|PANIC|exit code [1-9])",
)

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s*")

CONTEXT_LINES = 50


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class CICDDebugState:
    repo_name: str
    run_id: int
    run_name: str = ""
    head_branch: str = ""
    head_sha: str = ""
    conclusion: str = ""
    failed_job: str = ""
    failed_step: str = ""
    error_message: str = ""
    log_context: str = ""
    workflow_yaml: str = ""
    diagnosis: str = ""


# ---------------------------------------------------------------------------
# Steps
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

    # Find the first failed job and its first failed step
    for job in run.jobs():
        if job.conclusion != "failure":
            continue
        state.failed_job = job.name
        for step in job.steps:
            if step.conclusion == "failure":
                state.failed_step = step.name
                break
        break  # stop at first failed job


def fetch_workflow_yaml(state: CICDDebugState, github_token: str) -> None:
    """Fetch the workflow YAML file that triggered this run."""
    gh = Github(auth=Auth.Token(github_token))
    repo = gh.get_repo(state.repo_name)
    run = repo.get_workflow_run(state.run_id)

    try:
        workflow = repo.get_workflow(run.workflow_id)
        # workflow.path is e.g. ".github/workflows/pr-review.yml"
        contents = repo.get_contents(workflow.path, ref=state.head_sha)
        state.workflow_yaml = contents.decoded_content.decode("utf-8")
    except Exception:
        state.workflow_yaml = "(workflow YAML unavailable)"


def _clean_line(line: str) -> str:
    line = ANSI_ESCAPE.sub("", line)
    line = TIMESTAMP.sub("", line)
    return line.rstrip()


def fetch_and_parse_logs(state: CICDDebugState, github_token: str) -> None:
    """Download log zip, find the failed job log, extract error + context."""
    # PyGithub doesn't expose the logs download URL directly, so use the REST API
    url = f"https://api.github.com/repos/{state.repo_name}/actions/runs/{state.run_id}/logs"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(response.content))

    # The zip contains one file per job, named "<job_name>/<step_number>_<step_name>.txt"
    # Find the file that belongs to the failed job (case-insensitive prefix match)
    target_prefix = state.failed_job.lower().replace(" ", "_") if state.failed_job else ""

    log_text = _pick_best_log(zf, target_prefix)
    if not log_text:
        state.error_message = "(log extraction failed)"
        state.log_context = ""
        return

    lines = [_clean_line(l) for l in log_text.splitlines()]

    # Find the first line that looks like an error
    error_idx = next(
        (i for i, l in enumerate(lines) if ERROR_PATTERN.search(l)),
        len(lines) - 1,
    )

    state.error_message = lines[error_idx]
    start = max(0, error_idx - 10)
    end = min(len(lines), error_idx + CONTEXT_LINES)
    state.log_context = "\n".join(lines[start:end])


def _pick_best_log(zf: zipfile.ZipFile, target_prefix: str) -> str:
    """Return the log text most likely to contain the failure."""
    names = zf.namelist()

    # Prefer files whose directory matches the failed job name
    if target_prefix:
        candidates = [n for n in names if n.lower().startswith(target_prefix)]
        if not candidates:
            # Fallback: any file under a directory that contains the prefix
            candidates = [n for n in names if target_prefix in n.lower()]
    else:
        candidates = names

    if not candidates:
        candidates = names  # last resort: search everything

    # Among candidates, prefer the last file (most likely to contain the failure)
    candidates.sort()
    chosen = candidates[-1]

    with zf.open(chosen) as f:
        return f.read().decode("utf-8", errors="replace")


def call_claude(state: CICDDebugState, api_key: str) -> None:
    """Send run context to Claude and store the diagnosis in state."""
    client = anthropic.Anthropic(api_key=api_key)

    user_message = _build_user_message(state)

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    state.diagnosis = response.content[0].text.strip()


def _build_user_message(state: CICDDebugState) -> str:
    parts = [
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
        "## Log Context (up to 50 lines around the error)",
        f"```\n{state.log_context}\n```",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

BOLD  = "\033[1m"
CYAN  = "\033[36m"
RED   = "\033[31m"
RESET = "\033[0m"


def print_diagnosis(state: CICDDebugState) -> None:
    print(f"\n{BOLD}{'=' * 70}{RESET}")
    print(f"{BOLD}  CI/CD Failure Diagnosis{RESET}")
    print(f"  Repo: {state.repo_name}  |  Run ID: {state.run_id}")
    print(f"  Workflow: {state.run_name}  |  Branch: {state.head_branch}")
    print(f"  Failed job: {state.failed_job or '(unknown)'}  |  Step: {state.failed_step or '(unknown)'}")
    print(f"{BOLD}{'=' * 70}{RESET}")
    print(f"\n{CYAN}{state.diagnosis}{RESET}")
    print(f"\n{BOLD}{'=' * 70}{RESET}\n")


# ---------------------------------------------------------------------------
# GitHub posting
# ---------------------------------------------------------------------------

def post_comment_to_commit(state: CICDDebugState, github_token: str) -> str:
    """Post the diagnosis as a commit comment and return the comment URL."""
    gh = Github(auth=Auth.Token(github_token))
    repo = gh.get_repo(state.repo_name)
    commit = repo.get_commit(state.head_sha)

    body = _build_commit_comment(state)
    comment = commit.create_comment(body)
    return comment.html_url


def _build_commit_comment(state: CICDDebugState) -> str:
    lines = [
        "## CI/CD Failure Diagnosis",
        "",
        f"**Workflow:** {state.run_name}  |  **Branch:** `{state.head_branch}`",
        f"**Failed job:** `{state.failed_job or 'unknown'}`  |  **Failed step:** `{state.failed_step or 'unknown'}`",
        "",
        "<details><summary>Error context</summary>",
        "",
        f"```\n{state.error_message}\n```",
        "",
        "</details>",
        "",
        "---",
        "",
        state.diagnosis,
        "",
        "---",
        "*Posted by terraform-ai-guardian*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI-powered CI/CD failure debugger")
    parser.add_argument("--repo", required=True, help='GitHub repo, e.g. "owner/repo"')
    parser.add_argument("--run-id", required=True, type=int, help="GitHub Actions workflow run ID")
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
    print(f"  Workflow : {state.run_name}")
    print(f"  Branch   : {state.head_branch}")
    print(f"  Result   : {state.conclusion}")
    print(f"  Failed job  : {state.failed_job or '(unknown)'}")
    print(f"  Failed step : {state.failed_step or '(unknown)'}")

    print("Fetching workflow YAML...")
    fetch_workflow_yaml(state, github_token)

    print("Downloading and parsing logs...")
    fetch_and_parse_logs(state, github_token)

    print("Sending to Claude for diagnosis...")
    call_claude(state, api_key)

    print_diagnosis(state)

    print("Posting diagnosis to GitHub commit...")
    comment_url = post_comment_to_commit(state, github_token)
    print(f"Comment posted: {comment_url}")


if __name__ == "__main__":
    main()
