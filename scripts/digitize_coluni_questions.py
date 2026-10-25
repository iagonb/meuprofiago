#!/usr/bin/env python3
"""Create LaTeX source and browser-ready HTML for the COLUNI question bank.

Mathematics questions with curated source in Matemática/questoes.tex use that
source directly. Remaining questions are transcribed from the text layer of
the original exam PDFs into LaTeX. The original crop/PDF remains available in
the simulator for figures, scanned material, and comparison.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "static/simulados/coluni/questions.json"
PDF_DIR = ROOT / "static/simulados/coluni/provas"
TEX_SOURCE = ROOT / "Matemática/questoes.tex"
TEX_DIR = ROOT / "data/coluni/latex-source"
FIG_SOURCE = ROOT / "Matemática/figs"
FIG_DEST = ROOT / "static/simulados/coluni/latex-figs"


def latex_blocks() -> dict[str, str]:
    text = TEX_SOURCE.read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    for block in re.split(r"(?m)^\s*%%%+\s*$", text):
        match = re.search(r"CAP-COLUNI\s+(20\d{2})\s+--\s+Q(\d{1,2})", block)
        if match:
            key = f"{match.group(1)}-{int(match.group(2)):02d}"
            blocks[key] = block.strip()
    return blocks


def pdf_pages(year: int) -> list[str]:
    path = PDF_DIR / f"{year}.pdf"
    text = subprocess.check_output(["pdftotext", "-layout", str(path), "-"], text=True)
    return text.split("\f")


def question_text(question: dict, pages: list[str], next_question: dict | None) -> str:
    start_page = question["page"] - 1
    start_re = re.compile(rf"^\s*{question['number']:02d}\.\s+")
    start_line = next((i for i, line in enumerate(pages[start_page].splitlines()) if start_re.match(line)), None)
    if start_line is None:
        raise ValueError(f"Não localizei o início de {question['id']} na página {question['page']}.")

    lines = pages[start_page].splitlines()[start_line:]
    if next_question:
        end_page = next_question["page"] - 1
        end_re = re.compile(rf"^\s*{next_question['number']:02d}\.\s+")
        if end_page == start_page:
            page_lines = pages[start_page].splitlines()
            end_line = next((i for i in range(start_line + 1, len(page_lines)) if end_re.match(page_lines[i])), None)
            if end_line is not None:
                lines = page_lines[start_line:end_line]
        else:
            lines.extend(line for page in pages[start_page + 1:end_page] for line in page.splitlines())
            end_lines = pages[end_page].splitlines()
            end_line = next((i for i, line in enumerate(end_lines) if end_re.match(line)), None)
            if end_line is not None:
                lines.extend(end_lines[:end_line])

    cleaned = []
    for line in lines:
        if "EXAME DE SELEÇÃO" in line or "GABARITO 1" in line:
            continue
        if re.fullmatch(r"\s*\d{1,3}\s*", line):
            continue
        cleaned.append(line.rstrip())
    result = "\n".join(cleaned).strip()
    if len(result) < 20:
        raise ValueError(f"Transcrição curta ou vazia em {question['id']}.")
    return result


def escape_latex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in text)


def extracted_text_latex(question: dict, text: str) -> str:
    text = re.sub(rf"^\s*{question['number']:02d}\.\s*", "", text)
    labels = list(re.finditer(r"(?<![A-Za-z0-9])([a-d])\)\s*", text, re.IGNORECASE))
    choices = None
    for index in range(len(labels) - 3):
        group = labels[index:index + 4]
        if [match.group(1).lower() for match in group] == list("abcd"):
            candidate = [text[group[i].end():group[i + 1].start()].strip() for i in range(3)]
            candidate.append(text[group[3].end():].strip())
            if all(len(value) >= 8 for value in candidate):
                choices = (text[:group[0].start()].strip(), candidate)

    def paragraphs(source: str) -> str:
        result = []
        for paragraph in re.split(r"\n\s*\n", source):
            paragraph = " ".join(part.strip() for part in paragraph.splitlines() if part.strip())
            if paragraph:
                result.append(escape_latex(paragraph))
        return "\n\n\\par\n\n".join(result)

    main_text, option_texts = choices if choices else (text, None)
    body = paragraphs(main_text)
    if option_texts:
        body += r"\begin{enumerate}" + "\n" + "\n".join(r"\item " + escape_latex(option) for option in option_texts) + r"\end{enumerate}"
    return (
        r"\begin{minipage}{\linewidth}\raggedright "
        + rf"\textbf{{COLUNI {question['year']} -- Questão {question['number']:02d}}}\\[.6em]"
        + body
        + r"\end{minipage}"
    )


def curated_latex(block: str) -> str:
    body = re.sub(r"(?m)^%.*$", "", block)
    body = re.sub(r"(?s)^.*?\\question\s*", "", body)
    body = body.replace(r"\begin{qparts}", r"\begin{enumerate}")
    body = body.replace(r"\end{qparts}", r"\end{enumerate}")
    body = re.sub(r"\\qimage(?:\[[^]]+\])?\{([^}]+)\}", r"\\includegraphics{\1}", body)
    body = re.sub(r"\\newpage\s*", "", body)
    body = re.sub(r"\\section\*?\{[^}]*\}", "", body)
    body = re.sub(r"\\begin\{multicols\*?\}(?:\{[^}]+\})?", "", body)
    body = re.sub(r"\\end\{multicols\*?\}", "", body)
    return body.strip()


def pandoc_html(source: str, question: dict) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".tex", encoding="utf-8") as temp:
        temp.write(source)
        temp.flush()
        result = subprocess.run(
            ["pandoc", temp.name, "-f", "latex", "-t", "html", "--mathjax"],
            capture_output=True, text=True,
        )
        if result.returncode:
            raise RuntimeError(f"Pandoc falhou em {question['id']}: {result.stderr.strip()}\nFonte: {source[:500]}")
    rendered = result.stdout.strip()
    rendered = re.sub(
        r'src="(?:\./)?figs/([^" ]+)"',
        lambda match: f'src="/simulados/coluni/latex-figs/{match.group(1)}"',
        rendered,
    )
    rendered = rendered.replace(
        'src="static/simulados/coluni/',
        'src="/simulados/coluni/',
    )
    # Source questions use enumerate for alternatives; letters are clearer to students.
    rendered = rendered.replace("<ol>", '<ol class="coluni-latex-choices">')
    return rendered


def main() -> None:
    questions = json.loads(DATA.read_text(encoding="utf-8"))
    sources = latex_blocks()
    by_year: dict[int, list[str]] = {}
    TEX_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DEST.mkdir(parents=True, exist_ok=True)
    for image in FIG_SOURCE.glob("*.png"):
        shutil.copy2(image, FIG_DEST / image.name)
    for source_path in TEX_DIR.glob("*.tex"):
        for filename in re.findall(r"\\includegraphics\{(?:[^}]*?/)?([^/}]+)\}", source_path.read_text(encoding="utf-8")):
            if filename.startswith("CAP") and not (FIG_DEST / filename).exists():
                equivalent = FIG_SOURCE / filename[3:]
                if equivalent.exists():
                    shutil.copy2(equivalent, FIG_DEST / filename)

    for index, question in enumerate(questions):
        next_question = questions[index + 1] if index + 1 < len(questions) and questions[index + 1]["year"] == question["year"] else None
        key = question["id"]
        source_path = TEX_DIR / f"{key}.tex"
        if source_path.exists():
            latex = source_path.read_text(encoding="utf-8").strip()
            question["transcriptionSource"] = "latex" if key in sources else "pdf-text"
        elif key in sources:
            latex = curated_latex(sources[key])
            question["transcriptionSource"] = "latex"
        else:
            if question["year"] not in by_year:
                by_year[question["year"]] = pdf_pages(question["year"])
            text = question_text(question, by_year[question["year"]], next_question)
            latex = extracted_text_latex(question, text)
            question["transcriptionSource"] = "pdf-text"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        if not source_path.exists():
            source_path.write_text(latex + "\n", encoding="utf-8")
        question["latex"] = latex
        question["latexHtml"] = pandoc_html(latex, question)

    DATA.write_text(json.dumps(questions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Digitalizadas {len(questions)} questões; {len(sources)} usam LaTeX revisado e {len(questions)-len(sources)} usam extração textual dos PDFs.")


if __name__ == "__main__":
    main()
