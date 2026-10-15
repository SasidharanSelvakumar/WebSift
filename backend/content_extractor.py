import html
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup, Tag, NavigableString

from backend.models import ExtractedItem, ExtractionStats

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
BLOCK_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote",
    "pre", "article", "section", "dt", "dd", "caption", "figcaption", "td", "th"
}
NESTED_BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "blockquote", "pre", "div", "section", "article"}



def normalize_text(text: str) -> str:
    """
    Cleans raw text: unescapes HTML entities, strips control chars,
    and normalizes multiple whitespace / tabs into single spaces.
    """
    if not text:
        return ""
    unescaped = html.unescape(text)
    # Replace non-breaking spaces and zero-width spaces
    cleaned = unescaped.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")
    # Normalize internal whitespace while preserving readable words
    return " ".join(cleaned.split())


def extract_table_rows(table: Tag) -> List[Tuple[str, str]]:
    """
    Extracts structured rows from an HTML table.
    Returns list of (formatted_row_text, row_type).
    """
    rows = []
    # Identify headers if available
    headers: List[str] = []
    header_tr = table.find("tr")
    if header_tr:
        th_tags = header_tr.find_all("th")
        if th_tags:
            headers = [normalize_text(th.get_text()) for th in th_tags]

    # Process all tr elements
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue

        cell_values = [normalize_text(cell.get_text()) for cell in cells]
        # Ignore completely empty rows
        if not any(cell_values):
            continue

        is_header_row = all(c.name == "th" for c in cells)

        if is_header_row:
            row_text = " | ".join(cell_values)
            rows.append((row_text, "table_header"))
            if not headers:
                headers = cell_values
        else:
            # Pair with header names if header count matches cell count
            if headers and len(headers) == len(cell_values):
                row_parts = [f"{h}: {v}" if v else h for h, v in zip(headers, cell_values)]
                row_text = " | ".join(row_parts)
            else:
                row_text = " | ".join(cell_values)

            rows.append((row_text, "table_row"))

    return rows


def extract_structured_content(
    root: Tag,
    source_url: str,
    page_title: str,
    extracted_at: Optional[str] = None,
) -> Tuple[List[ExtractedItem], ExtractionStats, str]:
    """
    Traverses the cleaned DOM tree in reading order and extracts structured records.
    Associates each block with the active section heading.
    Returns: (items, stats, full_text_preview)
    """
    if extracted_at is None:
        extracted_at = datetime.now(timezone.utc).isoformat()

    items: List[ExtractedItem] = []
    sequence = 1
    current_heading: Optional[str] = None
    seen_texts: set = set()

    # Document statistics counters
    headings_count = 0
    paragraphs_count = 0
    lists_count = 0
    tables_count = 0

    # Add page title as the initial item if available
    if page_title and page_title != "Untitled Page":
        items.append(
            ExtractedItem(
                sequence_number=sequence,
                source_url=source_url,
                page_title=page_title,
                content_type="page_title",
                heading=None,
                text_content=page_title,
                extracted_at=extracted_at,
            )
        )
        sequence += 1
        current_heading = page_title
        headings_count += 1

    # Traverse elements in depth-first order
    processed_tags = set()

    for element in root.find_all(True):
        if id(element) in processed_tags:
            continue

        tag_name = element.name.lower()

        # 1. Headings (h1 - h6)
        if tag_name in HEADING_TAGS:
            text = normalize_text(element.get_text())
            if text and len(text) > 1 and text not in seen_texts:
                level = tag_name[-1]
                content_type = f"heading_{level}"
                current_heading = text
                seen_texts.add(text)
                headings_count += 1

                items.append(
                    ExtractedItem(
                        sequence_number=sequence,
                        source_url=source_url,
                        page_title=page_title,
                        content_type=content_type,
                        heading=current_heading,
                        text_content=text,
                        extracted_at=extracted_at,
                    )
                )
                sequence += 1
            processed_tags.add(id(element))

        # 2. Tables
        elif tag_name == "table":
            table_rows = extract_table_rows(element)
            for row_text, row_type in table_rows:
                if row_text and row_text not in seen_texts:
                    seen_texts.add(row_text)
                    tables_count += 1
                    items.append(
                        ExtractedItem(
                            sequence_number=sequence,
                            source_url=source_url,
                            page_title=page_title,
                            content_type=row_type,
                            heading=current_heading,
                            text_content=row_text,
                            extracted_at=extracted_at,
                        )
                    )
                    sequence += 1
            # Mark all descendant elements as processed so we don't duplicate table cells
            for desc in element.find_all(True):
                processed_tags.add(id(desc))
            processed_tags.add(id(element))

        # 3. List items (li)
        elif tag_name == "li":
            text = normalize_text(element.get_text())
            if text and len(text) > 1 and text not in seen_texts:
                seen_texts.add(text)
                lists_count += 1

                # Check if ordered list
                parent = element.parent
                prefix = ""
                if parent and parent.name == "ol":
                    # Determine list item index
                    index = element.parent.index(element) + 1 if element in element.parent.children else 1
                    prefix = f"{index}. "
                else:
                    prefix = "• "

                formatted_item = f"{prefix}{text}" if not text.startswith(("•", "-", "*", "1.", "2.")) else text

                items.append(
                    ExtractedItem(
                        sequence_number=sequence,
                        source_url=source_url,
                        page_title=page_title,
                        content_type="list_item",
                        heading=current_heading,
                        text_content=formatted_item,
                        extracted_at=extracted_at,
                    )
                )
                sequence += 1
            # Mark children inside li as processed to avoid double counting
            for desc in element.find_all(True):
                processed_tags.add(id(desc))
            processed_tags.add(id(element))

        # 4. Paragraphs, Blockquotes, and Leaf Text Containers
        elif tag_name in ("p", "blockquote", "pre", "dt", "dd", "figcaption", "div", "section"):
            if tag_name in ("div", "section"):
                # Treat div/section as a text block only if it has no nested block containers
                has_child_blocks = any(c.name in NESTED_BLOCK_TAGS for c in element.find_all(True))
                if has_child_blocks:
                    continue

            text = normalize_text(element.get_text())
            # Don't capture tiny 1-2 char noise or duplicated text
            if text and len(text) > 3 and text not in seen_texts:
                seen_texts.add(text)
                ctype = "paragraph"
                if tag_name == "blockquote":
                    ctype = "blockquote"
                elif tag_name == "pre":
                    ctype = "code_block"
                elif tag_name in ("dt", "dd"):
                    ctype = "definition"
                elif tag_name == "figcaption":
                    ctype = "caption"

                paragraphs_count += 1
                items.append(
                    ExtractedItem(
                        sequence_number=sequence,
                        source_url=source_url,
                        page_title=page_title,
                        content_type=ctype,
                        heading=current_heading,
                        text_content=text,
                        extracted_at=extracted_at,
                    )
                )
                sequence += 1
            for desc in element.find_all(True):
                processed_tags.add(id(desc))
            processed_tags.add(id(element))

        # 5. Meaningful standalone links outside paragraphs
        elif tag_name == "a":
            # If not already inside a paragraph/list/table
            text = normalize_text(element.get_text())
            href = element.get("href", "").strip()
            # Must have non-trivial text and not be a jump anchor '#'
            if text and len(text) > 3 and href and not href.startswith("#") and text not in seen_texts:
                seen_texts.add(text)
                items.append(
                    ExtractedItem(
                        sequence_number=sequence,
                        source_url=source_url,
                        page_title=page_title,
                        content_type="link",
                        heading=current_heading,
                        text_content=f"{text} [Link: {href}]" if not href.startswith("javascript") else text,
                        extracted_at=extracted_at,
                    )
                )
                sequence += 1
            processed_tags.add(id(element))

    # Fallback: if no blocks were matched (e.g. text in divs without <p> tags)
    if len(items) <= 1:
        # Extract general text lines from root
        lines = [normalize_text(line) for line in root.get_text("\n").split("\n")]
        for line in lines:
            if line and len(line) > 10 and line not in seen_texts:
                seen_texts.add(line)
                items.append(
                    ExtractedItem(
                        sequence_number=sequence,
                        source_url=source_url,
                        page_title=page_title,
                        content_type="text_block",
                        heading=current_heading,
                        text_content=line,
                        extracted_at=extracted_at,
                    )
                )
                sequence += 1
                paragraphs_count += 1

    # Compute Statistics
    all_text = " ".join(item.text_content for item in items)
    words = all_text.split()
    word_count = len(words)
    char_count = len(all_text)
    # Average adult reading speed: 200 words per minute
    reading_time = round(word_count / 200.0, 1)

    stats = ExtractionStats(
        block_count=len(items),
        word_count=word_count,
        character_count=char_count,
        reading_time_minutes=reading_time,
        headings_count=headings_count,
        paragraphs_count=paragraphs_count,
        lists_count=lists_count,
        tables_count=tables_count,
    )

    # Build readable full text preview
    preview_lines = []
    for item in items:
        if item.content_type.startswith("heading"):
            preview_lines.append(f"\n## {item.text_content}\n")
        elif item.content_type == "list_item":
            preview_lines.append(f"  {item.text_content}")
        elif item.content_type in ("table_row", "table_header"):
            preview_lines.append(f"  [Table] {item.text_content}")
        elif item.content_type == "page_title":
            preview_lines.append(f"# {item.text_content}\n")
        else:
            preview_lines.append(f"{item.text_content}\n")

    full_text_preview = "\n".join(preview_lines).strip()

    return items, stats, full_text_preview
