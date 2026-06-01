import re
import httpx

def main():
    print("Downloading frontend JS bundle to discover API methods...")
    
    # We found assets/index-DmtZiUSh.js in the captured URLs. Let's fetch it.
    # Note: Let's search captured_urls.txt to make sure the hash matches or we fetch the correct JS.
    # Let's read captured_urls.txt first
    with open("sandbox/palloliitto/captured_urls.txt", "r") as f:
        urls = f.read().splitlines()
        
    js_url = None
    for line in urls:
        if "assets/index-" in line and ".js" in line:
            parts = line.split(" ")
            js_url = parts[-1]
            break
            
    if not js_url:
        # Fallback to the one we saw
        js_url = "https://tulospalvelu.palloliitto.fi/assets/index-DmtZiUSh.js"
        
    print(f"JS URL to fetch: {js_url}")
    
    try:
        r = httpx.get(js_url, timeout=30.0)
        print(f"Status: {r.status_code}, length: {len(r.text)}")
        if r.status_code == 200:
            # Let's find all occurrences of getXYZ method calls
            # Usually they are inside strings like "getMatches", "getCategories", etc.
            # Torneopal rest paths look like: rest/getSomething
            # Let's search for "rest/" in the JS file or search for strings starting with "get" followed by uppercase
            methods = set(re.findall(r'get[A-Z][a-zA-Z0-9_]+', r.text))
            print(f"Found {len(methods)} possible method names in JS:")
            sorted_methods = sorted(list(methods))
            for m in sorted_methods:
                # Filter to only keep ones that are likely Torneopal endpoints (short, common sports terms)
                if any(x in m.lower() for x in ["match", "categor", "club", "standing", "group", "referee", "player", "score", "stat", "champ", "news", "site", "city", "location", "team"]):
                    print(f" - {m}")
                    
            # Let's search specifically for rest/ strings
            rest_matches = re.findall(r'taso/rest/([a-zA-Z0-9_]+)', r.text)
            print(f"\nSpecifically found following endpoints in taso/rest/ paths:")
            for rm in sorted(list(set(rest_matches))):
                print(f" - {rm}")
                
            # Let's also write a file with all matching methods for review
            with open("sandbox/palloliitto/discovered_methods.txt", "w") as f:
                f.write("DISCOVERED TASO/REST ENDPOINTS:\n")
                for rm in sorted(list(set(rest_matches))):
                    f.write(f"taso/rest/{rm}\n")
                f.write("\nALL POTENTIAL JS GET METHODS:\n")
                for m in sorted_methods:
                    f.write(f"{m}\n")
            print("\nSaved list to sandbox/palloliitto/discovered_methods.txt")
            
    except Exception as e:
        print("Failed to download or parse JS:", e)

if __name__ == "__main__":
    main()
