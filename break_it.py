# break_it.py
import re

# Read current app.py
with open("app.py", "r") as f:
    code = f.read()

# Enable the buggy discount engine
code = code.replace(
    "DISCOUNT_ENGINE_ENABLED = False",
    "DISCOUNT_ENGINE_ENABLED = True"
)

# Write back
with open("app.py", "w") as f:
    f.write(code)

print("💥 Breaking change applied to app.py")
print("   DISCOUNT_ENGINE_ENABLED = True (buggy SAVE50 logic active)")
print()
print("Now run:")
print("   git add app.py")
print("   git commit -m 'feat: enable discount engine'")
print("   git push origin main")