import json
import os

RESPONSES_DIR = "sandbox/palloliitto/responses_params"

def inspect_file(filename, path_key=None):
    path = os.path.join(RESPONSES_DIR, filename)
    if not os.path.exists(path):
        print(f"{filename} does not exist.")
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"\n=================== INSPECTING {filename} ===================")
    print("Top level keys:", list(data.keys()))
    
    if path_key and path_key in data:
        obj = data[path_key]
        print(f"Type of '{path_key}':", type(obj).__name__)
        if isinstance(obj, dict):
            print("Sub keys:", list(obj.keys()))
            # Print a clean, formatted sample of the structure
            print("\nSample structure:")
            print(json.dumps(obj, indent=2, ensure_ascii=False)[:1000])
        elif isinstance(obj, list):
            print("Length of list:", len(obj))
            if obj:
                print("Type of items in list:", type(obj[0]).__name__)
                if isinstance(obj[0], dict):
                    print("Item keys:", list(obj[0].keys()))
                print("\nSample list item structure:")
                print(json.dumps(obj[0], indent=2, ensure_ascii=False)[:1000])

if __name__ == "__main__":
    inspect_file("getCategory_VL.json", "category")
    inspect_file("getGroup_VL_g1.json", "group")
    inspect_file("getTeam_SalPa.json", "team")
    inspect_file("getMatch_4066662.json", "match")
