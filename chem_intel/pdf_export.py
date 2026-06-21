"""Markdown レポート → PDF（日本語対応）。

WeasyPrint で HTML→PDF 変換。日本語フォントは Noto Sans CJK を利用
（Streamlit Cloud では packages.txt の fonts-noto-cjk で導入される）。
"""
from __future__ import annotations

import markdown as md_lib

CSS = """
@page { size: A4; margin: 18mm 15mm; }
* { font-family: "Noto Sans CJK JP", "Noto Sans JP", "Hiragino Sans",
    "Yu Gothic", "Meiryo", sans-serif; }
body { font-size: 10.5pt; line-height: 1.6; color: #1a1a1a; }
h1 { font-size: 20pt; color: #0b3d91; border-bottom: 3px solid #0b3d91;
     padding-bottom: 6px; }
h2 { font-size: 14pt; color: #0b3d91; margin-top: 18px;
     border-left: 5px solid #0b3d91; padding-left: 8px; }
h3 { font-size: 12pt; color: #333; margin-top: 12px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9.5pt; }
th, td { border: 1px solid #bbb; padding: 5px 7px; text-align: left; }
th { background: #eef2fb; }
a { color: #1155cc; word-break: break-all; }
hr { border: none; border-top: 1px solid #ddd; margin: 14px 0; }
code { background: #f3f3f3; padding: 1px 4px; border-radius: 3px; }
em { color: #666; }
"""


def markdown_to_html(markdown_text: str, title: str = "Chemical Report") -> str:
    body = md_lib.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<title>{title}</title><style>{CSS}</style></head>
<body>{body}</body></html>"""


def to_pdf(markdown_text: str, title: str = "Chemical Report") -> bytes:
    """PDF バイト列を返す。WeasyPrint 未導入環境では RuntimeError。"""
    from weasyprint import HTML

    html = markdown_to_html(markdown_text, title)
    return HTML(string=html).write_pdf()
