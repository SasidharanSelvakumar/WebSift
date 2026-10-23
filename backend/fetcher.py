import re
from typing import Tuple, Optional
import httpx

from backend.config import USER_AGENT, REQUEST_TIMEOUT_SECONDS, MAX_CONTENT_LENGTH
from backend.url_validator import validate_and_sanitize_url, SSRFProtectionError


class FetchError(Exception):
    """Raised when HTTP fetching fails."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class ContentTooLargeError(FetchError):
    """Raised when the fetched page exceeds maximum allowed size."""
    pass


# Markers that indicate a client-side rendered Single Page Application (SPA)
SPA_INDICATORS = [
    re.compile(r'<div[^>]+id=["\'](?:root|app|__next|___gatsby)["\']\s*>\s*</div>', re.IGNORECASE),
    re.compile(r'You need to enable JavaScript to run this app', re.IGNORECASE),
    re.compile(r'Please enable JavaScript to view this website', re.IGNORECASE),
    re.compile(r'<noscript>.*?(?:JavaScript|enable js).*?</noscript>', re.IGNORECASE | re.DOTALL),
]


def is_spa_or_js_heavy(html: str) -> bool:
    """
    Heuristic check to determine if an HTML document is mostly an empty JS shell.
    """
    # Quick strip of script and style tags to gauge raw visible text
    stripped = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    stripped = re.sub(r'<style.*?</style>', '', stripped, flags=re.DOTALL | re.IGNORECASE)
    text_content = re.sub(r'<[^>]+>', ' ', stripped)
    text_content = ' '.join(text_content.split())

    # If visible text is very sparse and known SPA markers exist
    if len(text_content) < 300:
        for pattern in SPA_INDICATORS:
            if pattern.search(html):
                return True

    return False


async def fetch_html(
    target_url: str,
    max_redirects: int = 5
) -> Tuple[str, str, bool]:
    """
    Safely fetches HTML content via HTTP.
    Enforces SSRF validation on initial URL and on every redirect hop.
    Enforces maximum content length and timeouts.
    Returns: (html_content, final_url, needs_browser_fallback)
    """
    current_url, _ = validate_and_sanitize_url(target_url)
    redirect_count = 0

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
    }

    timeout = httpx.Timeout(
        connect=5.0,
        read=REQUEST_TIMEOUT_SECONDS,
        write=5.0,
        pool=5.0,
    )

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        follow_redirects=False,  # We manually validate each redirect hop for SSRF
        verify=True,
    ) as client:
        while True:
            try:
                # Stream the response to enforce MAX_CONTENT_LENGTH before reading everything
                async with client.stream("GET", current_url) as response:
                    # Check Content-Length header if present
                    content_length_header = response.headers.get("Content-Length")
                    if content_length_header and int(content_length_header) > MAX_CONTENT_LENGTH:
                        raise ContentTooLargeError(
                            f"Content-Length ({content_length_header} bytes) exceeds maximum limit of {MAX_CONTENT_LENGTH} bytes."
                        )

                    # Handle Redirects safely
                    if response.status_code in (301, 302, 303, 307, 308):
                        redirect_count += 1
                        if redirect_count > max_redirects:
                            raise FetchError(f"Exceeded maximum redirect limit of {max_redirects}.")

                        location = response.headers.get("Location")
                        if not location:
                            raise FetchError("Received redirect status with missing Location header.")

                        # Resolve relative redirect URL
                        next_url = str(response.url.join(location))
                        # SSRF validation on the redirect target
                        current_url, _ = validate_and_sanitize_url(next_url)
                        continue

                    # Check HTTP status
                    if response.status_code >= 400:
                        raise FetchError(
                            f"Webpage returned error status code: {response.status_code} ({response.reason_phrase})",
                            status_code=response.status_code,
                        )

                    # Check Content-Type (must be HTML or text)
                    content_type = response.headers.get("Content-Type", "").lower()
                    if content_type and not any(t in content_type for t in ["text/html", "application/xhtml+xml", "text/plain", "application/xml"]):
                        raise FetchError(f"Unsupported content type '{content_type}'. WebSift only scrapes web pages.")

                    # Read and decompress body safely
                    await response.aread()
                    if len(response.content) > MAX_CONTENT_LENGTH:
                        raise ContentTooLargeError(
                            f"Response body exceeded maximum limit of {MAX_CONTENT_LENGTH} bytes."
                        )

                    html = response.text
                    needs_browser = is_spa_or_js_heavy(html)
                    return html, current_url, needs_browser

            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout):
                raise FetchError(f"Request timed out while connecting to {current_url}.")
            except httpx.ConnectError as e:
                raise FetchError(f"Failed to connect to host: {str(e)}")
            except (SSRFProtectionError, ContentTooLargeError, FetchError):
                raise
            except Exception as e:
                raise FetchError(f"Error fetching {current_url}: {str(e)}")
