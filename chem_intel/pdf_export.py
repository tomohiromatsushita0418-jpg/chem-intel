"""Markdown レポート → PDF（日本語対応）。

2段構え:
  1. WeasyPrint（HTML+CSSで高品質。Streamlit Cloudは packages.txt で動作）
  2. 失敗時は fpdf2（純Python・システムライブラリ不要）へ自動フォールバック
日本語フォントは bundled → システムフォントの順で自動検出。
"""
from __future__ import annotations

import os
import re

import markdown as md_lib

# PDFフォントが持たない絵文字・記号類を除去（画面表示では残す）
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF️]"
)


def _strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text)

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

# CJK フォントの探索候補（bundled を最優先）
_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "..", "assets", "NotoSansJP-Regular.ttf"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
]


def _find_font() -> str | None:
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def markdown_to_html(markdown_text: str, title: str = "Chemical Report") -> str:
    body = md_lib.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<title>{title}</title><style>{CSS}</style></head>
<body>{body}</body></html>"""


def _weasyprint_pdf(markdown_text: str, title: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=markdown_to_html(markdown_text, title)).write_pdf()


def _fpdf_pdf(markdown_text: str, title: str) -> bytes:
    """純Pythonフォールバック。markdown→HTML本文を fpdf2 で描画。"""
    from fpdf import FPDF

    font_path = _find_font()
    body = md_lib.markdown(
        markdown_text, extensions=["tables", "sane_lists"]
    )

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    if font_path:
        pdf.add_font("CJK", "", font_path)
        pdf.add_font("CJK", "B", font_path)
        pdf.add_font("CJK", "I", font_path)
        pdf.set_font("CJK", size=10)
    else:
        pdf.set_font("helvetica", size=10)
    pdf.write_html(body)
    return bytes(pdf.output())


def to_pdf(markdown_text: str, title: str = "Chemical Report") -> bytes:
    """PDF バイト列を返す。WeasyPrint→fpdf2 の順で試す。"""
    markdown_text = _strip_emoji(markdown_text)
    try:
        return _weasyprint_pdf(markdown_text, title)
    except Exception:
        return _fpdf_pdf(markdown_text, title)
