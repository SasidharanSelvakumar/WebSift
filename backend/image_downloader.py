import asyncio
import logging
import os
import platform
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from backend.config import USER_AGENT
from backend.crawler import (
    extract_listing_scope,
    extract_next_page_link,
    extract_product_links,
    get_fallback_next_page_url,
    is_explicit_last_page,
)
from backend.fetcher import fetch_html
from backend.url_validator import validate_and_sanitize_url

logger = logging.getLogger("websift.image_downloader")

# Root output directory for downloaded medicine images
OUTPUT_IMAGES_DIR = Path(__file__).resolve().parent.parent / "output" / "medicine_images"


def sanitize_medicine_filename(name: str, max_length: int = 120) -> str:
    """
    Sanitizes a medicine name for safe cross-platform filesystem storage:
    - Strips invalid characters (<>:"/\\|?* and control characters).
    - Converts spaces and punctuation dashes into single underscores.
    - Collapses multiple underscores and strips leading/trailing underscores/dots.
    - Preserves alphanumeric tokens, decimal dots in dosages (e.g. 0.8ml, 2.5mg).
    - Caps name length to prevent filesystem path overflow on Windows.
    - Defaults to 'medicine_product' if resulting string is empty.
    """
    if not name:
        return "medicine_product"

    cleaned = name.strip()

    # Replace forbidden Windows/POSIX characters
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", cleaned)

    # Replace parentheses, brackets, commas, semicolons, quotes with space
    cleaned = re.sub(r"[()\[\]{};,'`]", " ", cleaned)

    # Replace whitespace and dashes with underscores
    cleaned = re.sub(r"[\s\-]+", "_", cleaned)

    # Collapse multiple underscores
    cleaned = re.sub(r"_+", "_", cleaned)

    # Strip leading/trailing underscores and periods
    cleaned = cleaned.strip("._ ")

    # Cap length
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip("._ ")

    return cleaned if cleaned else "medicine_product"


def detect_image_extension(image_url: str, content_type: Optional[str] = None) -> str:
    """
    Determines the appropriate file extension (.webp, .jpg, .png, etc.)
    from the image URL or the HTTP Content-Type header.
    Defaults to .jpg if undetermined.
    """
    # 1. Check Content-Type header if provided
    if content_type:
        ct = content_type.lower().split(";")[0].strip()
        if ct in ("image/webp", "application/webp"):
            return ".webp"
        elif ct in ("image/png", "application/png"):
            return ".png"
        elif ct in ("image/jpeg", "image/jpg", "image/pjpeg"):
            return ".jpg"
        elif ct in ("image/gif",):
            return ".gif"
        elif ct in ("image/avif",):
            return ".avif"
        elif ct in ("image/svg+xml", "image/svg"):
            return ".svg"

    # 2. Check path in URL
    parsed = urlparse(image_url)
    path = parsed.path.lower()
    for ext in (".webp", ".png", ".jpg", ".jpeg", ".avif", ".gif", ".svg"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext

    # 3. Check query parameters (e.g. format=webp or f_auto)
    query = parsed.query.lower()
    if "format=webp" in query or "f_webp" in query:
        return ".webp"
    elif "format=png" in query or "f_png" in query:
        return ".png"
    elif "format=jpg" in query or "format=jpeg" in query or "f_jpg" in query:
        return ".jpg"

    return ".jpg"


def extract_medicine_name_and_image(raw_html: str, page_url: str) -> Tuple[str, Optional[str]]:
    """
    Extracts the medicine name and primary product image URL from a product detail page.
    Supports Tata 1mg and general pharmacy / e-commerce platforms.
    """
    if not raw_html:
        return "", None

    soup = BeautifulSoup(raw_html, "html.parser")

    # 1. Medicine Name
    name = ""
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(strip=True)

    if not name:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            name = og_title["content"].split(" - ")[0].split(" | ")[0].split(": View")[0].strip()

    if not name and soup.title and soup.title.string:
        name = soup.title.string.split(" - ")[0].split(" | ")[0].split(": View")[0].strip()

    # Fallback name from URL slug if still empty
    if not name:
        slug = urlparse(page_url).path.rstrip("/").split("/")[-1]
        name = slug.replace("-", " ").title()

    # 2. Product Image URL Discovery
    img_url = None

    # Heuristic A: Look for SkuImages / ProductImage classes (1mg / pharmacy pattern)
    for img in soup.find_all("img"):
        classes = " ".join(img.get("class") or []).lower()
        if "skuimages" in classes or "productimage" in classes or "gallery" in classes:
            src = img.get("src") or img.get("data-src") or ""
            if src.startswith("http") and not src.lower().endswith(".svg"):
                img_url = src
                break

    # Heuristic B: Gumlet / Cloudinary cropped product images (Tata 1mg pattern)
    if not img_url:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if "onemg.gumlet.io" in src and "cropped" in src:
                if not src.lower().endswith(".svg"):
                    img_url = src
                    break

    # Heuristic C: General CDN product images (excluding logos, icons, navigation, SVGs)
    if not img_url:
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if any(domain in src for domain in ["onemg.gumlet.io", "res.cloudinary.com", "images.1mg.com", "product"]):
                if not any(noise in src.lower() for noise in ["logo", "icon", "chevron", "dropdown", "placeholder", "badge", ".svg"]):
                    img_url = src
                    break

    # Heuristic D: Schema.org JSON-LD structured data
    if not img_url:
        import json
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string)
                if isinstance(data, dict):
                    img_candidate = data.get("image")
                    if isinstance(img_candidate, str) and img_candidate.startswith("http") and not img_candidate.lower().endswith(".svg"):
                        img_url = img_candidate
                        break
                    elif isinstance(img_candidate, list) and img_candidate:
                        first = img_candidate[0]
                        if isinstance(first, str) and first.startswith("http") and not first.lower().endswith(".svg"):
                            img_url = first
                            break
            except Exception:
                pass

    # Heuristic E: OpenGraph og:image (if not site generic logo or icon)
    if not img_url:
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            content = og_img["content"].strip()
            if content.startswith("http") and not any(noise in content.lower() for noise in ["logo", "default", "favicon", "placeholder", ".svg"]):
                img_url = content

    # Heuristic F: First non-icon image in main/article container
    if not img_url:
        main_elem = soup.find(["main", "article", "div[class*='product']"])
        if main_elem:
            for img in main_elem.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src.startswith("http") and not any(noise in src.lower() for noise in ["logo", "icon", "placeholder", ".svg"]):
                    img_url = src
                    break

    return name, img_url


def extract_direct_images_from_listing(raw_html: str, base_url: str) -> List[Dict[str, str]]:
    """
    Checks if a listing page contains cards with BOTH the medicine name and image reference directly.
    Returns a list of dicts: [{"name": ..., "image_url": ..., "product_url": ...}]
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    results = []
    seen_images = set()

    # Search for product card containers
    card_selectors = [
        "article",
        "[class*='product-card']",
        "[class*='product-item']",
        "[class*='product-tile']",
        "[class*='productCard']",
        "[class*='drug-item']",
    ]

    for sel in card_selectors:
        cards = soup.select(sel)
        for card in cards:
            a = card.find("a", href=True)
            img = card.find("img")
            if not a or not img:
                continue

            src = img.get("src") or img.get("data-src") or ""
            if not src.startswith("http") or any(noise in src.lower() for noise in ["logo", "icon", "placeholder", ".svg"]):
                continue

            # Extract medicine name from card text, title, or img alt
            name = a.get_text(strip=True)
            if not name:
                name = img.get("alt", "").strip()

            if name and src not in seen_images:
                seen_images.add(src)
                href = a["href"]
                from backend.crawler import normalize_url
                norm_href = normalize_url(href, base_url) or href
                results.append({
                    "name": name,
                    "image_url": src,
                    "product_url": norm_href,
                })

    return results


def resolve_unique_filename(
    output_dir: Path,
    base_name: str,
    ext: str,
    product_url: str,
    known_product_files: Dict[str, str],
) -> Path:
    """
    Resolves the final target filepath while strictly avoiding overwriting duplicate product names:
    - If the product URL was already saved to a path, returns that exact path.
    - If base_name.ext is claimed by a DIFFERENT product in this session, appends product identifier or numeric suffix.
    - If base_name.ext exists on disk and is unclaimed in this session, reuses it to allow duplicate download skipping.
    """
    if product_url in known_product_files:
        return Path(known_product_files[product_url])

    clean_ext = ext if ext.startswith(".") else f".{ext}"
    candidate_path = output_dir / f"{base_name}{clean_ext}"

    # Map paths to product URLs claimed in this session
    claimed_urls = {v: k for k, v in known_product_files.items()}

    # If the default filename is unclaimed or already claimed by this product
    if str(candidate_path) not in claimed_urls or claimed_urls.get(str(candidate_path)) == product_url:
        return candidate_path

    # The default filename is claimed by a DIFFERENT product in this session!
    # Try adding product ID / slug (e.g. 41565 from /drugs/dolo-650-tablet-41565)
    slug_id = None
    try:
        url_path = urlparse(product_url).path.rstrip("/")
        parts = url_path.split("/")[-1].split("-")
        if parts and parts[-1].isdigit():
            slug_id = parts[-1]
    except Exception:
        pass

    if slug_id:
        slug_candidate = output_dir / f"{base_name}_{slug_id}{clean_ext}"
        if str(slug_candidate) not in claimed_urls or claimed_urls.get(str(slug_candidate)) == product_url:
            return slug_candidate

    # Numeric suffix fallback (_1, _2, _3...)
    suffix = 1
    while True:
        suffixed_path = output_dir / f"{base_name}_{suffix}{clean_ext}"
        if str(suffixed_path) not in claimed_urls or claimed_urls.get(str(suffixed_path)) == product_url:
            return suffixed_path
        suffix += 1


async def download_image_file(
    client: httpx.AsyncClient,
    image_url: str,
    target_path: Path,
    chunk_size: int = 16384,
) -> Tuple[bool, int, Optional[str]]:
    """
    Incrementally streams an image directly to disk in chunks to handle thousands of
    images without high memory consumption.
    Uses an atomic .tmp file to guarantee no corrupted partial images exist on disk.
    Returns: (success: bool, bytes_downloaded: int, error_message: Optional[str])
    """
    try:
        # Validate URL scheme and safety
        safe_url, _ = validate_and_sanitize_url(image_url)
    except Exception as e:
        return False, 0, f"SSRF/URL validation failed: {str(e)}"

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(f"{target_path.suffix}.tmp_{uuid.uuid4().hex[:6]}")

    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "image/webp,image/avif,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.5",
        }
        async with client.stream("GET", safe_url, headers=headers) as resp:
            if resp.status_code != 200:
                return False, 0, f"HTTP error status: {resp.status_code}"

            total_bytes = 0
            with open(tmp_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        total_bytes += len(chunk)

            if total_bytes == 0:
                if tmp_path.exists():
                    tmp_path.unlink()
                return False, 0, "Downloaded 0 bytes (empty image file)"

            # Atomically replace destination file
            tmp_path.replace(target_path)
            return True, total_bytes, None

    except Exception as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        return False, 0, str(e)


def open_output_folder(folder_path: Optional[Path] = None) -> Tuple[bool, str, Optional[str]]:
    """
    Opens the target folder in the native OS desktop file explorer:
    - Windows: explorer.exe / os.startfile
    - macOS: open
    - Linux: xdg-open
    Returns: (success: bool, folder_path_str: str, error_message: Optional[str])
    """
    target = folder_path if folder_path is not None else OUTPUT_IMAGES_DIR
    target.mkdir(parents=True, exist_ok=True)
    abs_str = str(target.resolve())

    try:
        current_os = platform.system()
        if current_os == "Windows":
            os.startfile(abs_str)
            return True, abs_str, None
        elif current_os == "Darwin":
            subprocess.run(["open", abs_str], check=True)
            return True, abs_str, None
        else:
            subprocess.run(["xdg-open", abs_str], check=True)
            return True, abs_str, None
    except Exception as e:
        logger.warning(f"Could not open folder automatically: {str(e)}")
        return False, abs_str, str(e)


class ImageDownloaderRunner:
    """
    Mode C Background Engine:
    - Traverses listing pages using verified crawler pagination.
    - Discovers medicine names and image references.
    - Incrementally streams image downloads into output/medicine_images/.
    - Names files after actual medicine names with extension detection and duplicate collision avoidance.
    - Avoids re-downloading files that already exist on disk.
    - Tracks live counts and exposes progress for UI polling.
    """

    def __init__(
        self,
        listing_url: str,
        output_dir: Optional[Path] = None,
        max_pages: Optional[int] = None,
        max_images: Optional[int] = None,
        delay_seconds: float = 0.5,
        product_selector: Optional[str] = None,
        next_page_selector: Optional[str] = None,
    ):
        self.job_id = f"img_job_{uuid.uuid4().hex[:12]}"
        self.listing_url = listing_url
        self.output_dir = output_dir or OUTPUT_IMAGES_DIR
        self.max_pages = max_pages
        self.max_images = max_images
        self.delay_seconds = max(0.0, min(10.0, delay_seconds))
        self.product_selector = product_selector
        self.next_page_selector = next_page_selector

        # Live Job State
        self.job_status = "pending"
        self.start_time = datetime.now(timezone.utc).isoformat()
        self.last_updated_time = self.start_time
        self.completion_time: Optional[str] = None

        self.pages_visited = 0
        self.total_discovered = 0
        self.images_downloaded = 0
        self.images_skipped = 0
        self.images_failed = 0
        self.images_remaining = 0

        self.current_page_url: Optional[str] = None
        self.current_product_url: Optional[str] = None
        self.current_medicine_name: Optional[str] = None
        self.error_message: Optional[str] = None

        self.recent_downloads: List[Dict[str, Any]] = []
        self._known_product_files: Dict[str, str] = {}
        self._visited_page_urls: Set[str] = set()
        self._processed_product_urls: Set[str] = set()

        self._cancelled = False
        self._task: Optional[asyncio.Task] = None

    def start(self):
        """Launches the background download task."""
        self.job_status = "running"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._task = asyncio.create_task(self._run_job())

    def stop(self):
        """Gracefully stops the running job."""
        self._cancelled = True
        self.job_status = "stopped"
        self.last_updated_time = datetime.now(timezone.utc).isoformat()
        logger.info(f"Image download job {self.job_id} cancellation requested.")

    def to_dict(self) -> Dict[str, Any]:
        """Serializes current job state for API responses."""
        return {
            "job_id": self.job_id,
            "listing_url": self.listing_url,
            "job_status": self.job_status,
            "start_time": self.start_time,
            "last_updated_time": self.last_updated_time,
            "completion_time": self.completion_time,
            "pages_visited": self.pages_visited,
            "total_discovered": self.total_discovered,
            "images_downloaded": self.images_downloaded,
            "images_skipped": self.images_skipped,
            "images_failed": self.images_failed,
            "images_remaining": max(0, self.total_discovered - (self.images_downloaded + self.images_skipped + self.images_failed)),
            "current_page_url": self.current_page_url,
            "current_product_url": self.current_product_url,
            "current_medicine_name": self.current_medicine_name,
            "output_dir": str(self.output_dir.resolve()),
            "error_message": self.error_message,
            "recent_downloads": self.recent_downloads[-15:],
        }

    async def _run_job(self):
        logger.info(f"Starting Mode C image download job {self.job_id} for: {self.listing_url}")
        current_page_url = self.listing_url
        scope = extract_listing_scope(self.listing_url)

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as http_client:
            while current_page_url and not self._cancelled:
                # Check maximum page limit if specified
                if self.max_pages and self.pages_visited >= self.max_pages:
                    logger.info(f"Job {self.job_id} reached max_pages limit ({self.max_pages}).")
                    break

                self.current_page_url = current_page_url
                self._visited_page_urls.add(current_page_url)
                self.pages_visited += 1
                self.last_updated_time = datetime.now(timezone.utc).isoformat()

                try:
                    page_html, _, _ = await fetch_html(current_page_url)
                except Exception as e:
                    logger.warning(f"Failed to fetch listing page {current_page_url}: {str(e)}")
                    self.images_failed += 1
                    # Attempt next page
                    break

                # 1. Discover product links on this listing page
                discovered_urls = extract_product_links(
                    raw_html=page_html,
                    base_url=current_page_url,
                    custom_selector=self.product_selector,
                )

                # Update discovered count
                new_products = [u for u in discovered_urls if u not in self._processed_product_urls]
                self.total_discovered += len(new_products)

                # Process products discovered on this page incrementally
                for prod_url in discovered_urls:
                    if self._cancelled:
                        break

                    # Check max images limit
                    if self.max_images and (self.images_downloaded >= self.max_images):
                        logger.info(f"Job {self.job_id} reached max_images limit ({self.max_images}).")
                        break

                    if prod_url in self._processed_product_urls:
                        continue

                    self._processed_product_urls.add(prod_url)
                    self.current_product_url = prod_url
                    self.last_updated_time = datetime.now(timezone.utc).isoformat()

                    await self._process_single_product(http_client, prod_url)

                    if self.delay_seconds > 0:
                        await asyncio.sleep(self.delay_seconds)

                if self._cancelled:
                    break

                if self.max_images and (self.images_downloaded >= self.max_images):
                    break

                # 2. Determine Next Listing Page using verified pagination
                if is_explicit_last_page(page_html):
                    logger.info(f"Listing page {current_page_url} marked as explicit last page.")
                    break

                next_url = extract_next_page_link(
                    raw_html=page_html,
                    base_url=self.listing_url,
                    current_page_url=current_page_url,
                    custom_selector=self.next_page_selector,
                    visited_urls=self._visited_page_urls,
                )

                if not next_url and discovered_urls:
                    next_url = get_fallback_next_page_url(
                        current_page_url=current_page_url,
                        scope=scope,
                        visited_urls=self._visited_page_urls,
                    )

                if not next_url or next_url in self._visited_page_urls:
                    logger.info(f"Pagination endpoint reached for job {self.job_id}.")
                    break

                current_page_url = next_url

        # Finalize job status
        self.completion_time = datetime.now(timezone.utc).isoformat()
        self.last_updated_time = self.completion_time
        if self._cancelled:
            self.job_status = "stopped"
        else:
            self.job_status = "completed"

        self.current_product_url = None
        self.current_medicine_name = None
        logger.info(
            f"Image job {self.job_id} finished with status: {self.job_status}. "
            f"Downloaded: {self.images_downloaded}, Skipped: {self.images_skipped}, Failed: {self.images_failed}"
        )

    async def _process_single_product(self, client: httpx.AsyncClient, product_url: str):
        """Fetches a single medicine detail page, discovers its image, and streams it to disk."""
        try:
            prod_html, _, _ = await fetch_html(product_url)
        except Exception as e:
            logger.warning(f"Could not fetch product {product_url}: {str(e)}")
            self.images_failed += 1
            return

        med_name, img_url = extract_medicine_name_and_image(prod_html, product_url)
        self.current_medicine_name = med_name

        if not img_url:
            logger.info(f"No image found for medicine '{med_name}' ({product_url}). Skipping.")
            self.images_failed += 1
            return

        # Sanitize filename based on actual medicine name
        sanitized_name = sanitize_medicine_filename(med_name)
        ext = detect_image_extension(img_url)

        target_file = resolve_unique_filename(
            output_dir=self.output_dir,
            base_name=sanitized_name,
            ext=ext,
            product_url=product_url,
            known_product_files=self._known_product_files,
        )

        # Check if file already exists with non-zero size (avoid duplicate downloads)
        if target_file.exists() and target_file.stat().st_size > 0:
            self._known_product_files[product_url] = str(target_file)
            self.images_skipped += 1
            logger.info(f"Image already exists on disk: {target_file.name}. Skipped download.")
            self.recent_downloads.append({
                "medicine_name": med_name,
                "filename": target_file.name,
                "status": "skipped_exists",
                "size_bytes": target_file.stat().st_size,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return

        # Incrementally download and stream to disk
        success, size_bytes, err = await download_image_file(client, img_url, target_file)
        if success:
            self._known_product_files[product_url] = str(target_file)
            self.images_downloaded += 1
            logger.info(f"Saved image: {target_file.name} ({size_bytes} bytes)")
            self.recent_downloads.append({
                "medicine_name": med_name,
                "filename": target_file.name,
                "status": "downloaded",
                "size_bytes": size_bytes,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        else:
            self.images_failed += 1
            logger.warning(f"Failed to download image for '{med_name}' ({img_url}): {err}")
            self.recent_downloads.append({
                "medicine_name": med_name,
                "filename": target_file.name,
                "status": "failed",
                "error": err,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })


# Global dictionary storing active and recently finished Mode C runners
active_image_jobs: Dict[str, ImageDownloaderRunner] = {}


def start_image_download_job(
    listing_url: str,
    output_dir: Optional[Path] = None,
    max_pages: Optional[int] = None,
    max_images: Optional[int] = None,
    delay_seconds: float = 0.5,
    product_selector: Optional[str] = None,
    next_page_selector: Optional[str] = None,
) -> ImageDownloaderRunner:
    """Creates and starts a new Mode C background image downloader runner."""
    runner = ImageDownloaderRunner(
        listing_url=listing_url,
        output_dir=output_dir,
        max_pages=max_pages,
        max_images=max_images,
        delay_seconds=delay_seconds,
        product_selector=product_selector,
        next_page_selector=next_page_selector,
    )
    active_image_jobs[runner.job_id] = runner
    runner.start()
    return runner
