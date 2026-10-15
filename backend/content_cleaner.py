import re
from typing import Tuple, List, Optional
from bs4 import BeautifulSoup, Tag, Comment

# Tags that should be completely excised along with their children
DISCARD_TAGS = {
    "script",
    "style",
    "noscript",
    "iframe",
    "frame",
    "frameset",
    "object",
    "embed",
    "applet",
    "canvas",
    "svg",
    "audio",
    "video",
    "source",
    "track",
    "map",
    "area",
    "template",
    "slot",
    "portal",
    "dialog",
}

# Regex to detect hidden style attributes
HIDDEN_STYLE_RE = re.compile(
    r'(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0|font-size\s*:\s*0)',
    re.IGNORECASE,
)

# Common clutter classes/IDs (ads, cookie banners, tracking, share buttons)
CLUTTER_PATTERNS = [
    re.compile(r'(?:advertisement|cookie-banner|cookie-notice|cookie-consent|privacy-notice|ad-container|ad-wrapper|banner-ad|newsletter-popup|social-share|share-buttons)', re.IGNORECASE),
]

# Primary content candidate selectors in priority order
MAIN_CONTENT_SELECTORS = [
    "article",
    "main",
    '[role="main"]',
    "#main-content",
    "#content",
    ".main-content",
    ".content-area",
    ".post-content",
    ".article-content",
    ".entry-content",
    ".document-body",
    ".markdown-body",
    ".prose",
    ".story-body",
    "#story",
    "#article",
]


def is_element_hidden(tag: Tag) -> bool:
    """
    Check if a DOM element is styled or tagged as hidden.
    """
    # 1. HTML5 hidden attribute
    if tag.has_attr("hidden"):
        return True

    # 2. ARIA hidden
    if tag.get("aria-hidden", "").lower() == "true":
        return True

    # 3. Inline style display:none, visibility:hidden
    style = tag.get("style", "")
    if style and HIDDEN_STYLE_RE.search(style):
        return True

    return False


def is_clutter_element(tag: Tag) -> bool:
    """
    Identify popups, cookie consents, and advertisement widgets.
    """
    tag_id = tag.get("id", "")
    tag_classes = " ".join(tag.get("class", [])) if isinstance(tag.get("class"), list) else str(tag.get("class", ""))
    identifier = f"{tag_id} {tag_classes}".lower()

    for pattern in CLUTTER_PATTERNS:
        if pattern.search(identifier):
            return True

    return False


def extract_page_metadata(soup: BeautifulSoup) -> Tuple[str, Optional[str]]:
    """
    Extracts page title and meta description.
    """
    # Title resolution: <title> tag -> og:title -> twitter:title -> <h1>
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    elif soup.find("meta", property="og:title"):
        title = soup.find("meta", property="og:title").get("content", "").strip()
    elif soup.find("h1"):
        title = soup.find("h1").get_text(" ", strip=True)

    if not title:
        title = "Untitled Page"

    # Meta description
    meta_desc = None
    desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if desc_tag and desc_tag.get("content"):
        meta_desc = desc_tag.get("content").strip()

    return title, meta_desc


def clean_html_document(
    raw_html: str,
    mode: str = "main",
) -> Tuple[BeautifulSoup, Tag, str, Optional[str], List[str]]:
    """
    Cleans raw HTML:
    - Removes comments, scripts, styles, iframes, SVG, canvas, and media payloads
    - Unwraps images while preserving nearby or enclosed text and captions
    - Removes explicitly hidden elements and ad/cookie clutter
    - Locates the target root element according to scraping mode ('main' or 'full')
    Returns: (cleaned_soup, root_element, page_title, meta_description, warnings)
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    warnings: List[str] = []

    # 1. Extract metadata before destructive cleaning
    title, meta_desc = extract_page_metadata(soup)

    # 2. Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # 3. Remove blacklisted technical and graphical tags
    for tag in soup.find_all(list(DISCARD_TAGS)):
        tag.decompose()

    # 4. Remove image tags (img, picture) but preserve captions/surrounding text
    # If an image tag has an alt text that provides meaningful context, it might be noted,
    # but prompt specifies: "Images, image data, scripts, styles, and irrelevant visual elements are excluded.
    # Do not discard meaningful text simply because it is located near an image."
    for img in soup.find_all(["img", "picture", "figure"]):
        if img.name in ("img", "picture"):
            img.decompose()
        elif img.name == "figure":
            # In <figure>, if there's a <figcaption>, preserve it, just remove <img> inside
            for sub_img in img.find_all(["img", "picture", "svg"]):
                sub_img.decompose()

    # 5. Remove hidden elements
    for tag in soup.find_all(True):
        if is_element_hidden(tag):
            tag.decompose()

    # 6. Remove clutter (cookie banners, ads)
    for tag in soup.find_all(True):
        if is_clutter_element(tag):
            tag.decompose()

    # 7. Select Target Root based on mode
    body = soup.find("body") or soup

    if mode == "main":
        target_root = None
        # Try finding primary semantic article/main container
        for selector in MAIN_CONTENT_SELECTORS:
            candidates = body.select(selector)
            if candidates:
                # Pick candidate with the highest text length
                best = max(candidates, key=lambda c: len(c.get_text(strip=True)))
                if len(best.get_text(strip=True)) > 100:
                    target_root = best
                    break

        if target_root is None:
            # Fallback: remove <header>, <nav>, <footer>, <aside> from body clone for main content
            # Create a shallow working element
            target_root = body
            for nav in target_root.find_all(["header", "nav", "footer", "aside"]):
                nav.decompose()
            warnings.append("No explicit <article> or <main> container identified. Extracted cleaned body.")
    else:
        # Full Page mode: retain full body (including navigation, headers, footers)
        target_root = body

    return soup, target_root, title, meta_desc, warnings
