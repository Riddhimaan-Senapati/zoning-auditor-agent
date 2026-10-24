import pytest

from auditor.cli import main
from auditor.saved_pages import check_saved_dir, check_saved_page

SHELL = """<html><head><script src="app.js"></script><script>window.__STATE__ = {"53-1": 1, "53-2": 2,
"53-3": 3, "53-4": 4, "53-5": 5}</script></head><body><div id="app">Loading...</div></body></html>"""


def _article(sections: int) -> str:
    body = "".join(f"<h3>Section 53-{n}. - Heading {n}.</h3><p>{'Dimensional text. ' * 30}</p>"
                   for n in range(1, sections + 1))
    return f"<html><body><script>var x=1;</script>{body}</body></html>"


def test_js_shell_fails_with_a_reload_hint(tmp_path):
    page = tmp_path / "53.html"
    page.write_text(SHELL)
    (problem,) = check_saved_page(page)
    assert problem.startswith("53.html looks like it was saved before the code text loaded")
    assert 'save again as "Webpage, Complete"' in problem
    assert problem.endswith("Found 0 distinct Section 53-N numbers.")


def test_rendered_article_passes_and_numbers_must_be_distinct(tmp_path):
    page = tmp_path / "53.html"
    page.write_text(_article(6))
    assert check_saved_page(page) == []
    page.write_text(_article(1) * 6)
    assert check_saved_page(page)[0].endswith("Found 1 distinct Section 53-N numbers.")


def test_toc_needs_many_articles(tmp_path):
    toc = tmp_path / "toc.html"
    toc.write_text("<ul>" + "".join(f"<li>ARTICLE {n} - Title</li>" for n in range(1, 25)) + "</ul>")
    assert check_saved_page(toc) == []
    toc.write_text("<ul><li>Article 53</li></ul>")
    assert check_saved_page(toc)[0].endswith("Found 1 distinct articles.")


def test_unexpected_names_and_empty_dirs_fail(tmp_path):
    (tmp_path / "East Boston.html").write_text(_article(6))
    assert check_saved_dir(tmp_path) == ["East Boston.html: name saved pages <article>.html (e.g. 53.html) or toc.html."]
    empty = tmp_path / "empty"
    empty.mkdir()
    assert check_saved_dir(empty) == [f"{empty}: no saved .html pages."]


def test_cli_exits_nonzero_on_a_shell(tmp_path, capsys):
    (tmp_path / "53.html").write_text(SHELL)
    with pytest.raises(SystemExit) as exit:
        main(["check-pages", str(tmp_path)])
    assert exit.value.code == 1
    assert "53.html looks like it was saved" in capsys.readouterr().err
    (tmp_path / "53.html").write_text(_article(6))
    main(["check-pages", str(tmp_path)])
    assert capsys.readouterr().out == "saved pages look complete\n"
