import json
import os

with open("sandbox/palloliitto/responses/getSite.json", "r") as f:
    data = json.load(f)

print("getSite.json structure:")
for k, v in data.items():
    if isinstance(v, dict):
        print(f"Key: {k}, sub-keys: {list(v.keys())}")
    else:
        print(f"Key: {k}, type: {type(v).__name__}")

# Check 'call' field
if "call" in data:
    print("\nCall details:")
    print(json.dumps(data["call"], indent=2))

# Check 'current_competition'
if "current_competition" in data:
    print("\nCurrent competition details:")
    print(json.dumps(data["current_competition"], indent=2))
