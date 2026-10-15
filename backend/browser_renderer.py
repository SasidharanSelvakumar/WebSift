import asyncio
import logging
from typing import Tuple
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from backend.config import USER_AGENT, PLAYWRIGHT_TIMEOUT_MS
from backend.url_validator import validate_and_sanitize_url

logger = logging.getLogger("websift.browser")


class BrowserRenderError(Exception):
    """Raised when headless browser rendering fails."""
    pass


async def render_with_browser(target_url: str) -> Tuple[str, str]:
    """
    Renders a page using headless Chromium to execute client-side JavaScript.
    Blocks media and fonts for maximum performance and security.
    Returns: (rendered_html, final_url)
    """
    safe_url, _ = validate_and_sanitize_url(target_url)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--no-first-run",
                    "--no-zygote",
                    "--disable-gpu",
                ],
            )

            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=False,
                java_script_enabled=True,
            )

            page = await context.new_page()

            # Optimize performance: block images, media, fonts, and heavy tracking
            async def intercept_route(route):
                request = route.request
                resource_type = request.resource_type
                if resource_type in ("image", "media", "font", "imageset"):
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", intercept_route)

            try:
                # Navigate and wait for DOM content loaded
                response = await page.goto(
                    safe_url,
                    wait_until="domcontentloaded",
                    timeout=PLAYWRIGHT_TIMEOUT_MS,
                )

                # Wait slightly for client-side scripts to populate DOM (up to 2 seconds or network idle)
                try:
                    await page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    # Network idle timeout is normal for streaming/analytics scripts
                    pass

                # Re-validate final URL in case of client-side or meta-refresh redirect
                final_url = page.url
                validate_and_sanitize_url(final_url)

                html_content = await page.content()
                await browser.close()
                return html_content, final_url

            except PlaywrightTimeoutError:
                await browser.close()
                raise BrowserRenderError(f"Browser rendering timed out after {PLAYWRIGHT_TIMEOUT_MS/1000} seconds for {safe_url}.")
            except Exception as e:
                await browser.close()
                raise BrowserRenderError(f"Browser rendering encountered an error: {str(e)}")

    except Exception as e:
        if isinstance(e, BrowserRenderError):
            raise
        raise BrowserRenderError(f"Failed to initialize headless browser: {str(e)}")
