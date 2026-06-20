# immune_system.py
from dotenv import load_dotenv
import os, json, subprocess
from e2b_code_interpreter import Sandbox
from smolagents import ToolCallingAgent, CodeAgent, OpenAIServerModel, tool
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

load_dotenv()

model = OpenAIServerModel(
    model_id="gpt-4o-mini",
    api_base="https://openai.vocareum.com/v1",
    api_key=os.getenv("UDACITY_OPENAI_API_KEY")
)

# ── Tools ──────────────────────────────────────────────────────────────────────

@tool
def run_tests_in_sandbox(test_code: str) -> dict:
    """
    Uploads app.py and runs the generated pytest code
    inside a secure e2b cloud sandbox.
    Args:
        test_code: complete pytest source code as a string
    Returns structured test results.
    """
    with Sandbox() as sandbox:
        # Install dependencies
        sandbox.commands.run(
            "pip install fastapi httpx pytest httpx2 python-multipart",
            timeout=60
        )

        # Upload real app.py from disk
        with open("app.py", "r") as f:
            sandbox.files.write("/home/user/app.py", f.read())

        # Write generated tests
        sandbox.files.write("/home/user/test_generated.py", test_code)

        # Run pytest
        result = sandbox.commands.run(
            "cd /home/user && pytest test_generated.py -v --tb=short",
            timeout=60
        )

        return {
            "status": "passed" if result.exit_code == 0 else "failed",
            "return_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr
        }


@tool
def save_test_to_file(content: str) -> str:
    """
    Saves generated pytest code to generated_tests.py locally
    and returns the content for sandbox execution.
    Args:
        content: complete pytest source code
    Returns confirmation with the saved content.
    """
    filename = "generated_tests.py"
    with open(filename, "w") as f:
        f.write(content + "\n")
    if "def test_" not in content:
        raise RuntimeError("No test functions found in generated code")
    return content   # ← return content so it can be passed to sandbox


@tool
def rollback_feature(reason: str) -> str:
    """
    Rolls back the breaking change by running fix_it.py
    and committing the revert.
    Args:
        reason: why the rollback is being applied
    Returns confirmation.
    """
    os.system("python fix_it.py")
    return f"⏪ Feature rolled back: {reason}"


@tool
def escalate(reason: str) -> str:
    """
    Escalates to on-call engineer via Slack.
    Args:
        reason: full failure description
    Returns confirmation.
    """
    print(f"🚨 ESCALATED: {reason}")
    return f"🚨 Escalated to on-call: {reason}"


@tool
def patch_feature(reason: str) -> str:
    """
    Applies a targeted fix to the buggy feature logic.
    Args:
        reason: description of the fix
    Returns confirmation.
    """
    with open("app.py", "r") as f:
        code = f.read()

    # Fix the specific SAVE50 bug
    code = code.replace(
        "return round(price / quantity * 0.5, 2)",
        "return round(price * quantity * 0.5, 2)"
    )

    with open("app.py", "w") as f:
        f.write(code)

    return f"✅ Patched discount engine: {reason}"


# ── Agents ─────────────────────────────────────────────────────────────────────

testgen_agent = ToolCallingAgent(
    name="TestGenAgent",
    description="Generates pytest regression tests for the detected failure.",
    model=model,
    tools=[save_test_to_file],
    max_steps=3
)

testrunner_agent = ToolCallingAgent(
    name="TestRunnerAgent",
    description="Runs tests in e2b sandbox and reports results.",
    model=model,
    tools=[run_tests_in_sandbox],
    max_steps=2
)

guardian_agent = CodeAgent(
    name="GuardianAgent",
    description="Decides PATCH, ROLLBACK or ESCALATE.",
    model=model,
    tools=[]
)

healer_agent = ToolCallingAgent(
    name="HealerAgent",
    description="Executes the recovery action.",
    model=model,
    tools=[patch_feature, rollback_feature, escalate],
    max_steps=3
)

# ── FastAPI immune system API ──────────────────────────────────────────────────

immune_app = FastAPI()

class FailureEvent(BaseModel):
    repo: str
    commit_sha: str
    branch: str
    failure_log: str

@immune_app.post("/analyze")
def analyze(event: FailureEvent):
    print(f"\n🧬 IMMUNE SYSTEM TRIGGERED")
    print(f"   Repo:   {event.repo}")
    print(f"   Commit: {event.commit_sha[:7]}")
    print(f"   Branch: {event.branch}\n")

    memory = []
    if os.path.exists("immune_memory.json"):
        with open("immune_memory.json") as f:
            memory = json.load(f)
    failure_count = len(memory)

    # Step 1: Generate tests
    print("🧪 TestGenAgent generating regression tests...")
    test_code = testgen_agent.run(f"""
    A commit to '{event.branch}' caused these test failures:
    {event.failure_log}

    Generate pytest tests that reproduce this failure.
    Use:
        from fastapi.testclient import TestClient
        from app import app
        client = TestClient(app)
        client.post("/order", json={{"product_id": 2, "quantity": 4, "coupon": "SAVE50"}})

    Test both:
    - A basic order that should return status 200
    - The failing SAVE50 coupon scenario asserting correct total

    ALWAYS include all necessary imports.
    Do NOT set anything at module level except imports and client.
    Call save_test_to_file with the complete code when done.
    """)

    # Step 2: Run tests in e2b sandbox
    print("\n🏃 TestRunnerAgent running tests in e2b sandbox...")
    test_result = testrunner_agent.run(
        f"Run these tests in the sandbox:\n{test_code}"
    )
    print(f"Result: {test_result}\n")

    # Step 3: Guardian decides
    print("🧠 GuardianAgent deciding action...")
    decision_raw = guardian_agent.run(f"""
    Failure log: {event.failure_log}
    Test result: {test_result}
    Times failed before: {failure_count}

    - PATCH    if failure_count == 0 and bug is in logic
    - ROLLBACK if failure_count >= 1
    - ESCALATE if failure_count >= 3

    Return ONLY one word: PATCH, ROLLBACK, or ESCALATE
    """)

    action = "ROLLBACK"
    for word in ["ESCALATE", "PATCH", "ROLLBACK"]:
        if word in str(decision_raw).upper():
            action = word
            break
    print(f"Decision: {action}\n")

    # Step 4: Heal
    print(f"🛠️  HealerAgent executing {action}...")
    healer_agent.run(f"""
    Decision: {action}
    Failure: {event.failure_log}

    - PATCH    → call patch_feature with reason
    - ROLLBACK → call rollback_feature with reason
    - ESCALATE → call escalate with reason
    """)

    # Step 5: Memory
    memory.append({
        "commit": event.commit_sha,
        "action": action,
        "branch": event.branch
    })
    with open("immune_memory.json", "w") as f:
        json.dump(memory, f, indent=2)

    print(f"\n✅ Immune cycle complete — action taken: {action}")
    return {"action": action, "commit": event.commit_sha}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(immune_app, host="0.0.0.0", port=8000)