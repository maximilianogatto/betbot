import json
import os

with open("sandbox/palloliitto/captured_headers.json", "r") as f:
    data = json.load(f)

# Find API requests (containing 'taso/rest')
api_requests = [r for r in data if "taso/rest" in r.get("url", "")]
print(f"Found {len(api_requests)} REST API requests.")

if api_requests:
    print("\nHeaders for the first REST API request:")
    first = api_requests[0]
    print(f"URL: {first['url']}")
    print(f"Method: {first['method']}")
    print("Headers:")
    print(json.dumps(first["headers"], indent=2))
    
    # Check if there are differences between headers of different API requests
    print("\nAre there any authorization or stamp headers in other API requests?")
    for r in api_requests:
        url_name = r["url"].split("/")[-1].split("?")[0]
        auth_headers = {k: v for k, v in r["headers"].items() if k.lower() in ["authorization", "cookie", "stamp", "x-stamp", "token"]}
        print(f"Endpoint: {url_name} -> Auth headers: {auth_headers}")
else:
    print("No REST API requests found in captured_headers.json.")
