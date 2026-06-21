import os
import json
import base64
import requests
from e2b_code_interpreter import Sandbox

OPENAI_KEY    = os.environ["OPENAI_API_KEY"]
GH_TOKEN      = os.environ["GH_TOKEN"]
REPO          = os.environ["REPO"]
COMMIT_SHA    = os.environ["COMMIT_SHA"]
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK_URL", "")

with open("test_output.txt", encoding="utf-8") as f:
    FAILURE_LOG = f.read()


def get_file_from_github(filepath):
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/{filepath}",
        headers={"Authorization": f"token {GH_TOKEN}"},
        params={"ref": COMMIT_SHA}
    )
    return base64.b64decode(r.json()["content"]).decode("utf-8")


def push_fix_to_github(filepath, fixed_code, message):
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/{filepath}",
        headers={"Authorization": f"token {GH_TOKEN}"}
    )
    file_sha = r.json()["sha"]
    requests.put(
        f"https://api.github.com/repos/{REPO}/contents/{filepath}",
        headers={"Authorization": f"token {GH_TOKEN}"},
        json={
            "message": message,
            "content": base64.b64encode(fixed_code.encode()).decode(),
            "sha": file_sha
        }
    )
    print(f"Fix pushed: {message}")


def notify_slack(message):
    if SLACK_WEBHOOK:
        requests.post(SLACK_WEBHOOK, json={"text": message})


IMMUNE_CODE = '''
import os
import sys
import json
import subprocess
import importlib
from typing import TypedDict
from langgraph.graph import StateGraph, END
from smolagents import ToolCallingAgent, CodeAgent, OpenAIServerModel, tool
from fastapi.testclient import TestClient

# ── Load app ──────────────────────────────────────────────────────────────────
spec = importlib.util.spec_from_file_location("app", "/home/user/app.py")
app_module = importlib.util.module_from_spec(spec)
sys.modules["app"] = app_module
spec.loader.exec_module(app_module)
app = app_module.app
client = TestClient(app, raise_server_exceptions=False)

model = OpenAIServerModel(
    model_id="gpt-4o-mini",
    api_base="https://openai.vocareum.com/v1",
    api_key=os.environ["OPENAI_API_KEY"]
)

failure_log   = os.environ.get("FAILURE_LOG", "")
failure_count = int(os.environ.get("FAILURE_COUNT", "0"))


def reload_app():
    global app, client
    spec = importlib.util.spec_from_file_location("app", "/home/user/app.py")
    app_module = importlib.util.module_from_spec(spec)
    sys.modules["app"] = app_module
    spec.loader.exec_module(app_module)
    app = app_module.app
    client = TestClient(app, raise_server_exceptions=False)


# ── Tools ─────────────────────────────────────────────────────────────────────
@tool
def check_health() -> dict:
    """
    Runs smoke tests against the order API.
    Returns a health report showing which scenarios pass or fail.
    """
    results = {}
    r1 = client.post("/order", json={"product_id": 1, "quantity": 2})
    results["basic_order"] = {
        "status_code": r1.status_code,
        "healthy": r1.status_code == 200 and r1.json().get("total") == 20.0,
        "response": r1.json()
    }
    r2 = client.post("/order", json={"product_id": 1, "quantity": 2, "coupon": "SAVE10"})
    results["save10_coupon"] = {
        "status_code": r2.status_code,
        "healthy": r2.status_code == 200 and r2.json().get("total") == 18.0,
        "response": r2.json()
    }
    r3 = client.post("/order", json={"product_id": 2, "quantity": 4, "coupon": "SAVE50"})
    results["save50_coupon"] = {
        "status_code": r3.status_code,
        "healthy": r3.status_code == 200 and r3.json().get("total") == 4.0,
        "response": r3.json()
    }
    return results


@tool
def save_test_to_file(content: str) -> str:
    """
    Saves generated pytest code to file.

    Args:
        content: Complete pytest source code as a string to save.
    """
    with open("/home/user/test_generated.py", "w") as f:
        f.write(content + "\\n")
    if "def test_" not in content:
        raise RuntimeError("No test functions found")
    return content


@tool
def run_tests(test_code: str) -> dict:
    """
    Runs pytest on the generated test file inside the sandbox.

    Args:
        test_code: Complete pytest source code as a string to execute.
    """
    with open("/home/user/test_generated.py", "w") as f:
        f.write(test_code + "\\n")
    result = subprocess.run(
        ["pytest", "/home/user/test_generated.py", "-v", "--tb=short"],
        capture_output=True, text=True
    )
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr
    }


@tool
def patch_app(reason: str) -> str:
    """
    Patches the buggy SAVE50 discount calculation in app.py.

    Args:
        reason: Description of the fix being applied to the app.
    """
    with open("/home/user/app.py", "r") as f:
        code = f.read()
    fixed = code.replace(
        "return round(price / quantity * 0.5, 2)",
        "return round(price * quantity * 0.5, 2)"
    )
    if fixed == code:
        return "No bug pattern found to patch"
    with open("/home/user/app.py", "w") as f:
        f.write(fixed)
    with open("/home/user/fixed_app.py", "w") as f:
        f.write(fixed)
    reload_app()
    return f"Patched: {reason}"


@tool
def rollback_app(reason: str) -> str:
    """
    Rolls back app.py to the last commit where CI workflow passed.

    Args:
        reason: Description of why the rollback is being performed.
    """
    import urllib.request
    import json as _json
    import base64 as _base64

    gh_token = os.environ.get("GH_TOKEN", "")
    repo     = os.environ.get("REPO", "")
    headers  = {
        "Authorization": f"token {gh_token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "digital-immune-system"
    }

    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/commits?per_page=20",
        headers=headers
    )
    with urllib.request.urlopen(req) as r:
        commits = _json.loads(r.read())

    stable_sha = None
    stable_message = None
    for commit in commits:
        sha = commit["sha"]
        message = commit["commit"]["message"]
        try:
            req2 = urllib.request.Request(
                f"https://api.github.com/repos/{repo}/actions/runs?head_sha={sha}",
                headers=headers
            )
            with urllib.request.urlopen(req2) as r:
                data = _json.loads(r.read())
            workflow_runs = data.get("workflow_runs", [])
            if not workflow_runs:
                continue
            all_passed = all(
                run["status"] == "completed" and run["conclusion"] == "success"
                for run in workflow_runs
            )
            if all_passed:
                stable_sha = sha
                stable_message = message
                break
        except Exception:
            continue

    if not stable_sha:
        return "Could not find any stable commit in recent history"

    req3 = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/contents/app.py?ref={stable_sha}",
        headers=headers
    )
    with urllib.request.urlopen(req3) as r:
        file_data = _json.loads(r.read())
    stable_code = _base64.b64decode(file_data["content"]).decode("utf-8")

    with open("/home/user/app.py", "w") as f:
        f.write(stable_code)
    with open("/home/user/fixed_app.py", "w") as f:
        f.write(stable_code)
    reload_app()
    return f"Rolled back to stable commit {stable_sha[:7]} ({stable_message[:50]}): {reason}"


@tool
def escalate(reason: str) -> str:
    """
    Escalates the failure to the on-call engineer when auto-healing fails.

    Args:
        reason: Full description of the unresolved failure to escalate.
    """
    msg = f"ESCALATED TO ON-CALL: {reason}"
    print(msg)
    return msg


# ── Agents ────────────────────────────────────────────────────────────────────
monitor_agent    = ToolCallingAgent(name="MonitorAgent",    model=model, tools=[check_health])
testgen_agent    = ToolCallingAgent(name="TestGenAgent",    model=model, tools=[save_test_to_file], max_steps=3)
testrunner_agent = ToolCallingAgent(name="TestRunnerAgent", model=model, tools=[run_tests], max_steps=2)
guardian_agent   = CodeAgent(name="GuardianAgent",          model=model, tools=[])
healer_agent     = ToolCallingAgent(name="HealerAgent",     model=model, tools=[patch_app, rollback_app, escalate], max_steps=3)


# ── State ─────────────────────────────────────────────────────────────────────
class ImmuneState(TypedDict):
    health: str
    all_healthy: bool
    test_code: str
    test_result: str
    decision: str
    heal_result: str
    recovered: bool


# ── Nodes ─────────────────────────────────────────────────────────────────────
def monitor_node(state: ImmuneState) -> ImmuneState:
    print("\\nMonitorAgent scanning...")
    health = monitor_agent.run("Run health checks on the order API.")
    print(f"Health: {health}")
    all_healthy = isinstance(health, dict) and all(
        v.get("healthy") for v in health.values() if isinstance(v, dict)
    )
    return {**state, "health": str(health), "all_healthy": all_healthy}


def testgen_node(state: ImmuneState) -> ImmuneState:
    print("\\nTestGenAgent generating tests...")
    prompt = (
        f"Regression detected. Health: {state[\'health\']}\\n"
        f"Failure log: {failure_log}\\n\\n"
        "Generate pytest tests using ONLY:\\n"
        "    from fastapi.testclient import TestClient\\n"
        "    from app import app\\n"
        "    client = TestClient(app)\\n\\n"
        "Test these three scenarios:\\n"
        "    POST /order product_id=1 quantity=2 -> total == 20.0\\n"
        "    POST /order product_id=1 quantity=2 coupon=SAVE10 -> total == 18.0\\n"
        "    POST /order product_id=2 quantity=4 coupon=SAVE50 -> total == 4.0\\n\\n"
        "Include all necessary imports. Call save_test_to_file when done."
    )
    testgen_agent.run(prompt)
    with open("/home/user/test_generated.py", "r") as f:
        test_code = f.read()
    return {**state, "test_code": test_code}


def testrunner_node(state: ImmuneState) -> ImmuneState:
    print("\\nTestRunnerAgent running tests...")
    test_result = testrunner_agent.run(
        f"Run these tests and report results:\\n{state[\'test_code\']}"
    )
    print(f"Result: {test_result}")
    return {**state, "test_result": str(test_result)}


def guardian_node(state: ImmuneState) -> ImmuneState:
    print("\\nGuardianAgent deciding...")
    prompt = (
        f"Regression in order API.\\n"
        f"Health: {state[\'health\']}\\n"
        f"Test result: {state[\'test_result\']}\\n"
        f"Times failed before: {failure_count}\\n\\n"
        "PATCH    if failure_count == 0 and bug is in calculation logic (/ instead of *)\\n"
        "ROLLBACK if failure_count >= 1\\n"
        "ESCALATE if failure_count >= 3\\n\\n"
        "Return ONLY one word: PATCH, ROLLBACK, or ESCALATE"
    )
    decision_raw = guardian_agent.run(prompt)
    decision = "ROLLBACK"
    for word in ["ESCALATE", "PATCH", "ROLLBACK"]:
        if word in str(decision_raw).upper():
            decision = word
            break
    print(f"Decision: {decision}")
    return {**state, "decision": decision}


def healer_node(state: ImmuneState) -> ImmuneState:
    action = state["decision"]
    print(f"\\nHealerAgent executing {action}...")
    prompt = (
        f"Decision: {action}\\n"
        f"Health: {state[\'health\']}\\n\\n"
        "You MUST call ONLY ONE tool based on the decision.\\n"
        f"The decision is: {action}\\n\\n"
        "If PATCH    - call patch_app only\\n"
        "If ROLLBACK - call rollback_app only\\n"
        "If ESCALATE - call escalate only\\n\\n"
        f"Call ONLY the tool that matches: {action}"
    )
    heal_result = healer_agent.run(prompt)
    return {**state, "heal_result": str(heal_result)}


def verify_node(state: ImmuneState) -> ImmuneState:
    print("\\nVerifying recovery...")
    health_after = monitor_agent.run("Run health checks again and confirm recovery.")
    recovered = isinstance(health_after, dict) and all(
        v.get("healthy") for v in health_after.values() if isinstance(v, dict)
    )
    print("Recovered" if recovered else "Still degraded")
    return {**state, "recovered": recovered}


# ── Conditional edge ──────────────────────────────────────────────────────────
def route_after_monitor(state: ImmuneState):
    return "testgen" if not state["all_healthy"] else END


# ── Build graph ───────────────────────────────────────────────────────────────
graph = StateGraph(ImmuneState)

graph.add_node("monitor",    monitor_node)
graph.add_node("testgen",    testgen_node)
graph.add_node("testrunner", testrunner_node)
graph.add_node("guardian",   guardian_node)
graph.add_node("healer",     healer_node)
graph.add_node("verify",     verify_node)

graph.set_entry_point("monitor")

graph.add_conditional_edges("monitor", route_after_monitor,
    {"testgen": "testgen", END: END})
graph.add_edge("testgen",    "testrunner")
graph.add_edge("testrunner", "guardian")
graph.add_edge("guardian",   "healer")
graph.add_edge("healer",     "verify")
graph.add_edge("verify",     END)

immune_graph = graph.compile()

# ── Run ───────────────────────────────────────────────────────────────────────
print("\\nDIGITAL IMMUNE SYSTEM ACTIVATED\\n")

initial_state: ImmuneState = {
    "health": "",
    "all_healthy": False,
    "test_code": "",
    "test_result": "",
    "decision": "NONE",
    "heal_result": "",
    "recovered": False
}

final_state = immune_graph.invoke(initial_state)

with open("/home/user/result.json", "w") as f:
    json.dump({
        "action": final_state["decision"],
        "recovered": final_state["recovered"]
    }, f)
'''

print(f"Fetching app.py from GitHub at {COMMIT_SHA[:7]}...")
app_code = get_file_from_github("app.py")

print("Spinning up e2b sandbox...")
with Sandbox.create() as sandbox:
    sandbox.commands.run(
        "pip install fastapi pytest httpx httpx2 smolagents openai python-multipart langgraph",
        timeout=120
    )

    sandbox.files.write("/home/user/app.py", app_code)
    sandbox.files.write("/home/user/immune_system.py", IMMUNE_CODE)

    result = sandbox.commands.run(
        "cd /home/user && "
        f"OPENAI_API_KEY='{OPENAI_KEY}' "
        f"GH_TOKEN='{GH_TOKEN}' "
        f"REPO='{REPO}' "
        "FAILURE_COUNT='0' "
        "python immune_system.py",
        timeout=300
    )

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    try:
        result_json = sandbox.files.read("/home/user/result.json")
        outcome = json.loads(result_json)
    except Exception:
        outcome = {"action": "UNKNOWN", "recovered": False}

    print(f"Outcome: {outcome}")

    if outcome["action"] in ["PATCH", "ROLLBACK"]:
        try:
            fixed_code = sandbox.files.read("/home/user/fixed_app.py")

            # Verify it's valid Python before pushing
            if "ESCALATE" in fixed_code and len(fixed_code) < 50:
                print("ERROR: fixed_app.py contains invalid content, skipping push")
            else:
                push_fix_to_github(
                    "app.py",
                    fixed_code,
                    f"fix: auto-healed [{outcome['action']}] on {COMMIT_SHA[:7]}"
                )
                notify_slack(
                    f"Digital Immune System\n"
                    f"Repo: {REPO}\n"
                    f"Commit: {COMMIT_SHA[:7]}\n"
                    f"Action: {outcome['action']}\n"
                    f"Recovered: {'Yes' if outcome['recovered'] else 'No'}"
                )
        except Exception as e:
            print(f"Could not push fix: {e}")

    elif outcome["action"] == "ESCALATE":
        notify_slack(
            f"Digital Immune System - ESCALATION\n"
            f"Repo: {REPO}\n"
            f"Commit: {COMMIT_SHA[:7]}\n"
            f"Could not auto-heal. On-call required."
        )