import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

logger = logging.getLogger("websift.crawler")

# Common tracking / noise query parameters to strip during normalization
TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "msclkid",
    "ref",
    "ref_",
    "source",
    "_ga",
    "_gl",
}

# Regex to detect product-like path segments
PRODUCT_URL_PATTERNS = [
    re.compile(r"/(?:product|products|p|item|items|medicine|medicines|drug|drugs|detail|dp)/[a-zA-Z0-9_\-\.\/]+", re.IGNORECASE),
    re.compile(r"/[a-zA-Z0-9_\-]+-(?:tablet|capsule|syrup|injection|ointment|gel|suspension|drops|mg|mcg|pack|strip)\b", re.IGNORECASE),
    re.compile(r"[?&](?:product_id|item_id|sku|pid|prod_id)=\w+", re.IGNORECASE),
]

# Patterns for links that are definitely NOT products
NON_PRODUCT_PATTERNS = [
    re.compile(r"/(?:cart|checkout|basket|account|login|register|signin|signup|profile|auth|privacy|terms|contact|about|faq|help|careers|blog|news|press)/?", re.IGNORECASE),
    re.compile(r"/(?:wishlist|orders|track-order|shipping|returns|disclaimer|sitemap|feedback|editorial-policy)/?", re.IGNORECASE),
    re.compile(r"/(?:cancer-care|subscription-plan|subscription|subscriptions|done-in-one|prescription-order|order-with-prescription|care-plan|consult-doctor|doctor-consultation)/?", re.IGNORECASE),
    re.compile(r"/(?:drugs-all-medicines|drugs-faq|all-diseases|articles|offers|coupons|deals|labs|diagnostics|radiology)/?", re.IGNORECASE),
    re.compile(r"\.(?:png|jpg|jpeg|gif|webp|svg|ico|css|js|pdf|zip|rar)$", re.IGNORECASE),
    re.compile(r"^(?:mailto|tel|javascript|whatsapp):", re.IGNORECASE),
]

# Words that indicate a "Next Page" link in text or attributes
NEXT_PAGE_TEXT_PATTERNS = [
    re.compile(r"^\s*(?:next|next\s*page|next\s*>|next\s*»|next\s*→|›|»)\s*$", re.IGNORECASE),
    re.compile(r"\bnext\b", re.IGNORECASE),
]


def normalize_url(raw_url: str, base_url: str) -> Optional[str]:
    """
    Resolves relative URLs against base_url, removes fragments, normalizes scheme/host,
    and strips common tracking query parameters.
    """
    if not raw_url:
        return None

    trimmed = raw_url.strip()
    if trimmed.startswith(("#", "javascript:", "mailto:", "tel:", "whatsapp:")):
        return None

    # Resolve relative URL to absolute
    absolute_url = urljoin(base_url, trimmed)

    try:
        parsed = urlparse(absolute_url)
    except Exception:
        return None

    if parsed.scheme not in ("http", "https"):
        return None

    # Clean query parameters (remove tracking params)
    query_dict = parse_qs(parsed.query, keep_blank_values=True)
    filtered_query = {k: v for k, v in query_dict.items() if k.lower() not in TRACKING_QUERY_PARAMS}
    cleaned_query = urlencode(filtered_query, doseq=True)

    # Reconstruct URL without fragment and with normalized lowercase netloc
    clean_url = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path,
        parsed.params,
        cleaned_query,
        "",  # No fragment
    ))

    # Strip trailing slash unless it's just root path
    if clean_url.endswith("/") and parsed.path != "/":
        clean_url = clean_url.rstrip("/")

    return clean_url


def is_product_url(url: str, base_url: str) -> bool:
    """
    Determines whether a normalized URL is likely a medicine product detail page.
    Restricts to the same hostname, checks non-product exclusions, and enforces
    site-specific patterns (such as 1mg /drugs/<slug> format).
    """
    try:
        base_netloc = urlparse(base_url).netloc.lower()
        target_netloc = urlparse(url).netloc.lower()
        parsed_target = urlparse(url)
    except Exception:
        return False

    # Must be same domain or subdomain
    if target_netloc != base_netloc and not target_netloc.endswith(f".{base_netloc}"):
        return False

    # Exclude non-product paths immediately
    for pattern in NON_PRODUCT_PATTERNS:
        if pattern.search(url):
            return False

    path = parsed_target.path

    # Specific strict rule for Tata 1mg
    if "1mg.com" in target_netloc:
        # A valid medicine detail page on 1mg MUST be /drugs/<medicine-slug-id>
        # And must NOT be /drugs-all-medicines or /drugs-faq
        if path.startswith("/drugs-all-medicines") or path.startswith("/drugs-faq"):
            return False
        if re.match(r"^/drugs/[a-zA-Z0-9_\-\.]+(?:-\d+)?$", path, re.IGNORECASE):
            return True
        return False

    # Positive match against product URL patterns for general pharmacy sites
    for pattern in PRODUCT_URL_PATTERNS:
        if pattern.search(url):
            return True

    # Fallback check on path depth: product detail pages typically have depth >= 2
    path_segments = [p for p in path.split("/") if p]
    if len(path_segments) >= 2 and any(any(c.isdigit() for c in p) or "-" in p for p in path_segments):
        # Exclude general non-product directories
        first_segment = path_segments[0].lower()
        if first_segment in (
            "category", "categories", "catalog", "browse", "department",
            "search", "collection", "collections", "brand", "brands", "info"
        ):
            return False
        return True

    return False


def extract_product_links(
    raw_html: str,
    base_url: str,
    custom_selector: Optional[str] = None,
) -> List[str]:
    """
    Discovers all unique product URLs on a category/listing page.
    Supports configurable CSS selectors with an intelligent heuristic fallback.
    Maintains discovery order and deduplicates URLs.
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    discovered_urls: List[str] = []
    seen: Set[str] = set()

    # 1. Custom CSS selector if supplied
    if custom_selector:
        try:
            for elem in soup.select(custom_selector):
                href = elem.get("href") if elem.name == "a" else None
                if not href:
                    a_child = elem.find("a", href=True)
                    if a_child:
                        href = a_child["href"]

                if href:
                    normalized = normalize_url(href, base_url)
                    if normalized and normalized not in seen:
                        seen.add(normalized)
                        discovered_urls.append(normalized)

            if discovered_urls:
                logger.info(f"Discovered {len(discovered_urls)} product URLs using custom selector '{custom_selector}'")
                return discovered_urls
        except Exception as e:
            logger.warning(f"Custom product selector failed: {str(e)}. Falling back to heuristic discovery.")

    # 2. Heuristic container discovery: Look for product cards / tiles
    container_selectors = [
        "article",
        "[class*='product-card']",
        "[class*='product-item']",
        "[class*='product-tile']",
        "[class*='productCard']",
        "[class*='productItem']",
        "[class*='medicine-card']",
        "[class*='item-card']",
        "[class*='catalog-item']",
        "[data-sku]",
        "[data-product-id]",
    ]

    for sel in container_selectors:
        cards = soup.select(sel)
        if cards:
            for card in cards:
                # Find the primary link inside card
                for a in card.find_all("a", href=True):
                    href = a["href"]
                    normalized = normalize_url(href, base_url)
                    if normalized and normalized != base_url:
                        # Validate it's not a generic action link
                        if not any(np.search(normalized) for np in NON_PRODUCT_PATTERNS):
                            if normalized not in seen:
                                seen.add(normalized)
                                discovered_urls.append(normalized)
                                break  # One primary link per card

    if len(discovered_urls) >= 2:
        return discovered_urls

    # 3. Fallback: Scan all <a> tags with product pattern detection
    for a in soup.find_all("a", href=True):
        href = a["href"]
        normalized = normalize_url(href, base_url)
        if not normalized or normalized in seen or normalized == base_url:
            continue

        if is_product_url(normalized, base_url):
            seen.add(normalized)
            discovered_urls.append(normalized)

    return discovered_urls


PAGINATION_QUERY_PARAMS = {"page", "p", "pg", "page_number", "pageindex", "pagenum"}


def extract_listing_scope(base_url: str, raw_html: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts the listing scope (hostname, path, and non-pagination query parameters
    such as alphabet 'label' or 'category') from the starting URL and optional HTML.
    """
    parsed = urlparse(base_url)
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    query = parse_qs(parsed.query, keep_blank_values=True)

    scope_params = {
        k: v for k, v in query.items()
        if k.lower() not in PAGINATION_QUERY_PARAMS
        and k.lower() not in TRACKING_QUERY_PARAMS
    }

    # Special scope detection for Tata 1mg:
    if "1mg.com" in netloc and (path == "/drugs-all-medicines" or path.startswith("/drugs-all-medicines")):
        if "label" not in scope_params:
            label_val = None
            if raw_html:
                soup_mini = BeautifulSoup(raw_html[:8192], "html.parser")
                can = soup_mini.find("link", rel=lambda r: r and "canonical" in r)
                if can and can.get("href"):
                    can_q = parse_qs(urlparse(can["href"]).query)
                    if "label" in can_q:
                        label_val = can_q["label"][0].lower()
            if not label_val:
                label_val = "a"  # default alphabet on 1mg
            scope_params["label"] = [label_val]

    return {
        "netloc": netloc,
        "path": path,
        "scope_params": scope_params,
    }


def is_url_in_scope(candidate_url: str, scope: Dict[str, Any]) -> bool:
    """
    Validates whether candidate_url strictly belongs to the defined listing scope.
    Guards against alphabet hopping (e.g. label=a jumping to label=b) and path divergence.
    """
    try:
        parsed = urlparse(candidate_url)
    except Exception:
        return False

    cand_netloc = parsed.netloc.lower()
    scope_netloc = scope.get("netloc", "")
    if cand_netloc != scope_netloc and not cand_netloc.endswith(f".{scope_netloc}"):
        return False

    cand_path = parsed.path.rstrip("/")
    scope_path = scope.get("path", "")
    if cand_path != scope_path:
        return False

    cand_query = parse_qs(parsed.query, keep_blank_values=True)
    for k, expected_vals in scope.get("scope_params", {}).items():
        if k in cand_query:
            cand_vals = [x.lower() for x in cand_query[k]]
            norm_expected = [x.lower() for x in expected_vals]
            if cand_vals != norm_expected:
                return False

    return True


def preserve_scope_in_url(
    candidate_url: str,
    scope: Dict[str, Any],
    page_num: Optional[int] = None,
) -> str:
    """
    Ensures all scope query parameters (like alphabet label) are preserved in candidate_url.
    Optionally sets/updates the page number parameter.
    """
    parsed = urlparse(candidate_url)
    query_dict = parse_qs(parsed.query, keep_blank_values=True)

    # Merge scope params if missing
    for k, v in scope.get("scope_params", {}).items():
        if k not in query_dict:
            query_dict[k] = v

    if page_num is not None:
        query_dict["page"] = [str(page_num)]

    filtered_query = {
        k: v for k, v in query_dict.items() if k.lower() not in TRACKING_QUERY_PARAMS
    }
    cleaned_query = urlencode(filtered_query, doseq=True)

    netloc = parsed.netloc.lower() or scope.get("netloc", "")
    scheme = parsed.scheme.lower() or "https"

    clean_url = urlunparse((
        scheme,
        netloc,
        parsed.path,
        parsed.params,
        cleaned_query,
        "",
    ))
    if clean_url.endswith("/") and parsed.path != "/":
        clean_url = clean_url.rstrip("/")
    return clean_url


def extract_next_page_link(
    raw_html: str,
    base_url: str,
    current_page_url: str,
    custom_selector: Optional[str] = None,
    visited_urls: Optional[Set[str]] = None,
) -> Optional[str]:
    """
    Finds the next listing page URL from pagination controls or query parameters.
    Supports configurable CSS selectors, standard rel="next", pagination text heuristics,
    numbered pagination, button-based pagination controls, and query-based pagination.
    Enforces scope isolation (e.g. keeping alphabet label) and guards against pagination loops.
    """
    if visited_urls is None:
        visited_urls = set()

    scope = extract_listing_scope(base_url, raw_html)
    soup = BeautifulSoup(raw_html, "html.parser")

    def _validate_and_format_candidate(cand_href: str) -> Optional[str]:
        cand = normalize_url(cand_href, current_page_url)
        if not cand:
            return None
        if not is_url_in_scope(cand, scope):
            return None
        formatted = preserve_scope_in_url(cand, scope)
        if formatted and formatted not in visited_urls and formatted != current_page_url:
            return formatted
        return None

    # 1. User-configured custom next-page selector
    if custom_selector:
        try:
            elem = soup.select_one(custom_selector)
            if elem:
                href = elem.get("href") if elem.name == "a" else None
                if not href:
                    a_child = elem.find("a", href=True)
                    if a_child:
                        href = a_child["href"]

                if href:
                    cand = _validate_and_format_candidate(href)
                    if cand:
                        return cand
        except Exception as e:
            logger.warning(f"Custom next page selector failed: {str(e)}")

    # 2. Standard HTML rel="next" tag (<link rel="next"> or <a rel="next">)
    rel_next = soup.find(lambda tag: tag.name in ("link", "a") and tag.get("rel") and "next" in tag.get("rel"))
    if rel_next and rel_next.get("href"):
        cand = _validate_and_format_candidate(rel_next["href"])
        if cand:
            return cand

    # 3. Explicit classes or aria labels indicating "Next"
    next_selectors = [
        "a.next",
        "a.next-page",
        "a.pagination__next",
        "a.pagination-next",
        "a[aria-label*='Next' i]",
        "a[aria-label*='next page' i]",
        "a[title*='Next' i]",
        "li.next a",
        "li.pagination-next a",
        "[class*='next'] a",
    ]
    for sel in next_selectors:
        for elem in soup.select(sel):
            href = elem.get("href")
            if href:
                # Check that it's not disabled
                classes = " ".join(elem.get("class") or [])
                parent_classes = " ".join(elem.parent.get("class") or []) if elem.parent else ""
                if "disabled" in classes.lower() or "disabled" in parent_classes.lower():
                    continue

                cand = _validate_and_format_candidate(href)
                if cand:
                    return cand

    # 4. Text-matching on <a> tags ("Next", "Next >", "Next »", "›", "»")
    for a in soup.find_all("a", href=True):
        text = a.get_text().strip()
        aria_label = a.get("aria-label", "").strip()
        classes = " ".join(a.get("class") or [])
        if "disabled" in classes.lower():
            continue

        for pat in NEXT_PAGE_TEXT_PATTERNS:
            if pat.match(text) or pat.match(aria_label):
                cand = _validate_and_format_candidate(a["href"])
                if cand:
                    return cand

    # 5. Numbered pagination: Find active page and check next sibling page link
    active_selectors = [
        "li.active a",
        "li.selected a",
        "a.active",
        "a.current",
        "[aria-current='page']",
        ".pagination .active",
    ]
    for sel in active_selectors:
        active_elem = soup.select_one(sel)
        if active_elem:
            parent = active_elem.parent if active_elem.name == "a" else active_elem
            next_sib = parent.find_next_sibling()
            if next_sib:
                a_tag = next_sib if next_sib.name == "a" else next_sib.find("a", href=True)
                if a_tag and a_tag.get("href"):
                    cand = _validate_and_format_candidate(a_tag["href"])
                    if cand:
                        return cand

    # 6. Fallback / Button & JS Pagination (e.g. Tata 1mg, SPA or button-driven pagination)
    # Check if there is an explicit Next button or control
    next_btn = soup.find(
        lambda tag: tag.name in ("button", "div", "span")
        and (
            (tag.get("aria-label") and "next" in tag.get("aria-label", "").lower())
            or (tag.get("title") and "next" in tag.get("title", "").lower())
            or any(pat.match(tag.get_text().strip()) for pat in NEXT_PAGE_TEXT_PATTERNS if tag.get_text().strip())
        )
    )

    if next_btn:
        btn_classes = " ".join(next_btn.get("class") or []).lower()
        parent_classes = " ".join(next_btn.parent.get("class") or []).lower() if next_btn.parent else ""
        is_disabled = (
            next_btn.has_attr("disabled")
            or next_btn.get("aria-disabled") == "true"
            or "disabled" in btn_classes
            or "disabled" in parent_classes
        )
        if is_disabled:
            # Explicitly disabled next button -> End of pagination reached!
            return None

        # Next button is present and active: determine next page number
        parsed_curr = urlparse(current_page_url)
        curr_query = parse_qs(parsed_curr.query, keep_blank_values=True)
        curr_page = 1
        for p_param in ("page", "p", "pg", "page_number"):
            if p_param in curr_query:
                try:
                    curr_page = int(curr_query[p_param][0])
                    break
                except (ValueError, IndexError):
                    pass

        next_page_num = curr_page + 1
        cand = preserve_scope_in_url(current_page_url, scope, page_num=next_page_num)
        if cand and cand not in visited_urls and cand != current_page_url:
            return cand

    # 7. Check numbered pagination container without href (e.g. div role="link" or page buttons)
    pagination_container = soup.find(
        lambda tag: tag.name in ("div", "ul", "nav")
        and any(
            cls in " ".join(tag.get("class") or []).lower()
            for cls in ("pagination", "pager", "page-nav", "paging")
        )
    )
    if pagination_container:
        parsed_curr = urlparse(current_page_url)
        curr_query = parse_qs(parsed_curr.query, keep_blank_values=True)
        curr_page = 1
        for p_param in ("page", "p", "pg", "page_number"):
            if p_param in curr_query:
                try:
                    curr_page = int(curr_query[p_param][0])
                    break
                except (ValueError, IndexError):
                    pass

        next_page_str = str(curr_page + 1)
        has_next_num = any(
            elem.get_text().strip() == next_page_str
            for elem in pagination_container.find_all(True)
        )
        if has_next_num:
            cand = preserve_scope_in_url(current_page_url, scope, page_num=curr_page + 1)
            if cand and cand not in visited_urls and cand != current_page_url:
                return cand

    return None


def is_explicit_last_page(raw_html: str) -> bool:
    """
    Checks if the HTML explicitly contains a disabled 'Next' button or pagination endpoint marker.
    """
    if not raw_html:
        return False
    soup = BeautifulSoup(raw_html, "html.parser")
    next_btn = soup.find(
        lambda tag: tag.name in ("button", "div", "span", "a", "li")
        and (
            (tag.get("aria-label") and "next" in tag.get("aria-label", "").lower())
            or (tag.get("title") and "next" in tag.get("title", "").lower())
            or any(pat.match(tag.get_text().strip()) for pat in NEXT_PAGE_TEXT_PATTERNS if tag.get_text().strip())
        )
    )
    if next_btn:
        btn_classes = " ".join(next_btn.get("class") or []).lower()
        parent_classes = " ".join(next_btn.parent.get("class") or []).lower() if next_btn.parent else ""
        if (
            next_btn.has_attr("disabled")
            or next_btn.get("aria-disabled") == "true"
            or "disabled" in btn_classes
            or "disabled" in parent_classes
        ):
            return True
    return False


def get_fallback_next_page_url(
    current_page_url: str,
    scope: Dict[str, Any],
    visited_urls: Optional[Set[str]] = None,
) -> Optional[str]:
    """
    Computes the sequential fallback next page URL by incrementing the page query parameter,
    strictly preserving all scope parameters (e.g. alphabet label), and checking visited_urls.
    Returns None if current URL has no discernible pagination parameter or if next page is already visited.
    """
    if visited_urls is None:
        visited_urls = set()

    parsed = urlparse(current_page_url)
    curr_query = parse_qs(parsed.query, keep_blank_values=True)

    curr_page = 1
    found_page_param = False
    for p_param in ("page", "p", "pg", "page_number"):
        if p_param in curr_query:
            try:
                curr_page = int(curr_query[p_param][0])
                found_page_param = True
                break
            except (ValueError, IndexError):
                pass

    if not found_page_param and "drugs-all-medicines" in parsed.path:
        curr_page = 1
        found_page_param = True

    if not found_page_param:
        return None

    next_page_num = curr_page + 1
    cand = preserve_scope_in_url(current_page_url, scope, page_num=next_page_num)
    if cand and cand not in visited_urls and cand != current_page_url:
        return cand
    return None
