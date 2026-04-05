# 🛡️ Terraform AI Guardian

**AI-powered agents that automatically review your Terraform PRs for security & compliance issues and diagnose CI/CD pipeline failures — fully integrated with GitHub Actions.**

Open a PR with Terraform changes → get an instant security review with fix suggestions. Pipeline breaks → get an automated root cause diagnosis with concrete fixes. No manual steps.

---

## What It Does

This repo contains **two AI agents** that work together to guard your infrastructure code:

### Agent 1: Terraform PR Security Reviewer

Automatically reviews every Pull Request that touches Terraform files, scanning for issues across four categories:

**🔴 Security** — Public S3 buckets, overly permissive IAM policies (`Action: *`), hardcoded credentials in user data, SSH open to `0.0.0.0/0`, wildcard principals on SNS/SQS policies, missing encryption at rest

**💰 Cost** — Oversized instances (`t3.2xlarge` when `t3.small` suffices → ~$200/month savings), 500GB root volumes, unbounded auto-scaling with no alerts, missing lifecycle rules on S3

**🟡 Reliability** — No multi-AZ deployment, single-day backup retention, missing deletion protection, no dead letter queues, single-node Redis without replication

**🔵 Best Practices** — No remote state backend, missing resource tags, hardcoded values that should be variables, deprecated patterns

Each finding includes the exact file and line number, a clear explanation of why it matters, and a **concrete Terraform code suggestion** to fix it.

### Agent 2: CI/CD Pipeline Debugger

Automatically triggers when a GitHub Actions pipeline fails. It:

1. **Fetches** the full workflow run logs from GitHub API
2. **Parses** through noisy CI output to extract the actual error (stripping ANSI codes, timestamps, and noise)
3. **Diagnoses** the root cause using Claude with full context (workflow YAML + error logs + related files)
4. **Posts** a structured diagnosis directly to the PR with root cause, category, fix steps, and prevention advice
5. **Clears** the diagnosis automatically when the pipeline recovers (updates to "✅ Pipeline is now passing")

**Error categories:** `config_error` · `dependency_issue` · `credentials` · `code_error` · `infra_issue` · `flaky_test`

---

## How It Works

```
Developer opens PR with .tf changes
    │
    ├─── PR Reviewer (Agent 1) triggers automatically
    │       │
    │       ├── Fetches all changed .tf files via GitHub API
    │       ├── Sends full file content to Claude with security-focused system prompt
    │       ├── Claude returns structured JSON findings with severity, category, fix
    │       └── Posts formatted review comment to the PR (updates existing, never duplicates)
    │
    └─── Terraform Plan (CI) triggers automatically
            │
            ├── terraform init → validate → fmt check
            │
            ├── ✅ Passes → Pipeline Monitor confirms "pipeline is now passing"
            │
            └── ❌ Fails → Pipeline Debugger (Agent 2) triggers automatically
                    │
                    ├── Downloads workflow run logs from GitHub API
                    ├── Extracts error context (failed job, step, error message)
                    ├── Sends to Claude with workflow YAML for root cause analysis
                    └── Posts diagnosis to PR (root cause, fix, prevention)
```

**Key design decisions:**
- Each agent owns **one comment** per PR — updates on subsequent pushes, never creates duplicates
- The debugger **only posts when there's a failure** — stays silent on passing pipelines
- Old diagnosis comments are **automatically cleared** when the issue is resolved
- **Fork protection** — workflows only trigger for PRs from within the repo, not from forks (prevents API credit abuse)
- **Concurrency limits** — rapid pushes to the same PR cancel previous runs instead of stacking

---

## Live Demo

The best way to see this in action is to clone the repo, open a PR with a `.tf` file change, and watch the agents work. Every existing PR in this repo has real review comments from the agents.

### Example: PR Security Review

The agent catches a wildcard SNS policy, missing encryption, and no dead letter queue — with Terraform code fixes for each:

```
🛡️ Terraform Security & Compliance Review

Found 5 issue(s) — 1 critical, 2 medium, 2 low

🔴 Critical (1)
  SNS topic policy allows unrestricted public access
  Location: infra/sns.tf:11
  The policy uses Principal = "*" which allows anyone to publish messages...

  Suggestion:
    Principal = {
      AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
    }
```

### Example: Pipeline Failure Diagnosis

The agent diagnoses a Terraform validation failure with three distinct errors, exact fix commands, and prevention advice:

```
CI/CD Failure Diagnosis

Workflow: Terraform Plan | Branch: feature/add-lambda
Failed job: terraform | Failed step: Terraform Validate
Category: config_error

Root Cause:
  Three errors in broken.tf:
  1. 'enable_acceleration' is not a valid aws_s3_bucket argument
  2. depends_on references undeclared aws_iam_role.nonexistent_role
  3. aws_security_group_rule missing required security_group_id

Fix:
  1. Use aws_s3_bucket_accelerate_configuration resource instead
  2. Declare the IAM role or remove the depends_on
  3. Add security_group_id = aws_security_group.example.id

Prevention:
  Add terraform validate to pre-commit hooks
  Use IDE extensions for real-time syntax validation
```

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Python 3.11 | Agent logic and GitHub integration |
| AI | Claude API (Sonnet) | Security analysis and root cause diagnosis |
| GitHub | PyGithub + REST API | Fetch PRs, diffs, logs; post review comments |
| CI/CD | GitHub Actions | Automated triggers for both agents |
| IaC | Terraform | Target infrastructure code being reviewed |
| Dev Tool | Claude Code CLI | Used to build the agents themselves |

**No LangGraph, no LangChain, no heavyweight frameworks.** Both agents are clean Python scripts using the Anthropic SDK directly. The architecture is intentionally simple — each agent is a linear pipeline that's easy to understand, debug, and extend.

---

## Repository Structure

```
terraform-ai-guardian/
├── agent-pr-reviewer/          # Agent 1: Terraform PR Security Reviewer
│   └── main.py                 #   Fetch diff → Claude review → post to PR
│
├── agent-cicd-debugger/        # Agent 2: CI/CD Pipeline Debugger
│   └── main.py                 #   Fetch logs → parse error → Claude diagnosis → post to PR
│
├── infra/                      # Sample Terraform infrastructure
│   ├── main.tf                 #   VPC, subnets, security groups
│   ├── s3.tf                   #   S3 buckets (with intentional issues)
│   ├── iam.tf                  #   IAM roles and policies
│   ├── rds.tf                  #   RDS and ElastiCache
│   ├── sns.tf                  #   SNS and SQS
│   ├── variables.tf            #   Input variables
│   └── outputs.tf              #   Output values
│
├── .github/workflows/
│   ├── pr-review.yml           #   Triggers Agent 1 on PR with .tf changes
│   ├── terraform-plan.yml      #   Runs terraform validate + fmt check
│   └── debug-on-failure.yml    #   Triggers Agent 2 when plan fails
│
├── shared/                     # Shared utilities and prompt templates
├── requirements.txt
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))
- GitHub Personal Access Token (with `contents:read` and `pull-requests:write`)

### Run Locally

```bash
# Clone the repo
git clone https://github.com/jc-shreyas/terraform-ai-guardian.git
cd terraform-ai-guardian

# Set up Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY and GITHUB_TOKEN

# Run PR reviewer against a specific PR
python agent-pr-reviewer/main.py --repo jc-shreyas/terraform-ai-guardian --pr 7

# Run CI/CD debugger against a failed workflow run
python agent-cicd-debugger/main.py --repo jc-shreyas/terraform-ai-guardian --run-id <RUN_ID>
```

### Enable Automated Workflows

1. Add `ANTHROPIC_API_KEY` as a repository secret (Settings → Secrets → Actions)
2. Open a PR that modifies any `.tf` file under `infra/`
3. Watch both agents trigger automatically

---

## Design Decisions

**Why plain Python instead of LangGraph/LangChain?**
Both agents are linear pipelines — fetch → process → analyze → post. There are no cycles, no complex branching, no human-in-the-loop checkpoints that would justify an orchestration framework. Adding LangGraph would increase complexity without adding value. The agents are ~300 lines each, easy to read, and easy to extend.

**Why Claude Sonnet instead of GPT-4 or open-source models?**
Claude Sonnet offers the best balance of code understanding, structured output reliability, and cost for this use case. Each review costs ~$0.02–0.05. The tool-use and JSON output capabilities make it reliable for structured findings.

**Why post to PRs instead of Slack/email?**
Developers are already looking at the PR. The review and diagnosis appear exactly where the developer needs them, in context. No tab switching, no notification fatigue.

**Why update comments instead of creating new ones?**
Multiple pushes to the same PR would create a wall of duplicate comments. Each agent owns one comment that gets updated — the developer always sees the latest review.

---

## What I Learned Building This

- **Prompt engineering is 60% of agent quality.** The system prompts for security review and root cause analysis went through many iterations. Being specific about output format (JSON with exact fields) dramatically improved reliability.
- **GitHub's log API has quirks.** The log download endpoint redirects to a CDN URL, and forwarding the auth header to the CDN causes a 403. The fix is to follow redirects manually and drop auth headers on the second request.
- **AI agents don't need frameworks.** For linear pipelines, plain Python with the Anthropic SDK is cleaner, faster to debug, and easier to understand than any agent framework.
- **I used Claude Code (an AI agent) to build these AI agents.** The meta-loop — using an agentic tool to build agentic tools — was the fastest development approach I've experienced.

---

## Future Enhancements

- Add cost estimation for infrastructure changes using Infracost
- Support for Terraform modules and cross-file dependency analysis
- Integrate static analysis tools (tfsec, checkov) alongside AI review
- Add Slack/Teams notifications for critical findings
- Support for Pulumi and CloudFormation

---

## License

MIT
