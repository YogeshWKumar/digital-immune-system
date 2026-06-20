# fix_it.py
# Read current app.py
with open("app.py", "r") as f:
    code = f.read()

# Disable the buggy feature
code = code.replace(
    "DISCOUNT_ENGINE_ENABLED = True",
    "DISCOUNT_ENGINE_ENABLED = False"
)

with open("app.py", "w") as f:
    f.write(code)

print("✅ Feature rolled back — DISCOUNT_ENGINE_ENABLED = False")