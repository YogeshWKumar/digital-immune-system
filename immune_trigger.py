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


IMMUNE_CODE = r"""
import os
import sys
import json
import subprocess
from smolagents import ToolCallingAgent, CodeAgent, OpenAIServerModel, tool
from fastapi.testclient import TestClient
import importlib.util

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


@tool
def check_health() -> dict:
    'Runs smoke tests against the order API.'
    results = {}
    r1 = client.post("/order", json={"product_id": 1, "quantity": 2})
    results["basic_order"] = {
        "status_code": r1.status_code,
        "healthy": r1.status_code == 200 and r1.json().get("total") == 20.0,
        "response": r1.json()
    }
    r2 = client.post("/order", json={
        "product_id": 2, "quantity": 4, "coupon": "SAVE50"
    })
    results["save50_coupon"] = {
        "status_code": r2.status_code,
        "healthy": r2.status_code == 200 and r2.json().get("total") == 4.0,
        "response": r2.json(),
        "expected_total": 4.0
    }
    return results


@tool
def save_test_to_file(content: str) -> str:
    'Saves generated pytest code. Returns code for runner.'
    with open("/home/user/test_generated.py", "w") as f:
        f.write(content + "\n")
    if "def test_" not in content:
        raise RuntimeError("No test functions found")
    return content


@tool
def run_tests(test_code: str) -> dict:
    'Runs pytest on generated tests inside sandbox.'
    with open("/home/user/test_generated.py", "w") as f:
        f.write(test_code + "\n")
    result = subprocess.run(
        ["pytest", "/home/user/test_generated.py", "-v", "--tb=short"],
        capture_output=True,
        text=True
    )
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr
    }


@tool
def patch_app(reason: str) -> str:
    'Patches buggy calculation in app.py.'
    with open("/home/user/app.py", "r") as f:
        code = f.read()
    code = code.replace(
        "return round(price / quantity * 0.5, 2)",
        "return round(price * quantity * 0.5, 2)"
    )
    with open("/home/user/app.py", "w") as f:
        f.write(code)
    with open("/home/user/fixed_app.py", "w") as f:
        f.write(code)
    return f"Patched: {reason}"


@tool
def rollback_app(reason: str) -> str:
    'Disables breaking feature in app.py.'
    with open("/home/user/app.py", "r") as f:
        code = f.read()
    code = code.replace(
        "DISCOUNT_ENGINE_ENABLED = True",
        "DISCOUNT_ENGINE_ENABLED = False"
    )
    with open("/home/user/app.py", "w") as f:
        f.write(code)
    with open("/home/user/fixed_app.py", "w") as f:
        f.write(code)
    return f"Rolled back: {reason}"


@tool
def escalate(reason: str) -> str:
    'Escalates to on-call engineer.'
    print(f"ESCALATED: {reason}")
    with open("/home/user/fixed_app.py", "w") as f:
        f.write("ESCALATE")
    return f"Escalated: {reason}"


monitor_agent    = ToolCallingAgent(name="MonitorAgent",    model=model, tools=[check_health])
testgen_agent    = ToolCallingAgent(name="TestGenAgent",    model=model, tools=[save_test_to_file], max_steps=3)
testrunner_agent = ToolCallingAgent(name="TestRunnerAgent", model=model, tools=[run_tests], max_steps=2)
guardian_agent   = CodeAgent(name="GuardianAgent", model=model, tools=[])
healer_agent     = ToolCallingAgent(name="HealerAgent",     model=model, tools=[patch_app, rollback_app, escalate], max_steps=3)

failure_log   = os.environ.get("FAILURE_LOG", "")
failure_count = int(os.environ.get("FAILURE_COUNT", "0"))

print("\nDIGITAL IMMUNE SYSTEM ACTIVATED\n")

print("MonitorAgent scanning...")
health = monitor_agent.run("Run health checks on the order API.")
print(f"Health: {health}\n")

all_healthy = isinstance(health, dict) and all(
    v.get("healthy") for v in health.values() if isinstance(v, dict)
)

if all_healthy:
    print("All healthy")
    with open("/home/user/result.json", "w") as f:
        json.dump({"action": "NONE", "recovered": True}, f)
else:
    print("Regression detected\n")

    print("TestGenAgent generating tests...")
    prompt = (
        f"Regression detected. Health: {health}\n"
        f"Failure log: {failure_log}\n\n"
        "Generate pytest tests using ONLY:\n"
        "    from fastapi.testclient import TestClient\n"
        "    from app import app\n"
        "    client = TestClient(app)\n"
        '    client.post("/order", json={"product_id": 1, "quantity": 2})\n'
        '    client.post("/order", json={"product_id": 2, "quantity": 4, "coupon": "SAVE50"})\n\n'
        "Test basic order returns 200 and total == 20.0\n"
        "Test SAVE50 returns 200 and total == 4.0\n"
        "Include all imports. Call save_test_to_file when done."
    )
    test_code = testgen_agent.run(prompt)

    print("\nTestRunnerAgent running tests...")
    test_result = testrunner_agent.run(f"Run these tests:\n{test_code}")
    print(f"Result: {test_result}\n")

    print("GuardianAgent deciding...")
    guardian_prompt = (
        f"Regression in order API.\n"
        f"Health: {health}\n"
        f"Test result: {test_result}\n"
        f"Times failed before: {failure_count}\n\n"
        "PATCH    if failure_count == 0 and bug is in logic\n"
        "ROLLBACK if failure_count >= 1\n"
        "ESCALATE if failure_count >= 3\n\n"
        "Return ONLY one word: PATCH, ROLLBACK, or ESCALATE"
    )
    decision_raw = guardian_agent.run(guardian_prompt)

    action = "ROLLBACK"
    for word in ["ESCALATE", "PATCH", "ROLLBACK"]:
        if word in str(decision_raw).upper():
            action = word
            break
    print(f"Decision: {action}\n")

    print(f"HealerAgent executing {action}...")
    healer_prompt = (
        f"Decision: {action}\n"
        f"Health: {health}\n"
        "PATCH    -> call patch_app with reason\n"
        "ROLLBACK -> call rollback_app with reason\n"
        "ESCALATE -> call escalate with reason"
    )
    healer_agent.run(healer_prompt)

    print("\nVerifying recovery...")
    health_after = monitor_agent.run("Run health checks again.")
    recovered = isinstance(health_after, dict) and all(
        v.get("healthy") for v in health_after.values() if isinstance(v, dict)
    )
    print("Recovered" if recovered else "Still degraded")

    with open("/home/user/result.json", "w") as f:
        json.dump({"action": action, "recovered": recovered}, f)
"""

print(f"Fetching app.py from GitHub at {COMMIT_SHA[:7]}...")
app_code = get_file_from_github("app.py")

print("Spinning up e2b sandbox...")
with Sandbox.create() as sandbox:
    sandbox.commands.run(
        "pip install fastapi pytest httpx httpx2 smolagents openai python-multipart",
        timeout=120
    )

    sandbox.files.write("/home/user/app.py", app_code)
    sandbox.files.write("/home/user/immune_system.py", IMMUNE_CODE)

    result = sandbox.commands.run(
        "cd /home/user && "
        f"OPENAI_API_KEY='{OPENAI_KEY}' "
        "FAILURE_COUNT='0' "
        "FAILURE_LOG='baseline tests failed' "
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