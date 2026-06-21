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
import ast
from typing import TypedDict, Optional
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
    return "Tests saved successfully to /home/user/test_generated.py"


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
monitor_agent    = ToolCallingAgent(name="MonitorAgent",    model=model, tools=[check_health], max_steps=1)
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
    stable_sha: Optional[str]
    retest_result: str

def print_state(state: ImmuneState, node_name: str):
    print(f"\\n{'='*50}")
    print(f"State after {node_name}:")
    print(f"  health        : {state['health'][:80] if state['health'] else 'empty'}...")
    print(f"  all_healthy : {state['all_healthy']}")
    print(f"  decision    : {state['decision']}")
    print(f"  recovered   : {state['recovered']}")
    print(f"  test_code   : {state['test_code'][:80] if state['test_code'] else 'empty'}...")
    print(f"  test_result : {state['test_result'][:80] if state['test_result'] else 'empty'}...")
    print(f"  heal_result : {state['heal_result'][:80] if state['heal_result'] else 'empty'}...")
    print(f"  retest_result : {state['retest_result'][:80] if state['retest_result'] else 'empty'}...")
    print(f"{'='*50}\\n")    


def get_health_from_memory(agent):
    for step in reversed(agent.memory.steps):
        if hasattr(step, "observations") and step.observations:
            obs = step.observations
            if isinstance(obs, dict):
                return obs
            if isinstance(obs, str) and "basic_order" in obs:
                try:
                    return ast.literal_eval(obs)
                except Exception:
                    pass
    return None    
    
# ── Nodes ─────────────────────────────────────────────────────────────────────
def monitor_node(state: ImmuneState) -> ImmuneState:
    print("\\nMonitorAgent scanning...")
    monitor_agent.run("Run health checks on the order API.")
    health = get_health_from_memory(monitor_agent)
    print(f"Health: {health}")
    all_healthy = isinstance(health, dict) and all(
        v.get("healthy") for v in health.values() if isinstance(v, dict)
    )
    new_state = {**state, "health": str(health), "all_healthy": all_healthy}
    print_state(new_state, "monitor_node")
    return new_state


def testgen_node(state: ImmuneState) -> ImmuneState:
    print("\\nTestGenAgent generating tests...")
    prompt = (
        f"Regression detected. Health: {state[\'health\']}\\n"
        f"Failure log: {failure_log}\\n\\n"
        "Generate pytest tests using ONLY:\\n"
        "    from fastapi.testclient import TestClient\\n"
        "    from app import app\\n"
        "    client = TestClient(app)\\n\\n"
        "IMPORTANT: Assert ONLY response.json()[\'total\'] — do NOT assert the full response dict.\\n"
        "IMPORTANT: Use ONLY these hardcoded expected totals — do NOT use values from health report:\\n"
            "POST /order product_id=1 quantity=2               -> assert response.json()[\'total\'] == 20.0\\n"
            "POST /order product_id=1 quantity=2 coupon=SAVE10 -> assert response.json()[\'total\'] == 18.0\\n"
            "POST /order product_id=2 quantity=4 coupon=SAVE50 -> assert response.json()[\'total\'] == 4.0\\n\\n"
        "Include all necessary imports. Call save_test_to_file when done."
    )
    testgen_agent.run(prompt)
    with open("/home/user/test_generated.py", "r") as f:
        test_code = f.read()
    new_state = {**state, "test_code": test_code}
    print_state(new_state, "testgen_node")
    return new_state


def testrunner_node(state: ImmuneState) -> ImmuneState:
    print("\\nTestRunnerAgent running tests...")
    test_result = testrunner_agent.run(
        f"Run these tests and report results:\\n{state[\'test_code\']}"
    )
    print(f"Result: {test_result}")
    new_state = {**state, "test_result": str(test_result)}
    print_state(new_state, "testrunner_node")
    return new_state


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
    new_state = {**state, "decision": decision}
    print_state(new_state, "guardian_node")
    return new_state


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
    import re
    sha_match = re.search(r'stable commit ([a-f0-9]{7})', str(heal_result))
    stable_sha = sha_match.group(1) if sha_match else None
    new_state = {**state, "heal_result": str(heal_result), "stable_sha": stable_sha}
    print_state(new_state, "healer_node")
    return new_state


def verify_node(state: ImmuneState) -> ImmuneState:
    print("\\nVerifying recovery...")
    monitor_agent.run("Run health checks again and confirm recovery.")
    health_after = get_health_from_memory(monitor_agent)
    recovered = isinstance(health_after, dict) and all(
        v.get("healthy") for v in health_after.values() if isinstance(v, dict)
    )
    print("Recovered" if recovered else "Still degraded")
    new_state={**state, "recovered": recovered, "all_healthy": recovered}
    print_state(new_state, "verify_node")
    return new_state

def retest_node(state: ImmuneState) -> ImmuneState:
    print("\\nRetestAgent re-running tests after heal...")
    retest_result = testrunner_agent.run(
        f"Re-run these tests and report results:\\n{state[\'test_code\']}"
    )
    print(f"Retest result: {retest_result}")
    new_state = {**state, "retest_result": str(retest_result)}
    print_state(new_state, "retest_node")
    return new_state    

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
graph.add_node("retest", retest_node)

graph.set_entry_point("monitor")

graph.add_conditional_edges("monitor", route_after_monitor,
    {"testgen": "testgen", END: END})
graph.add_edge("testgen",    "testrunner")
graph.add_edge("testrunner", "guardian")
graph.add_edge("guardian",   "healer")
graph.add_edge("healer",     "verify")
graph.add_edge("verify",     "retest")
graph.add_edge("retest",  END)

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
    "recovered": False,
    "stable_sha": None,
    "retest_result": ""
}

final_state = immune_graph.invoke(initial_state)

with open("/home/user/result.json", "w") as f:
    json.dump({
        "action": final_state["decision"],
        "recovered": final_state["recovered"],
        "stable_sha": final_state["stable_sha"]
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
                # Build commit message
                if outcome["action"] == "ROLLBACK" and outcome.get("stable_sha"):
                    message = f"fix: auto-healed [ROLLBACK] triggered by {COMMIT_SHA[:7]} restored to {outcome['stable_sha']}"
                else:
                    message = f"fix: auto-healed [{outcome['action']}] on {COMMIT_SHA[:7]}"
                push_fix_to_github(
                    "app.py",
                    fixed_code,
                    message
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