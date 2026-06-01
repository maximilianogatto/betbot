import json
import httpx
from curl_cffi import requests

def test_with_httpx():
    print("--- Testing with httpx ---")
    url = "https://spl.torneopal.net/taso/rest/getSite"
    headers = {
        "accept": "json/4h7dznqdxwtp3hsfdyf5r793uahfxy7x",
        "referer": "https://tulospalvelu.palloliitto.fi/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    }
    try:
        r = httpx.get(url, headers=headers, timeout=10.0)
        print(f"httpx Status: {r.status_code}")
        if r.status_code == 200:
            print("httpx SUCCESS!")
            print("Response Sample:", r.text[:200])
            return True
        else:
            print("httpx Failed, response starts with:", r.text[:200])
    except Exception as e:
        print("httpx Exception:", e)
    return False

def test_with_curl_cffi():
    print("\n--- Testing with curl_cffi ---")
    url = "https://spl.torneopal.net/taso/rest/getSite"
    headers = {
        "accept": "json/4h7dznqdxwtp3hsfdyf5r793uahfxy7x",
        "referer": "https://tulospalvelu.palloliitto.fi/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, impersonate="chrome", timeout=10.0)
        print(f"curl_cffi Status: {r.status_code}")
        if r.status_code == 200:
            print("curl_cffi SUCCESS!")
            print("Response Sample:", r.text[:200])
            return True
        else:
            print("curl_cffi Failed, response starts with:", r.text[:200])
    except Exception as e:
        print("curl_cffi Exception:", e)
    return False

if __name__ == "__main__":
    httpx_success = test_with_httpx()
    curl_success = test_with_curl_cffi()
