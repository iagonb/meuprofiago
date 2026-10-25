#!/usr/bin/env python3
"""Render each question block from the original COLUNI proof PDFs as WebP."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "static/simulados/coluni/questions.json"
OUTPUT = ROOT / "static/simulados/coluni/questoes"
LEGACY_OUTPUT = ROOT / "static/simulados/coluni/paginas"
SCALE = 140 / 72


def main() -> None:
    questions = json.loads(DATA.read_text())
    pages: dict[int, set[int]] = defaultdict(set)
    for question in questions:
        for part in question["imageParts"]:
            pages[question["year"]].add(part["page"])

    if LEGACY_OUTPUT.exists():
        shutil.rmtree(LEGACY_OUTPUT)

    with tempfile.TemporaryDirectory(prefix="coluni-pages-") as temp:
        temp_path = Path(temp)
        for year, page_numbers in pages.items():
            pdf = ROOT / "static/simulados/coluni/provas" / f"{year}.pdf"
            prefix = temp_path / str(year)
            subprocess.run([
                "pdftoppm", "-r", "140", "-png",
                "-f", str(min(page_numbers)), "-l", str(max(page_numbers)),
                str(pdf), str(prefix),
            ], check=True)

            rendered: dict[int, Image.Image] = {}
            for page_number in page_numbers:
                page_path = Path(f"{prefix}-{page_number:02d}.png")
                rendered[page_number] = Image.open(page_path).convert("RGB")

            for question in (item for item in questions if item["year"] == year):
                destination = OUTPUT / str(year)
                destination.mkdir(parents=True, exist_ok=True)
                extra_images = []
                for index, part in enumerate(question["imageParts"], start=1):
                    page = rendered[part["page"]]
                    top = max(0, round(part["top"] * SCALE))
                    bottom = min(page.height, round(part["bottom"] * SCALE))
                    if bottom <= top:
                        raise ValueError(f"Recorte vazio para a questão {question['id']}")
                    crop = page.crop((0, top, page.width, bottom))
                    image_path = destination / f"questao-{question['number']:02d}-{index}.webp"
                    crop.save(image_path, "WEBP", quality=84, method=6)
                    if index > 1:
                        extra_images.append({
                            "src": f"/simulados/coluni/questoes/{year}/{image_path.name}",
                            "page": part["page"],
                        })
                question["extraImages"] = extra_images

            for page in rendered.values():
                page.close()

    for question in questions:
        question.pop("imageParts", None)
    DATA.write_text(json.dumps(questions, ensure_ascii=False, indent=2) + "\n")
    print(f"Renderizadas {len(questions)} questões objetivas em {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
