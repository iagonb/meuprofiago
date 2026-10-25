#!/usr/bin/env python3
"""Build the static index of objective COLUNI questions from the supplied PDFs.

Run from the repository root. Requires Poppler's pdftotext utility.
The downloaded official answer-key PDFs in ``Banco de Provas`` are used for
years 2019–2026. The 2018 key is image-only, so its Gabarito 1 answers are
recorded below from the official key page.
"""

from __future__ import annotations

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROOFS = ROOT / "Banco de Provas"
OUTPUT = ROOT / "static/simulados/coluni/questions.json"

PROOF_FILES = {
    2018: "COL18-Gab_1.pdf",
    2019: "COL19-Gab_1.pdf",
    2020: "COL2020-Gab1.pdf",
    2021: "COL2021_Gab-1.pdf",
    2022: "COL2022-Gabarito_01.pdf",
    2023: "COL2023_Gabarito-01.pdf",
    2024: "COL2024-Gabarito_01.pdf",
    2025: "COL2025-Gab_01.pdf",
    2026: "COL2026_Gabarito_01.pdf",
}

KEY_FILES = {
    2019: "COL19-GabaritoOficial-recursos.pdf",
    2020: "COL2020-Gab_Oficial-aposRecursos.pdf",
    2021: "COL2021-Gabarito_Oficial-RECURSOS.pdf",
    2022: "COL2022-Gabarito_Oficial-recursos.pdf",
    2023: "COL2023-Gabarito_Oficial-apos-recursos.pdf",
    2024: "COL2024-Gabarito_Oficial-apos-recursos.pdf",
    2025: "COL2025_Gabarito_Oficial_recursos.pdf",
    2026: "COL2026_Gabarito_Oficial.pdf",
}

ANSWERS_2018 = {
    1: "C", 2: "C", 3: "A", 4: "C", 5: "D", 6: "B", 7: "B", 8: "D",
    9: "C", 10: "A", 11: "C", 12: "C", 13: "C", 14: "D", 15: "B",
    16: "D", 17: "A", 18: None, 19: "B", 20: "A", 21: "B", 22: "C",
    23: "A", 24: "B", 25: "C", 26: "D", 27: "A", 28: "D", 29: "C",
    30: "B", 31: "C", 32: "D", 33: "C", 34: "C", 35: "C", 36: "D",
    37: "D", 38: "A",
}

SUBJECTS = (
    (1, 10, "Língua Portuguesa"),
    (11, 20, "Matemática"),
    (21, 22, "Inglês"),
    (23, 30, "Ciências"),
    (31, 34, "Geografia"),
    (35, 38, "História"),
)
CHOICES = {"A", "B", "C", "D"}


def pdf_text(path: Path) -> str:
    return subprocess.check_output(["pdftotext", "-layout", str(path), "-"], text=True)


def official_answers(year: int) -> dict[int, str | None]:
    if year == 2018:
        return ANSWERS_2018.copy()

    answers: dict[int, str | None] = {}
    for line in pdf_text(PROOFS / KEY_FILES[year]).splitlines():
        # The official key has the four booklets as columns. The first value
        # after each question number is the correct option for the supplied
        # Gabarito 1 proof PDF. Some PDFs collapse repeated ANULADA cells.
        tokens = line.split()
        for index, token in enumerate(tokens):
            if not re.fullmatch(r"\d{1,2}", token):
                continue
            number = int(token)
            if not 1 <= number <= 38 or index + 1 >= len(tokens):
                continue
            value = tokens[index + 1]
            if value in CHOICES:
                answers[number] = value
            elif value.startswith("ANULADA"):
                answers[number] = None

    if set(answers) != set(range(1, 39)):
        missing = sorted(set(range(1, 39)) - set(answers))
        raise ValueError(f"Gabarito {year}: questões sem resposta oficial: {missing}")
    return answers


def question_positions(year: int) -> tuple[dict[int, dict[str, float | int]], dict[int, float]]:
    path = PROOFS / PROOF_FILES[year]
    text_bbox = subprocess.check_output(["pdftotext", "-bbox-layout", str(path), "-"], text=True)
    root = ET.fromstring(text_bbox)
    namespace = "{http://www.w3.org/1999/xhtml}"
    found: dict[int, dict[str, float | int]] = {}
    heights: dict[int, float] = {}
    for page_number, page in enumerate(root.iter(f"{namespace}page"), start=1):
        heights[page_number] = float(page.attrib["height"])
        for line in page.iter(f"{namespace}line"):
            line_text = " ".join((word.text or "") for word in line.findall(f"{namespace}word"))
            match = re.match(r"^(0[1-9]|1[0-9]|2[0-9]|3[0-8])\.\s+", line_text)
            if match:
                found.setdefault(int(match.group(1)), {
                    "page": page_number,
                    "y": float(line.attrib["yMin"]),
                })
    if set(found) != set(range(1, 39)):
        missing = sorted(set(range(1, 39)) - set(found))
        raise ValueError(f"Prova {year}: questões sem página identificada: {missing}")
    return found, heights


def image_parts(number: int, positions: dict[int, dict[str, float | int]], heights: dict[int, float]) -> list[dict[str, float | int]]:
    start = positions[number]
    start_page = int(start["page"])
    start_y = float(start["y"])
    if number == 38:
        end_page = start_page
        end_y = heights[start_page] - 28
    else:
        end = positions[number + 1]
        end_page = int(end["page"])
        end_y = float(end["y"])

    if start_page == end_page:
        return [{"page": start_page, "top": max(0, start_y - 10), "bottom": max(start_y + 24, end_y - 6)}]

    parts = [{"page": start_page, "top": max(0, start_y - 10), "bottom": heights[start_page] - 28}]
    for page in range(start_page + 1, end_page):
        parts.append({"page": page, "top": 25, "bottom": heights[page] - 28})
    parts.append({"page": end_page, "top": 25, "bottom": max(50, end_y - 6)})
    return parts


def subject_for(number: int) -> str:
    for start, end, subject in SUBJECTS:
        if start <= number <= end:
            return subject
    raise ValueError(f"Questão fora das áreas objetivas: {number}")


def main() -> None:
    questions = []
    for year, proof_name in PROOF_FILES.items():
        answers = official_answers(year)
        positions, heights = question_positions(year)
        for number in range(1, 39):
            answer = answers[number]
            start_page = int(positions[number]["page"])
            questions.append({
                "id": f"{year}-{number:02d}",
                "year": year,
                "number": number,
                "subject": subject_for(number),
                "pdf": f"/simulados/coluni/provas/{year}.pdf",
                "page": start_page,
                "pageImage": f"/simulados/coluni/questoes/{year}/questao-{number:02d}-1.webp",
                "imageParts": image_parts(number, positions, heights),
                "answer": answer,
                "annulled": answer is None,
                "source": proof_name,
            })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(questions, ensure_ascii=False, indent=2) + "\n")
    print(f"Geradas {len(questions)} questões objetivas em {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
