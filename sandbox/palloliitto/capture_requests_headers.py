import asyncio
import json
import os
from playwright.async_api import async_playwright

async def main():
    print("Launching Playwright to capture request headers for Torneopal REST calls...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        captured = []
        
        # Listen to requests
        def handle_request(request):
            url = request.url
            if "torneopal.net" in url or "torneopal.fi" in url:
                headers = request.headers
                method = request.method
                captured.append({
                    "method": method,
                    "url": url,
                    "headers": headers
                })
                print(f"Captured: {method} {url}")
                
        page.on("request", handle_request)
        
        try:
            # Navigate to the home page
            await page.goto("https://tulospalvelu.palloliitto.fi/", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(5)
            
            # Save captured headers
            os.makedirs("sandbox/palloliitto", exist_ok=True)
            with open("sandbox/palloliitto/captured_headers.json", "w") as f:
                json.dump(captured, f, indent=2)
            print(f"Saved {len(captured)} requests with headers to sandbox/palloliitto/captured_headers.json")
            
        except Exception as e:
            print("Error:", e)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
