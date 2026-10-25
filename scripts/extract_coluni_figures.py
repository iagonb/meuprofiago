#!/usr/bin/env python3
"""Crop raster and vector figures from COLUNI PDFs and add them to LaTeX.

Poppler reports the positions of embedded images. PyMuPDF supplies bounding
boxes for vector drawings such as geometry diagrams. Crops are written one
per question and referenced from editable question sources with figure
environments.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import pymupdf
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "static/simulados/coluni/questions.json"
PDF_DIR = ROOT / "static/simulados/coluni/provas"
SOURCE_DIR = ROOT / "data/coluni/latex-source"
IMAGE_DIR = ROOT / "static/simulados/coluni/figuras"
MANIFEST = ROOT / "data/coluni/figures-manifest.json"
START_MARKER = "% COLUNI-AUTO-FIGURES-BEGIN"
END_MARKER = "% COLUNI-AUTO-FIGURES-END"
RENDER_DPI = 180
PDHTML_ZOOM = 1.5
MIN_IMAGE_WIDTH = 50
MIN_IMAGE_HEIGHT = 25
MIN_IMAGE_AREA = 2000

# Some PDFs store text glyphs as vector paths. A visual inspection of all
# extracted vector candidates found only these three real diagrams.
VECTOR_FIGURE_QUESTIONS = {"2018-23", "2020-23", "2025-12"}
SHARED_FIGURES = {
    "2022-03": "2022-02",
    "2022-04": "2022-02",
    "2024-02": "2024-01",
    "2026-06": "2026-05",
}

Box = tuple[float, float, float, float]


def element_text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def question_starts(root: ET.Element, questions: list[dict]) -> list[tuple[int, float, dict]]:
    starts = []
    for question in questions:
        page_number = question["page"]
        page = root.find(f"page[@number='{page_number}']")
        if page is None:
            raise ValueError(f"Página {page_number} ausente no PDF de {question['year']}.")
        rows: dict[int, list[tuple[float, str]]] = defaultdict(list)
        for item in page.findall("text"):
            top = round(float(item.attrib["top"]))
            rows[top].append((float(item.attrib["left"]), element_text(item)))
        candidates = []
        for top, cells in rows.items():
            cells.sort()
            line = re.sub(r"\s+", " ", " ".join(text for _, text in cells)).strip()
            if re.match(rf"^0?{question['number']}\s*\.", line) and cells[0][0] < 160:
                candidates.append((top, cells[0][0]))
        if not candidates:
            raise ValueError(f"Cabeçalho da questão {question['id']} não localizado no PDF.")
        top, _left = min(candidates, key=lambda value: (value[1], value[0]))
        starts.append((page_number, float(top), question))
    return sorted(starts, key=lambda value: (value[0], value[1]))


def image_groups(page: ET.Element) -> list[Box]:
    boxes = []
    for image in page.findall("image"):
        left, top = float(image.attrib["left"]), float(image.attrib["top"])
        width, height = float(image.attrib["width"]), float(image.attrib["height"])
        if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT or width * height < MIN_IMAGE_AREA:
            continue
        boxes.append((left, top, left + width, top + height))
    return merge_overlapping(boxes, overlap_threshold=0.35)


def merge_overlapping(boxes: list[Box], overlap_threshold: float) -> list[Box]:
    groups: list[list[Box]] = []
    for box in boxes:
        joined = []
        for index, group in enumerate(groups):
            for other in group:
                overlap_w = max(0.0, min(box[2], other[2]) - max(box[0], other[0]))
                overlap_h = max(0.0, min(box[3], other[3]) - max(box[1], other[1]))
                overlap = overlap_w * overlap_h
                smaller = min((box[2] - box[0]) * (box[3] - box[1]), (other[2] - other[0]) * (other[3] - other[1]))
                if smaller and overlap / smaller >= overlap_threshold:
                    joined.append(index)
                    break
        if not joined:
            groups.append([box])
        else:
            base = joined[0]
            groups[base].append(box)
            for extra in reversed(joined[1:]):
                groups[base].extend(groups.pop(extra))
    return sorted([
        (min(b[0] for b in group), min(b[1] for b in group), max(b[2] for b in group), max(b[3] for b in group))
        for group in groups
    ], key=lambda box: (box[1], box[0]))


def vector_groups(page: pymupdf.Page) -> list[Box]:
    boxes = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        width, height = rect.width, rect.height
        area = max(width, 1.0) * max(height, 1.0)
        # This removes page rules and small text underlines while retaining
        # connected lines, polygons, graphs, and geometry constructions.
        if width < 15 or height < 10:
            continue
        if width > 550 or height > 600 or area < 25:
            continue
        boxes.append((rect.x0 * PDHTML_ZOOM, rect.y0 * PDHTML_ZOOM,
                      rect.x1 * PDHTML_ZOOM, rect.y1 * PDHTML_ZOOM))

    # Paths that form a single vector illustration tend to touch or sit only
    # a few points apart. Merge these before filtering by final figure size.
    groups: list[list[Box]] = []
    for box in boxes:
        near = []
        for index, group in enumerate(groups):
            for other in group:
                dx = max(0.0, max(box[0] - other[2], other[0] - box[2]))
                dy = max(0.0, max(box[1] - other[3], other[1] - box[3]))
                if dx <= 8 and dy <= 8:
                    near.append(index)
                    break
        if not near:
            groups.append([box])
        else:
            base = near[0]
            groups[base].append(box)
            for extra in reversed(near[1:]):
                groups[base].extend(groups.pop(extra))

    result = []
    for group in groups:
        box = (min(b[0] for b in group), min(b[1] for b in group), max(b[2] for b in group), max(b[3] for b in group))
        width, height = box[2] - box[0], box[3] - box[1]
        if width >= 35 and height >= 25 and width * height >= 1000:
            result.append(box)
    return sorted(result, key=lambda box: (box[1], box[0]))


def overlaps(left: Box, right: Box, threshold: float = 0.25) -> bool:
    width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    area = width * height
    smaller = min((left[2] - left[0]) * (left[3] - left[1]), (right[2] - right[0]) * (right[3] - right[1]))
    return bool(smaller and area / smaller >= threshold)


def owner_for(page_number: int, top: float, starts: list[tuple[int, float, dict]]) -> dict | None:
    same_page = [item for item in starts if item[0] == page_number]
    earlier_here = [item for item in same_page if item[1] <= top]
    later_here = [item for item in same_page if item[1] > top]
    if earlier_here:
        return earlier_here[-1][2]
    if later_here:
        return later_here[0][2]
    prior_pages = [item for item in starts if item[0] < page_number]
    later_pages = [item for item in starts if item[0] > page_number]
    chosen = prior_pages[-1] if prior_pages else (later_pages[0] if later_pages else None)
    return chosen[2] if chosen else None


def insert_figure_blocks(source: Path, entries: list[dict]) -> None:
    text = source.read_text(encoding="utf-8")
    text = re.sub(r"^\\begin\{minipage\}\{\\linewidth\}\\raggedright\s*", "", text, count=1)
    text = re.sub(r"\\\\\[\.\d+em\]", lambda _match: r"\par\medskip", text, count=1)
    text = re.sub(r"\\end\{minipage\}\s*$", "", text)
    markers = re.compile(
        rf"(?ms)\s*% COLUNI-AUTO-FIGURES-BEGIN\n.*?"
        rf"% COLUNI-AUTO-FIGURES-END\s*"
    )
    text = markers.sub("", text)
    if not entries:
        source.write_text(text.strip() + "\n", encoding="utf-8")
        return

    blocks = [START_MARKER]
    for entry in entries:
        blocks.extend([
            r"\begin{figure}[htbp]",
            r"\centering",
            rf"\includegraphics[width=0.95\linewidth]{{{entry['texPath']}}}",
            r"\end{figure}",
        ])
    blocks.append(END_MARKER)
    figures = "\n\n" + "\n".join(blocks) + "\n"
    choices = text.find(r"\begin{enumerate}")
    if choices >= 0:
        text = text[:choices] + figures + text[choices:]
    else:
        text = text.rstrip() + "\n\n" + figures
    source.write_text(text.strip() + "\n", encoding="utf-8")


def remove_old_crops() -> None:
    if IMAGE_DIR.exists():
        shutil.rmtree(IMAGE_DIR)


def crop_candidates(pdf: Path, page_xml: dict[int, ET.Element], starts: list[tuple[int, float, dict]], year_questions: list[dict]) -> dict[str, list[dict]]:
    document = pymupdf.open(pdf)
    candidates_by_page: dict[int, list[dict]] = defaultdict(list)
    for page_number, page in page_xml.items():
        raster_boxes = image_groups(page)
        for box in raster_boxes:
            owner = owner_for(page_number, box[1], starts)
            if owner and owner.get("transcriptionSource") == "pdf-text":
                candidates_by_page[page_number].append({"question": owner, "box": box, "type": "raster"})

        pdf_page = document[page_number - 1]
        for box in vector_groups(pdf_page):
            if any(overlaps(box, raster) for raster in raster_boxes):
                continue
            owner = owner_for(page_number, box[1], starts)
            visual_terms = re.search(r"figura|imagem|gr[aá]fico|infogr[aá]fico|circuito|mapa|tirinha|charge|desenho|diagrama|cartum|ilustra|geometr", (owner or {}).get("latex", ""), re.IGNORECASE)
            if (owner and owner.get("transcriptionSource") == "pdf-text"
                    and owner["id"] in VECTOR_FIGURE_QUESTIONS and visual_terms):
                candidates_by_page[page_number].append({"question": owner, "box": box, "type": "vector"})

    result: dict[str, list[dict]] = defaultdict(list)
    with tempfile.TemporaryDirectory(prefix=f"coluni-crops-{pdf.stem}-") as temp_dir:
        temp = Path(temp_dir)
        for page_number, candidates in candidates_by_page.items():
            if not candidates:
                continue
            prefix = temp / f"page-{page_number}"
            subprocess.run([
                "pdftoppm", "-r", str(RENDER_DPI), "-png", "-singlefile",
                "-f", str(page_number), "-l", str(page_number), str(pdf), str(prefix),
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            rendered = Image.open(Path(str(prefix) + ".png")).convert("RGB")
            xml_page = page_xml[page_number]
            scale_x = rendered.width / float(xml_page.attrib["width"])
            scale_y = rendered.height / float(xml_page.attrib["height"])
            candidates.sort(key=lambda item: (item["box"][1], item["box"][0]))
            for item in candidates:
                question = item["question"]
                box = item["box"]
                margin = 5
                crop_box = (
                    max(0, int((box[0] - margin) * scale_x)),
                    max(0, int((box[1] - margin) * scale_y)),
                    min(rendered.width, int((box[2] + margin) * scale_x)),
                    min(rendered.height, int((box[3] + margin) * scale_y)),
                )
                crop = rendered.crop(crop_box)
                result[question["id"]].append({
                    "question": question,
                    "page": page_number,
                    "box": box,
                    "type": item["type"],
                    "crop": crop,
                })
            rendered.close()
    document.close()
    return result


def main() -> None:
    questions = json.loads(DATA.read_text(encoding="utf-8"))
    target = [q for q in questions if q.get("transcriptionSource") == "pdf-text"]
    by_year: dict[int, list[dict]] = defaultdict(list)
    for question in questions:
        by_year[question["year"]].append(question)

    remove_old_crops()
    manifest: dict[str, list[dict]] = {}
    for year, year_questions in by_year.items():
        targets = [q for q in year_questions if q.get("transcriptionSource") == "pdf-text"]
        pdf = PDF_DIR / f"{year}.pdf"
        with tempfile.TemporaryDirectory(prefix=f"coluni-map-{year}-") as temp_dir:
            prefix = Path(temp_dir) / "proof"
            subprocess.run(["pdftohtml", "-xml", "-q", str(pdf), str(prefix)], check=True, capture_output=True, text=True)
            root = ET.parse(Path(str(prefix) + ".xml")).getroot()
            starts = question_starts(root, year_questions)
            page_xml = {int(page.attrib["number"]): page for page in root.findall("page")}
            candidates = crop_candidates(pdf, page_xml, starts, targets)

        for question in targets:
            entries = []
            for index, candidate in enumerate(candidates.get(question["id"], []), start=1):
                qdir = IMAGE_DIR / str(year) / f"questao-{question['number']:02d}"
                qdir.mkdir(parents=True, exist_ok=True)
                filename = f"figura-{index}.png"
                candidate["crop"].save(qdir / filename, "PNG", optimize=True)
                candidate["crop"].close()
                tex_path = f"static/simulados/coluni/figuras/{year}/questao-{question['number']:02d}/{filename}"
                entries.append({
                    "path": f"/simulados/coluni/figuras/{year}/questao-{question['number']:02d}/{filename}",
                    "texPath": tex_path,
                    "page": candidate["page"],
                    "rect": [round(v, 2) for v in candidate["box"]],
                    "type": candidate["type"],
                })
            insert_figure_blocks(SOURCE_DIR / f"{question['id']}.tex", entries)
            if entries:
                manifest[question["id"]] = entries

    # Several adjacent questions use the same source material. Give each
    # question its own directory and image files so every LaTeX source remains
    # self-contained and independently editable.
    for target_id, source_id in SHARED_FIGURES.items():
        shared_entries = []
        for source_entry in manifest.get(source_id, []):
            source_file = ROOT / source_entry["texPath"]
            target_question = next(q for q in target if q["id"] == target_id)
            qdir = IMAGE_DIR / str(target_question["year"]) / f"questao-{target_question['number']:02d}"
            qdir.mkdir(parents=True, exist_ok=True)
            filename = f"figura-{len(shared_entries) + 1}.png"
            shutil.copy2(source_file, qdir / filename)
            tex_path = f"static/simulados/coluni/figuras/{target_question['year']}/questao-{target_question['number']:02d}/{filename}"
            shared_entries.append({
                "path": f"/simulados/coluni/figuras/{target_question['year']}/questao-{target_question['number']:02d}/{filename}",
                "texPath": tex_path,
                "page": source_entry["page"],
                "rect": source_entry["rect"],
                "type": "shared",
                "sharedFrom": source_id,
            })
        if shared_entries:
            target_question = next(q for q in target if q["id"] == target_id)
            insert_figure_blocks(SOURCE_DIR / f"{target_id}.tex", shared_entries)
            manifest[target_id] = shared_entries

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    nfigures = sum(map(len, manifest.values()))
    print(f"Recortadas {nfigures} figuras para {len(manifest)} questões PDF.")


if __name__ == "__main__":
    main()
