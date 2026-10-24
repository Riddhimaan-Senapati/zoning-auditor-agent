import re
from pathlib import Path

from bs4 import BeautifulSoup

MIN_TEXT_CHARS = 2000
MIN_SECTION_NUMBERS = 5
MIN_TOC_ARTICLES = 20


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def check_saved_page(path: Path) -> list[str]:
    """Problems that mean `path` is not a usable saved page; empty when it is.

    `<article>.html` (e.g. 53.html) must show that article's section numbers; `toc.html`
    must list many articles. A page saved before Municode rendered it holds almost no text.
    """
    text = visible_text(path.read_text(encoding="utf-8", errors="replace"))
    shell = (f"{path.name} looks like it was saved before the code text loaded "
             f"({len(text)} visible characters). Reload the page, wait until the text appears, "
             'then save again as "Webpage, Complete".')
    if path.stem == "toc":
        articles = len(set(re.findall(r"\bArticle\s+(\d+[A-Z]*)\b", text, re.IGNORECASE)))
        return [] if articles >= MIN_TOC_ARTICLES else [shell + f" Found {articles} distinct articles."]
    if not re.fullmatch(r"\d+[A-Z]*", path.stem):
        return [f"{path.name}: name saved pages <article>.html (e.g. 53.html) or toc.html."]
    numbers = set(re.findall(rf"\b{path.stem}-\d+[A-Za-z]?\b", text))
    if len(text) < MIN_TEXT_CHARS or len(numbers) < MIN_SECTION_NUMBERS:
        return [shell + f" Found {len(numbers)} distinct Section {path.stem}-N numbers."]
    return []


def check_saved_dir(directory: Path) -> list[str]:
    pages = sorted(directory.glob("*.html"))
    if not pages:
        return [f"{directory}: no saved .html pages."]
    return [problem for page in pages for problem in check_saved_page(page)]
