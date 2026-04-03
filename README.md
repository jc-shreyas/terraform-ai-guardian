# DevOps AI Agents

AI-powered agents that review your Terraform PRs for security/compliance issues and debug your CI/CD pipeline failures.

## What's in this repo

### `/infra` — Terraform Infrastructure
Sample AWS infrastructure (VPC, S3, IAM, RDS, ElastiCache) used as the target for the PR reviewer agent. Contains intentional security issues for demonstration.

### `/agent-pr-reviewer` — Terraform PR Review Agent
A Python agent (using the Anthropic Claude API directly) that reviews Terraform pull requests for:
- **Security**: Public access, missing encryption, overly permissive IAM, hardcoded credentials
- **Reliability**: No multi-AZ, missing backups, no deletion protection
- **Cost**: Oversized instances, unbounded auto-scaling, missing lifecycle rules
- **Best practices**: No remote state, missing tags, deprecated patterns

### `/agent-cicd-debugger` — CI/CD Pipeline Debugger Agent
A Python agent (using the Anthropic Claude API directly) that diagnoses failed GitHub Actions runs:
- Parses noisy CI logs to extract the actual error
- Identifies the failing step and related configuration
- Performs root cause analysis using Claude
- Generates concrete fix suggestions with code changes

## Tech Stack

- **Python** + **Anthropic Claude API** (via `anthropic` SDK) + **PyGithub**

## Prerequisites

- Python 3.11+
- Anthropic API key
- GitHub Personal Access Token
- Claude Code CLI (for development)

## Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/devops-ai-agents.git
cd devops-ai-agents

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Install dependencies
pip install -e ".[all]"

# Run PR reviewer on a specific PR
python -m agent_pr_reviewer.main --repo YOUR_USERNAME/devops-ai-agents --pr 1

# Run CI/CD debugger on a failed workflow run
python -m agent_cicd_debugger.main --repo YOUR_USERNAME/devops-ai-agents --run-id 12345
```

## Architecture

See the full build plan and architecture diagrams in the project documentation.

## License

MIT
