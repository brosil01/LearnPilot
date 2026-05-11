"""
pdf_service.py — LearnPilot PDF Resource Service v4

New: parse_subtopics() — extracts section headings within a chapter
     so we can build a learning plan and teach one section at a time.
"""

import re
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("LearnPilot")

UPLOAD_DIR    = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
METADATA_FILE = UPLOAD_DIR / "metadata.json"


def load_metadata() -> dict:
    if METADATA_FILE.exists():
        try:
            return json.loads(METADATA_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_metadata(meta: dict):
    METADATA_FILE.write_text(json.dumps(meta, indent=2))


def get_uploaded_files() -> list[dict]:
    meta = load_metadata()
    return [
        {"id": k, "name": v["name"], "pages": v.get("pages", 0)}
        for k, v in meta.items()
    ]


def extract_pages(pdf_path: Path, page_start: int = 1, page_end: int = None) -> tuple[str, int]:
    """Extract text from specific pages. Pages are 1-indexed."""
    try:
        import PyPDF2
        text_parts = []
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            total  = len(reader.pages)
            end    = min(page_end or total, total)
            start  = max(0, page_start - 1)
            for i in range(start, end):
                page_text = reader.pages[i].extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"[Page {i+1}]\n{page_text}")
        return "\n\n".join(text_parts), total
    except Exception as e:
        logger.error(f"[PDF] Extraction failed: {e}")
        return "", 0


def parse_toc(pdf_path: Path) -> dict:
    """Parse TOC → {chapter_num: start_page}"""
    toc_text, total_pages = extract_pages(pdf_path, 1, 30)
    if not toc_text:
        return {}

    chapter_pages = {}
    for m in re.finditer(
        r"chapter\s+(\d+)[^\n]{0,60}?(\d{1,4})\s*$",
        toc_text, re.IGNORECASE | re.MULTILINE
    ):
        ch, pg = int(m.group(1)), int(m.group(2))
        if 1 <= pg <= total_pages and ch not in chapter_pages:
            chapter_pages[ch] = pg
            logger.info(f"[PDF-TOC] Chapter {ch} → page {pg}")

    if not chapter_pages:
        for m in re.finditer(
            r"^(\d+)\.\s+[A-Z][^\n]{0,60}?(\d{1,4})\s*$",
            toc_text, re.MULTILINE
        ):
            ch, pg = int(m.group(1)), int(m.group(2))
            if 1 <= pg <= total_pages and ch <= 30:
                chapter_pages[ch] = pg

    logger.info(f"[PDF-TOC] Found {len(chapter_pages)} chapters: {chapter_pages}")
    return chapter_pages


def parse_subtopics(pdf_path: Path, chapter_num: int, toc_map: dict) -> list[dict]:
    """
    Parse section headings within a chapter to build a learning plan.

    For Tipler Ch1: finds 1-1, 1-2, 1-3, 1-4, 1-5, 1-6 from the TOC pages
    and maps them to page numbers.

    Returns list of:
      {"title": "1-1 The Experimental Basis", "page_start": 4, "page_end": 10}
    """
    subtopics = []

    if chapter_num not in toc_map:
        return subtopics

    ch_start = toc_map[chapter_num]
    ch_end   = toc_map.get(chapter_num + 1, ch_start + 62) - 1

    # Read TOC pages (first 30 pages) to find section headings + page numbers
    toc_text, total_pages = extract_pages(pdf_path, 1, 30)

    # DEBUG: log raw lines containing chapter-section numbers
    debug_lines = [l for l in toc_text.split('\n') if f'{chapter_num}-' in l]
    logger.info(f'[PDF-DEBUG] Lines with chapter-N: {debug_lines}')


    # Pattern: "1-1  The Experimental Basis of Relativity  4"
    # Section numbering format: "N-M  Title  PageNum"
    section_pattern = re.compile(
        rf"{chapter_num}-(\d+)[^\n]{{0,20}}?([A-Z][A-Za-z0-9/,;:\- ]+?)\s+(\d{{1,4}})[A-Za-z]*\s*$",
        re.MULTILINE
    )

    raw_sections = []
    for m in section_pattern.finditer(toc_text):
        sec_num  = int(m.group(1))
        title    = m.group(2).strip()
        pg       = int(m.group(3))
        if ch_start <= pg <= ch_end:
            raw_sections.append({
                "section": f"{chapter_num}-{sec_num}",
                "title":   title,
                "page":    pg,
            })

    logger.info(f'[PDF-DEBUG] Pattern matched {len(raw_sections)} sections for Ch{chapter_num}')

    if not raw_sections:
        logger.info(f"[PDF] No subsections found for Ch{chapter_num} — treating as one block")
        # No subsections found — split chapter into ~3 even chunks
        chunk_size = max(5, (ch_end - ch_start) // 3)
        for i, pg in enumerate(range(ch_start, ch_end, chunk_size)):
            subtopics.append({
                "title":      f"Chapter {chapter_num} Part {i+1}",
                "page_start": pg,
                "page_end":   min(pg + chunk_size - 1, ch_end),
                "section":    f"{chapter_num}.{i+1}",
            })
        return subtopics

    # Deduplicate — keep only FIRST occurrence of each section number
    seen_sections = set()
    unique_sections = []
    for sec in raw_sections:
        if sec["section"] not in seen_sections:
            seen_sections.add(sec["section"])
            unique_sections.append(sec)

    # Sort by page number to ensure correct order
    unique_sections.sort(key=lambda x: x["page"])

    # Build page ranges
    for i, sec in enumerate(unique_sections):
        next_pg = unique_sections[i+1]["page"] - 1 if i + 1 < len(unique_sections) else ch_end
        subtopics.append({
            "title":      f"{sec['section']} {sec['title']}",
            "page_start": sec["page"],
            "page_end":   min(next_pg, ch_end),
            "section":    sec["section"],
        })

    # Debug: show exact lines from PDF containing section references
    debug_lines = [l for l in toc_text.split("\n") if f"{chapter_num}-" in l and l.strip()]
    logger.info(f"[PDF-DEBUG] Raw TOC lines for Ch{chapter_num}: {debug_lines[:20]}")

    logger.info(f"[PDF] Ch{chapter_num} subtopics ({len(subtopics)}): {[s['title'] for s in subtopics]}")
    return subtopics


def get_chunk_context(file_id: str, page_start: int, page_end: int) -> str:
    """Extract text for a specific page range — used for chunked teaching."""
    meta = load_metadata()
    if file_id not in meta:
        return ""

    pdf_path = Path(meta[file_id]["path"])
    if not pdf_path.exists():
        return ""

    text, _ = extract_pages(pdf_path, page_start, page_end)
    filename = meta[file_id]["name"]
    label    = f"[From: {filename} — pages {page_start}–{page_end}]"
    return f"{label}\n\n{text[:5000]}" if text else ""


def extract_chapter_text(pdf_path: Path, chapter_ref: str, toc_map: dict = None) -> str:
    chapter_ref_lower = chapter_ref.lower().strip()
    _, total_pages = extract_pages(pdf_path, 1, 1)

    chapter_num = None
    page_start  = None
    page_end    = None

    pr = re.search(r"pages?\s+(\d+)\s*(?:-|to|–)\s*(\d+)", chapter_ref_lower)
    if pr:
        page_start, page_end = int(pr.group(1)), int(pr.group(2))

    if not page_start:
        cm = re.search(
            r"(?:chapter|ch|unit|section|part)\s*"
            r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)",
            chapter_ref_lower
        )
        if cm:
            word_map = {"one":1,"two":2,"three":3,"four":4,"five":5,
                        "six":6,"seven":7,"eight":8,"nine":9,"ten":10}
            chapter_num = word_map.get(cm.group(1)) or int(cm.group(1))
        else:
            nm = re.search(r"^\d+$", chapter_ref_lower)
            if nm:
                chapter_num = int(nm.group())

    if page_start and page_end:
        text, _ = extract_pages(pdf_path, page_start, page_end)
        return text[:5000]

    if chapter_num is not None and toc_map and chapter_num in toc_map:
        ch_start = toc_map[chapter_num]
        ch_end   = toc_map.get(chapter_num + 1, ch_start + 60) - 1
        logger.info(f"[PDF] TOC: Chapter {chapter_num} = pages {ch_start}–{ch_end}")
        text, _ = extract_pages(pdf_path, ch_start, ch_end)
        if text:
            return text[:5000]

    if chapter_num is not None:
        body_text, _ = extract_pages(pdf_path, 31, total_pages)
        page_pos = {int(m.group(1)): m.start()
                    for m in re.finditer(r"\[Page (\d+)\]", body_text)}
        heading_pos = None
        for pat in [rf"\bchapter\s+{chapter_num}\b", rf"\bCHAPTER\s+{chapter_num}\b"]:
            m = re.search(pat, body_text, re.IGNORECASE)
            if m:
                heading_pos = m.start(); break

        if heading_pos is not None:
            heading_page = max((pg for pg, pos in page_pos.items() if pos <= heading_pos), default=31)
            text, _ = extract_pages(pdf_path, heading_page, heading_page + 60)
            if text:
                return text[:5000]

    if chapter_num is not None:
        skip, per_ch = 20, max(15, (total_pages - 20) // 12)
        est_start    = skip + (chapter_num - 1) * per_ch + 1
        text, _      = extract_pages(pdf_path, est_start, est_start + per_ch - 1)
        return text[:5000]

    text, _ = extract_pages(pdf_path, 1, 10)
    return text[:2000]


async def save_pdf(file_bytes: bytes, filename: str) -> dict:
    import hashlib
    file_id   = hashlib.md5(file_bytes).hexdigest()[:12]
    safe_name = re.sub(r"[^\w\-.]", "_", filename)
    pdf_path  = UPLOAD_DIR / f"{file_id}_{safe_name}"
    pdf_path.write_bytes(file_bytes)

    _, page_count = extract_pages(pdf_path, 1, 1)
    toc_map       = parse_toc(pdf_path)

    meta = load_metadata()
    meta[file_id] = {
        "name":    filename,
        "path":    str(pdf_path),
        "pages":   page_count,
        "toc_map": toc_map,
    }
    save_metadata(meta)
    logger.info(f"[PDF] Saved '{filename}' ({page_count}p, TOC: {toc_map})")
    return {"id": file_id, "name": filename, "pages": page_count}


def get_pdf_context(file_id: str, chapter_ref: Optional[str] = None) -> str:
    meta = load_metadata()
    if file_id not in meta:
        return ""
    pdf_path = Path(meta[file_id]["path"])
    if not pdf_path.exists():
        return ""

    toc_map  = {int(k): v for k, v in meta[file_id].get("toc_map", {}).items()}
    filename = meta[file_id]["name"]

    if chapter_ref:
        text  = extract_chapter_text(pdf_path, chapter_ref, toc_map)
        label = f"[From: {filename} — {chapter_ref}]"
    else:
        text, _ = extract_pages(pdf_path, 1, 10)
        text     = text[:2000]
        label    = f"[From: {filename}]"

    return f"{label}\n\n{text}" if text else ""


def get_learning_plan(file_id: str, chapter_ref: str) -> list[dict]:
    """
    Build a learning plan — list of subtopics with page ranges.
    Called by /plan endpoint. Frontend uses this to drive Next button.
    """
    meta = load_metadata()
    if file_id not in meta:
        return []

    pdf_path = Path(meta[file_id]["path"])
    if not pdf_path.exists():
        return []

    toc_map = {int(k): v for k, v in meta[file_id].get("toc_map", {}).items()}

    # Extract chapter number from ref
    cm = re.search(r"(?:chapter|ch)\s*(\d+)", chapter_ref, re.IGNORECASE)
    if not cm:
        return []

    chapter_num = int(cm.group(1))
    return parse_subtopics(pdf_path, chapter_num, toc_map)


def delete_pdf(file_id: str) -> bool:
    meta = load_metadata()
    if file_id not in meta:
        return False
    try:
        Path(meta[file_id]["path"]).unlink(missing_ok=True)
        del meta[file_id]
        save_metadata(meta)
        return True
    except Exception as e:
        logger.error(f"[PDF] Delete failed: {e}")
        return False
