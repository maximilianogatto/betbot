import json
import httpx
import os

HEADERS = {
    "accept": "json/4h7dznqdxwtp3hsfdyf5r793uahfxy7x",
    "referer": "https://tulospalvelu.palloliitto.fi/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
}

def query_endpoint(name, url):
    print(f"\nProbing {name}: {url}")
    try:
        r = httpx.get(url, headers=HEADERS, timeout=10.0)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            call_status = data.get("call", {}).get("status", "unknown")
            print(f"Call status: {call_status}")
            if call_status == "ok":
                print("Keys:", list(data.keys()))
                os.makedirs("sandbox/palloliitto/responses_params", exist_ok=True)
                with open(f"sandbox/palloliitto/responses_params/{name}.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"Saved response to sandbox/palloliitto/responses_params/{name}.json")
                return data
            else:
                print("Error returned in call:", data.get("call", {}).get("error"))
        else:
            print("HTTP Error:", r.text[:200])
    except Exception as e:
        print("Exception:", e)
    return None

def main():
    # 1. Test getMatches with competition_id and category_id
    query_endpoint("getMatches_VL", "https://spl.torneopal.net/taso/rest/getMatches?competition_id=spljp26&category_id=VL")
    
    # 2. Test getGroup (standings)
    # Does getGroup return standings?
    query_endpoint("getGroup_VL", "https://spl.torneopal.net/taso/rest/getGroup?competition_id=spljp26&category_id=VL")
    query_endpoint("getGroup_VL_g1", "https://spl.torneopal.net/taso/rest/getGroup?competition_id=spljp26&category_id=VL&group_id=1")
    
    # 3. Test getCategory
    query_endpoint("getCategory_VL", "https://spl.torneopal.net/taso/rest/getCategory?competition_id=spljp26&category_id=VL")
    
    # 4. Test getTeam
    query_endpoint("getTeam_SalPa", "https://spl.torneopal.net/taso/rest/getTeam?team_id=35119462")
    
    # 5. Let's see if there is any other match_id from getMatches today
    # P15 Kakkonen (P152) match today: SalPa vs MuSa/Tove YJ2
    # In analyze_data output, we saw referee_classification P8, time_stamp, etc., but didn't print match_id.
    # Let's search inside getMatches_2026-06-01.json to find a valid match_id to probe getMatch
    today_file = "sandbox/palloliitto/responses/getMatches_2026-06-01.json"
    if os.path.exists(today_file):
        with open(today_file, "r") as f:
            tdata = json.load(f)
        matches = tdata.get("matches", [])
        if matches:
            for m in matches:
                m_id = m.get("match_id")
                if m_id:
                    query_endpoint(f"getMatch_{m_id}", f"https://spl.torneopal.net/taso/rest/getMatch?match_id={m_id}")
                    break

if __name__ == "__main__":
    main()
