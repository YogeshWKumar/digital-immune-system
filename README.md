🧬 Digital Immune System
> A self-healing CI pipeline that detects regressions, generates targeted tests, and autonomously applies fixes — powered by smolagents, LangGraph, e2b, and GitHub Actions.
![CI](https://github.com/YogeshWKumar/digital-immune-system/actions/workflows/ci.yml/badge.svg)
---
Overview
When a developer pushes a breaking change to `main`, instead of simply failing the build, the Digital Immune System activates a six-agent LangGraph pipeline running inside an isolated e2b cloud sandbox. It diagnoses the regression, generates targeted pytest tests, and autonomously applies one of three recovery strategies based on persistent failure history:
Strategy	Trigger	Action
PATCH	`failure_count == 0`	LLM rewrites the broken file
ROLLBACK	`failure_count >= 1`	Restores last verified stable commit
ESCALATE	`failure_count >= 3`	Pages on-call engineer via Slack
Every healing cycle is fully observable through LangSmith, which captures node-level traces for the entire pipeline — showing input state, output state, and latency for each of the seven nodes.
---
Workflow
```
Developer pushes buggy code
         ↓
GitHub Actions runs pytest → tests fail
         ↓
Digital Immune System activates
         ↓
6 agents diagnose → decide → heal
         ↓
Fix pushed back to main automatically
         ↓
Slack notification → #digital-immune-system
```
---
Architecture
```
┌─────────────────────────────────────────────────┐
│              Developer layer                    │
│   app.py · GitHub repo · test_baseline.py       │
└─────────────────────┬───────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│         CI + immune system layer                │
│                                                 │
│  GitHub Actions (ci.yml)                        │
│       ↓ on test failure                         │
│  immune_trigger.py                              │
│       ↓ spins sandbox                           │
│  ┌──────────────────────────────────────────┐   │
│  │         e2b cloud sandbox                │   │
│  │                                          │   │
│  │        LangGraph StateGraph              │   │
│  │                                          │   │
│  │  Monitor → TestGen → TestRunner          │   │
│  │     → Guardian → Healer → Verify         │   │
│  │                  ↓                       │   │
│  │   patch_app · rollback_app · escalate    │   │
│  │                  ↓                       │   │
│  │         result.json + fixed_app.py       │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────┬───────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│         Persistence + notification layer        │
│   Fix commit · immune_memory.json · Slack       │
└─────────────────────────────────────────────────┘
```
---
Tech stack
Layer	- Technology
CI orchestration - GitHub Actions
Agent framework	- smolagents
Orchestration - LangGraph StateGraph
Sandbox - e2b cloud sandbox
LLM - gpt-4o-mini (Vocareum proxy)
Application - FastAPI + pytest
Notifications - Slack incoming webhook
Memory - GitHub Contents API
Observability - LangSmith
---
Project structure
```
digital-immune-system/
├── app.py                  # Target FastAPI service
├── test_baseline.py        # Baseline regression tests
├── immune_trigger.py       # CI runner orchestrator
├── immune_memory.json      # Persistent failure memory
└── .github/
    └── workflows/
        └── ci.yml          # GitHub Actions workflow
```
---
How it works
1. CI detects a failure
Every push to `main` runs `pytest test_baseline.py`. On failure, the exit code triggers `immune_trigger.py`.
2. immune_trigger.py orchestrates
Runs on the GitHub Actions runner. Reads `immune_memory.json` from GitHub to get the current `failure_count`, fetches `app.py`, spins up an e2b sandbox, and injects `immune_system.py` with all required environment variables.
3. LangGraph pipeline runs inside the sandbox
Seven nodes execute in sequence:
```
monitor_node → testgen_node → testrunner_node → guardian_node
                                                      ↓
                                              healer_node
                                                      ↓
                                              verify_node → retest_node → END
```
MonitorAgent — runs live health checks against the API
TestGenAgent — generates pytest tests from app source + CI failure log
TestRunnerAgent — confirms the failure in the sandbox
GuardianAgent — reads `failure_count` and decides PATCH / ROLLBACK / ESCALATE
HealerAgent — executes exactly one recovery tool
VerifyAgent — re-runs health checks to confirm recovery
RetestAgent — re-runs pytest after healing
4. Fix pushed back to GitHub
`immune_trigger.py` reads `result.json` and `fixed_app.py` from the sandbox, pushes a fix commit with message `fix: auto-healed [PATCH/ROLLBACK] on <sha>`, updates `immune_memory.json`, and fires a Slack notification.
5. CI re-runs on the fix commit
The fix commit triggers CI again. Tests pass. Build is green.
---
Memory system
`immune_memory.json` tracks failure history across CI runs:
```json
{
  "failure_count": 0,
  "last_failure_sha": "...",
  "last_healed_sha": "...",
  "last_healed_at": "2026-06-26T09:05:24Z",
  "history": [
    {
      "sha": "...",
      "action": "PATCH",
      "healed": true,
      "timestamp": "..."
    }
  ]
}
```
`failure_count` drives the Guardian's decision. It resets to `0` on a successful heal and increments on failure. Changes to this file are excluded from CI triggers via `paths-ignore` to prevent unnecessary loops.
---
Setup
Prerequisites
Python 3.11+
GitHub repository with Actions enabled
e2b account — e2b.dev
OpenAI API key (Vocareum proxy or direct)
Slack workspace with incoming webhook
LangSmith account — smith.langchain.com
1. Clone the repo
```bash
git clone https://github.com/YogeshWKumar/digital-immune-system
cd digital-immune-system
```
2. Install dependencies
```bash
pip install fastapi httpx pytest smolagents openai e2b-code-interpreter requests langgraph langsmith
```
3. Add GitHub Secrets
Go to repo → Settings → Secrets and variables → Actions:
Secret	Description
`OPENAI_API_KEY`	Vocareum proxy key for gpt-4o-mini
`GH_TOKEN`	Personal access token with repo read/write
`E2B_API_KEY`	e2b cloud sandbox API key
`SLACK_WEBHOOK_URL`	Slack incoming webhook URL
`LANGSMITH_API_KEY`	LangSmith Personal Access Token
`LANGSMITH_TRACING`	true
`LANGSMITH_ENDPOINT`	https://api.smith.langchain.com
`LANGSMITH_PROJECT`	digital-immune-system
4. Configure ci.yml
The workflow is already configured in `.github/workflows/ci.yml`. Verify the env block includes all secrets:
```yaml
- name: Trigger Digital Immune System
  if: steps.run_tests.outputs.exit_code != '0'
  env:
    OPENAI_API_KEY:      ${{ secrets.OPENAI_API_KEY }}
    GH_TOKEN:            ${{ secrets.GH_TOKEN }}
    E2B_API_KEY:         ${{ secrets.E2B_API_KEY }}
    SLACK_WEBHOOK_URL:   ${{ secrets.SLACK_WEBHOOK_URL }}
    REPO:                ${{ github.repository }}
    COMMIT_SHA:          ${{ github.sha }}
    LANGSMITH_TRACING:   ${{ secrets.LANGSMITH_TRACING }}
    LANGSMITH_ENDPOINT:  ${{ secrets.LANGSMITH_ENDPOINT }}
    LANGSMITH_API_KEY:   ${{ secrets.LANGSMITH_API_KEY }}
    LANGSMITH_PROJECT:   ${{ secrets.LANGSMITH_PROJECT }}  
  run: python immune_trigger.py
```
5. Create LangSmith project
Go to smith.langchain.com → Tracing → + Project → name it `digital-immune-system`.
---
Testing the system
Trigger a PATCH
Introduce a bug in discount logic for SAVE10 coupon in app.py
  for example change (price * quantity * 0.9, 2) to (price + quantity / 0.9, 2)
```bash
git add app.py
git commit -m "test: introduce bug"
git push
```
Trigger a ROLLBACK
Set `failure_count` to 1 in immune_memory.json first
```bash
git add immune_memory.json && git commit -m "set failure_count=1" && git push
```
Introduce a bug in discount logic for SAVE10 coupon in app.py
  for example change (price * quantity * 0.9, 2) to (price + quantity / 0.9, 2)
```bash
git add app.py && git commit -m "test: trigger rollback" && git push
```
Trigger an ESCALATE
Set `failure_count` to 3 in immune_memory.json first
```bash
git add immune_memory.json && git commit -m "set failure_count=3" && git push
```
Introduce a bug in discount logic for SAVE10 coupon in app.py
  for example change (price * quantity * 0.9, 2) to (price + quantity / 0.9, 2)
```bash
git add app.py && git commit -m "test: trigger rollback" && git push
```
Reset memory after testing
Reset `failure_count` to 0 in immune_memory.json after testing
```bash
git add immune_memory.json && git commit -m "reset failure_count" && git push
```
---
Observability
Traces appear in LangSmith automatically after each CI run. Every node in the pipeline is captured as a child span:
```
LangGraph (46.86s)
├── monitor     5.41s  — health check results
├── testgen     6.59s  — generated test code
├── testrunner  8.72s  — pytest output
├── guardian    2.98s  — PATCH / ROLLBACK / ESCALATE decision
├── healer      9.48s  — LLM prompt + fixed code
├── verify      4.23s  — recovery confirmation
└── retest      9.42s  — final test results
```
Go to smith.langchain.com → `digital-immune-system` project to view traces.
---
Slack notifications
On patch:
```
✅ Digital Immune System — Auto-Healed
   Repo:       YogeshWKumar/digital-immune-system
   Commit:     295b622
   Action:     PATCH
   Recovered:  Yes ✅
   Fix commit: fix: auto-healed [PATCH] on 295b622
```
On rollback:
```
✅ Digital Immune System — Auto-Healed
   Repo:       YogeshWKumar/digital-immune-system
   Commit:     a7dfce4
   Action:     ROLLBACK
   Recovered:  Yes ✅
   Fix commit: fix: auto-healed [ROLLBACK] triggered by a7dfce4 restored to 171488b
```
On escalation:
```
🚨 Digital Immune System — ESCALATION
   Repo:           YogeshWKumar/digital-immune-system
   Commit:         6e80e76
   Failure count: 4
   Reason: Auto-healing failed after 3 attempts
   Action required: Manual intervention needed
   CI run: https://github.com/YogeshWKumar/digital-immune-system/actions
```
---
Performance (20 runs — Jun 22–26, 2026)
Metric	Value
Total healing cycles	20
Autonomous recovery rate	75%
PATCH success rate	71% (10/14)
ROLLBACK success rate	100% (4/4)
Average healing time	~47 seconds
Escalations	3
---
License
MIT
---
Built by Yogesh W Kumar · June 2026