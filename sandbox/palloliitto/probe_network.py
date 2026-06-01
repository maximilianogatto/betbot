import asyncio
import json
import os
import sys
from playwright.async_api import async_playwright

async def main():
    print("Starting Playwright to capture network requests on tulospalvelu.palloliitto.fi...")
    
    async with async_playwright() as p:
        # Launch browser in headless mode
        browser = await p.chromium.launch(headless=True)
        # Create a new page
        page = await browser.new_page()
        
        # Dictionary to store captured network requests
        captured_requests = []
        
        # Listen to requests
        page.on("request", lambda request: captured_requests.append({
            "url": request.url,
            "method": request.method,
            "headers": request.headers,
        }))
        
        # Listen to responses
        def handle_response(response):
            # Only log API or JSON responses
            url = response.url
            if "api" in url or "json" in url or "graphql" in url:
                print(f"Captured API Response: {response.status} {response.request.method} {url}")
                
        page.on("response", handle_response)
        
        try:
            # Navigate to the home page
            print("Navigating to home page...")
            await page.goto("https://tulospalvelu.palloliitto.fi/", wait_until="networkidle", timeout=60000)
            
            # Wait for 5 seconds to let dynamic content load
            await asyncio.sleep(5)
            
            # Save all request URLs to a file for analysis
            os.makedirs("sandbox/palloliitto", exist_ok=True)
            with open("sandbox/palloliitto/captured_urls.txt", "w") as f:
                for req in captured_requests:
                    f.write(f"{req['method']} {req['url']}\n")
            print(f"Saved {len(captured_requests)} captured request URLs to sandbox/palloliitto/captured_urls.txt")
            
        except Exception as e:
            print("Error during navigation:", e)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
