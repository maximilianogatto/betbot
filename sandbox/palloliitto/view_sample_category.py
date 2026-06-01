import json
import os

with open("sandbox/palloliitto/responses/getCategories.json", "r") as f:
    data = json.load(f)

categories = data.get("categories", [])
print(f"Total categories: {len(categories)}")

# Find one that matches 'VL'
vl_cat = [c for c in categories if c.get("category_id") == "VL"]
if vl_cat:
    print("\nVeikkausliiga Category:")
    print(json.dumps(vl_cat[0], indent=2))
else:
    print("\nVeikkausliiga category not found by ID 'VL'. First item:")
    print(json.dumps(categories[0], indent=2))
