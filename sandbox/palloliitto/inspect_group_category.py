import json
import os

RESPONSES_DIR = "sandbox/palloliitto/responses_params"

def main():
    # 1. Inspect Category VL
    cat_path = os.path.join(RESPONSES_DIR, "getCategory_VL.json")
    if os.path.exists(cat_path):
        with open(cat_path, "r") as f:
            data = json.load(f)
        category = data.get("category", {})
        print("Category Keys:", list(category.keys()))
        print("Category Name:", category.get("category_name"))
        # Check if there is groups list inside getCategory
        # E.g. 'groups' or 'category_group_levels' or 'phases' or 'rounds'
        for k in ["groups", "category_group_levels", "rounds", "phases", "stages"]:
            if k in category:
                print(f"Contains '{k}', length: {len(category[k]) if isinstance(category[k], list) else 'not list'}")
                if isinstance(category[k], list) and category[k]:
                    print(f"Sample '{k}' item keys:", list(category[k][0].keys()) if isinstance(category[k][0], dict) else "not dict")
                    print(f"Sample '{k}' item:", json.dumps(category[k][0], indent=2)[:500])

    # 2. Inspect Group VL g1
    group_path = os.path.join(RESPONSES_DIR, "getGroup_VL_g1.json")
    if os.path.exists(group_path):
        with open(group_path, "r") as f:
            gdata = json.load(f)
        group = gdata.get("group", {})
        print("\nGroup Keys:", list(group.keys()))
        print("Group Name:", group.get("group_name"))
        
        # Check ranking, teams, and live_standings
        for field in ["ranking", "teams", "live_standings"]:
            if field in group:
                val = group[field]
                print(f"\n--- Inspecting field '{field}', type: {type(val).__name__} ---")
                if isinstance(val, list):
                    print(f"List length: {len(val)}")
                    if val:
                        print("Sample item keys:", list(val[0].keys()) if isinstance(val[0], dict) else "not dict")
                        print("Sample item:", json.dumps(val[0], indent=2, ensure_ascii=False)[:800])
                elif isinstance(val, dict):
                    print("Dict keys:", list(val.keys()))
                    print("Sample:", json.dumps(val, indent=2, ensure_ascii=False)[:800])


if __name__ == "__main__":
    main()
