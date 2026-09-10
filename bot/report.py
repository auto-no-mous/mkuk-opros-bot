"""Builds the self-contained HTML report shown after a check run.

Everything is inlined: the report has to open from a local file on machines with
no access to anything but the survey site itself.
"""
from __future__ import annotations

import html
import time

STYLE = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; padding: 32px 20px 64px; background: #f5f7fb; color: #1f2937;
       font: 15px/1.5 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
.wrap { max-width: 940px; margin: 0 auto; }
h1 { font-size: 24px; margin: 0 0 4px; }
.meta { color: #6b7280; font-size: 13px; margin-bottom: 24px; }
.meta code { background: #e5e7eb; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
.banner { padding: 12px 16px; border-radius: 10px; margin-bottom: 24px; font-weight: 600; }
.banner.ok { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
.banner.fail { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
.page { background: #fff; border: 1px solid #e5e7eb; border-radius: 14px;
        padding: 20px 22px; margin-bottom: 18px; }
.page > h2 { font-size: 15px; margin: 0 0 14px; color: #6b7280; font-weight: 600;
             text-transform: uppercase; letter-spacing: .04em; }
.q { border-top: 1px solid #f3f4f6; padding: 14px 0 4px; }
.q:first-of-type { border-top: 0; padding-top: 0; }
.q > h3 { font-size: 15px; margin: 0 0 10px; font-weight: 600; }
.code { font: 12px ui-monospace, Consolas, monospace; color: #9ca3af; }
ul.opts { list-style: none; margin: 0; padding: 0; }
ul.opts li { padding: 4px 10px; border-radius: 6px; color: #6b7280; }
ul.opts li.on { background: #dcfce7; color: #14532d; font-weight: 600; }
ul.opts li.on::before { content: "✓  "; }
ul.opts li.off::before { content: "    "; }
table.matrix { border-collapse: collapse; width: 100%; font-size: 14px; }
table.matrix th { text-align: left; font-weight: 600; color: #6b7280; font-size: 12px;
                  padding: 6px 8px; border-bottom: 1px solid #e5e7eb; }
table.matrix td { padding: 6px 8px; border-bottom: 1px solid #f3f4f6; }
table.matrix td.pick { background: #dcfce7; color: #14532d; font-weight: 600; border-radius: 6px; }
.empty { color: #9ca3af; font-style: italic; }
a.raw { font-size: 12px; color: #2563eb; text-decoration: none; }
a.raw:hover { text-decoration: underline; }
"""


def _esc(text: str) -> str:
    return html.escape(text or "")


def _render_choice_list(question, chosen) -> str:
    chosen_ids = {option.input_id for option in chosen}
    items = []
    for option in question.options():
        state = "on" if option.input_id in chosen_ids else "off"
        items.append(f'<li class="{state}">{_esc(option.label)}</li>')
    return '<ul class="opts">' + "".join(items) + "</ul>"


def _render_matrix(question, chosen) -> str:
    chosen_ids = {option.input_id for option in chosen}
    rows = question.matrix_rows()
    if not rows:
        return '<p class="empty">В таблице не нашлось вариантов ответа.</p>'

    header = "".join(f"<th>{_esc(option.label)}</th>" for option in rows[0].options)
    body = []
    for index, row in enumerate(rows, start=1):
        cells = []
        for option in row.options:
            picked = option.input_id in chosen_ids
            cells.append(
                f'<td class="pick">{_esc(option.label)}</td>' if picked else "<td></td>"
            )
        title = _esc(row.label) or f"Строка {index}"
        body.append(f"<tr><td>{title}</td>{''.join(cells)}</tr>")
    return (
        f'<table class="matrix"><tr><th></th>{header}</tr>{"".join(body)}</table>'
    )


def _render_question(question, chosen) -> str:
    codes = sorted({option.name for option in chosen})
    code_html = f' <span class="code">{_esc(", ".join(codes))}</span>' if codes else ""
    body = _render_matrix(question, chosen) if question.is_matrix else _render_choice_list(question, chosen)
    return f'<div class="q"><h3>{_esc(question.text)}{code_html}</h3>{body}</div>'


def build(pages: list, survey_url: str, outcome: str, error: str = None) -> str:
    """pages: list of dicts with keys `title`, `decisions` [(question, chosen)], `raw_file`."""
    if error:
        banner = f'<div class="banner fail">Проверка завершилась ошибкой: {_esc(error)}</div>'
    else:
        banner = f'<div class="banner ok">{_esc(outcome)}</div>'

    blocks = []
    for page in pages:
        raw_link = (
            f' <a class="raw" href="{_esc(page["raw_file"])}">исходный HTML страницы</a>'
            if page.get("raw_file")
            else ""
        )
        if page["decisions"]:
            inner = "".join(_render_question(q, chosen) for q, chosen in page["decisions"])
        else:
            inner = '<p class="empty">На этой странице вопросов не было — бот просто нажал «Продолжить».</p>'
        blocks.append(f'<div class="page"><h2>{_esc(page["title"])}{raw_link}</h2>{inner}</div>')

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Проверка опрос-бота</title>
<style>{STYLE}</style>
</head>
<body>
<div class="wrap">
<h1>Что выбрал бот</h1>
<div class="meta">{time.strftime("%d.%m.%Y %H:%M:%S")} &middot; <code>{_esc(survey_url)}</code></div>
{banner}
{"".join(blocks)}
</div>
</body>
</html>
"""
