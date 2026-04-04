"""
PR Reviewer Agent — reviews Terraform files changed in a GitHub PR.

Usage:
    python agent-pr-reviewer/main.py --repo owner/repo --pr 42
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from github import Auth, Github

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are a senior infrastructure security engineer reviewing Terraform code for a production environment.

Review the Terraform file contents provided and identify all issues across these four categories:

SECURITY (severity: critical or high)
- S3 buckets with public access or public ACLs
- IAM policies with wildcard (*) actions or resources
- Security groups open to 0.0.0.0/0 on sensitive ports (22, 3306, 5432, 3389)
- Hardcoded secrets, passwords, or API keys in plain text
- Unencrypted storage (EBS, RDS, S3)
- Publicly accessible databases (publicly_accessible = true)
- Resources without encryption at rest or in transit
- Sensitive outputs not marked as sensitive

COST (severity: medium or high)
- Oversized instance types when smaller would suffice
- Excessive storage allocation without justification
- No lifecycle rules on S3 buckets
- Missing auto-scaling for variable workloads
- Provisioned IOPS without justification

RELIABILITY (severity: medium)
- No multi-AZ for databases
- No automated backups (backup_retention_period = 0)
- No deletion protection on production resources
- skip_final_snapshot = true on databases

BEST PRACTICES (severity: low or medium)
- Missing resource tags (Environment, Team, ManagedBy)
- Hardcoded values that should be variables
- Using default VPC instead of dedicated
- No remote state backend

Return ONLY a JSON array of findings with no other text. Each finding must follow this exact schema:
[
  {
    "file": "infra/main.tf",
    "line": 42,
    "severity": "critical",
    "category": "security",
    "title": "Short description of the issue",
    "explanation": "Why this is a problem and what the risk is",
    "suggestion": "Concrete fix with a Terraform code snippet showing the corrected configuration",
    "estimated_cost_impact": "$0/month"
  }
]

Rules:
- Reference exact resource names and attribute values in your findings
- Every finding must include a concrete fix
- Only flag real issues, not stylistic preferences
- For cost findings, include estimated monthly cost impact
- Return an empty array [] if there are no issues"""


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def fetch_tf_files(repo_name: str, pr_number: int, github_token: str) -> dict[str, str]:
    """Fetch full content of all .tf files changed in the PR."""
    gh = Github(auth=Auth.Token(github_token))
    repo = gh.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    tf_files: dict[str, str] = {}
    for f in pr.get_files():
        if not f.filename.endswith(".tf"):
            continue
        if f.status == "removed":
            continue
        # Fetch full file content at the PR head commit
        content = repo.get_contents(f.filename, ref=pr.head.sha)
        tf_files[f.filename] = content.decoded_content.decode("utf-8")

    return tf_files


def build_user_message(tf_files: dict[str, str]) -> str:
    """Combine all .tf file contents into a single review message."""
    parts = []
    for filepath, content in tf_files.items():
        parts.append(f"### File: {filepath}\n\n```hcl\n{content}\n```")
    return "\n\n---\n\n".join(parts)


def call_claude(tf_files: dict[str, str], api_key: str) -> list[dict]:
    """Send all .tf files to Claude and return parsed findings."""
    client = anthropic.Anthropic(api_key=api_key)

    user_message = build_user_message(tf_files)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Please review the following Terraform files for security, cost, reliability, and best practice issues:\n\n{user_message}",
            }
        ],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped the JSON
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

    return json.loads(raw)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

SEVERITY_ORDER = ["critical", "high", "medium", "low"]

SEVERITY_COLORS = {
    "critical": "\033[91m",  # bright red
    "high":     "\033[31m",  # red
    "medium":   "\033[33m",  # yellow
    "low":      "\033[36m",  # cyan
}
RESET = "\033[0m"
BOLD  = "\033[1m"


def severity_icon(severity: str) -> str:
    icons = {"critical": "CRIT", "high": "HIGH", "medium": " MED", "low": " LOW"}
    return icons.get(severity, severity.upper()[:4].rjust(4))


def print_findings(findings: list[dict], repo: str, pr_number: int) -> None:
    if not findings:
        print(f"\n{BOLD}No issues found.{RESET}")
        return

    # Group by severity
    by_severity: dict[str, list[dict]] = {s: [] for s in SEVERITY_ORDER}
    for f in findings:
        sev = f.get("severity", "low").lower()
        by_severity.setdefault(sev, []).append(f)

    # Summary header
    counts = {s: len(v) for s, v in by_severity.items() if v}
    total = sum(counts.values())
    summary_parts = [f"{c} {s}" for s, c in counts.items()]

    print(f"\n{BOLD}{'=' * 70}{RESET}")
    print(f"{BOLD}  Terraform PR Security Review{RESET}")
    print(f"  Repo: {repo}  |  PR: #{pr_number}")
    print(f"  {total} finding(s): {', '.join(summary_parts)}")
    print(f"{BOLD}{'=' * 70}{RESET}")

    for severity in SEVERITY_ORDER:
        group = by_severity.get(severity, [])
        if not group:
            continue

        color = SEVERITY_COLORS.get(severity, "")
        print(f"\n{color}{BOLD}[{severity.upper()}] — {len(group)} finding(s){RESET}")
        print(f"{color}{'─' * 70}{RESET}")

        for i, finding in enumerate(group, 1):
            icon = severity_icon(severity)
            category = finding.get("category", "").upper()
            title = finding.get("title", "")
            file_ = finding.get("file", "")
            line = finding.get("line", "?")
            explanation = finding.get("explanation", "")
            suggestion = finding.get("suggestion", "")
            cost = finding.get("estimated_cost_impact", "")

            print(f"\n  {color}{BOLD}[{icon}] {i}. {title}{RESET}")
            print(f"       Category : {category}")
            print(f"       Location : {file_}:{line}")
            if cost and cost != "$0/month":
                print(f"       Cost     : {cost}")
            print(f"\n       {explanation}")
            print(f"\n       Fix: {suggestion}")

    print(f"\n{BOLD}{'=' * 70}{RESET}\n")


# ---------------------------------------------------------------------------
# GitHub posting
# ---------------------------------------------------------------------------

SEVERITY_EMOJI = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🔵",
}


def build_pr_comment(findings: list[dict]) -> str:
    by_severity: dict[str, list[dict]] = {s: [] for s in SEVERITY_ORDER}
    for f in findings:
        sev = f.get("severity", "low").lower()
        by_severity.setdefault(sev, []).append(f)

    counts = {s: len(v) for s, v in by_severity.items() if v}
    total = sum(counts.values())
    summary_parts = [f"**{c} {s}**" for s, c in counts.items()]

    lines = [
        "## 🛡️ Terraform Security & Compliance Review",
        "",
        f"Found **{total} issue(s)** — {', '.join(summary_parts)}",
        "",
    ]

    for severity in SEVERITY_ORDER:
        group = by_severity.get(severity, [])
        if not group:
            continue

        emoji = SEVERITY_EMOJI.get(severity, "")
        lines.append(f"### {emoji} {severity.capitalize()} ({len(group)})")
        lines.append("")

        for finding in group:
            title = finding.get("title", "")
            file_ = finding.get("file", "")
            line = finding.get("line", "?")
            category = finding.get("category", "").upper()
            explanation = finding.get("explanation", "")
            suggestion = finding.get("suggestion", "")
            cost = finding.get("estimated_cost_impact", "")

            lines.append(f"#### {emoji} {title}")
            lines.append(f"- **Location:** `{file_}:{line}`")
            lines.append(f"- **Category:** {category}")
            if cost and cost != "$0/month":
                lines.append(f"- **Cost impact:** {cost}")
            lines.append("")
            lines.append(explanation)
            lines.append("")
            lines.append("**Suggestion:**")
            lines.append(f"```hcl\n{suggestion}\n```")
            lines.append("")

    lines.append("---")
    lines.append("*Posted by terraform-ai-guardian*")

    return "\n".join(lines)


def post_review_to_github(
    findings: list[dict],
    repo_name: str,
    pr_number: int,
    github_token: str,
) -> str:
    """Post findings as a single PR comment and return the comment URL."""
    gh = Github(auth=Auth.Token(github_token))
    repo = gh.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    body = build_pr_comment(findings)
    comment = pr.create_issue_comment(body)
    return comment.html_url


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI-powered Terraform PR reviewer")
    parser.add_argument("--repo", required=True, help='GitHub repo, e.g. "owner/repo"')
    parser.add_argument("--pr", required=True, type=int, help="PR number")
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

    print(f"Fetching .tf files from {args.repo} PR #{args.pr}...")
    tf_files = fetch_tf_files(args.repo, args.pr, github_token)

    if not tf_files:
        print("No Terraform (.tf) files changed in this PR.")
        return

    print(f"Found {len(tf_files)} .tf file(s): {', '.join(tf_files.keys())}")
    print("Sending to Claude for review...")

    findings = call_claude(tf_files, api_key)

    print_findings(findings, args.repo, args.pr)

    print("Posting review comment to GitHub...")
    comment_url = post_review_to_github(findings, args.repo, args.pr, github_token)
    print(f"Review posted: {comment_url}")


if __name__ == "__main__":
    main()
