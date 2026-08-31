import asyncio
import logging
from eap.adapters.excel.windows_com import WindowsExcelCOMAdapter
from eap.adapters.browser.playwright_adapter import PlaywrightBrowserAdapter

logging.basicConfig(level=logging.INFO)

async def test_playwright():
    try:
        adapter = PlaywrightBrowserAdapter(browser_type="chromium")
        await adapter.open_session(headless=True)
        print("Playwright session opened successfully")
        await adapter.close()
    except Exception as e:
        print(f"Playwright error: {e}")

def test_excel_com():
    try:
        adapter = WindowsExcelCOMAdapter(visible=False)
        xl = adapter._ensure_excel()
        print(f"Excel COM initialized successfully: {xl.Version}")
        adapter.close()
    except Exception as e:
        print(f"Excel COM error: {e}")

if __name__ == "__main__":
    print("Testing Excel COM...")
    test_excel_com()
    
    print("\nTesting Playwright...")
    asyncio.run(test_playwright())
