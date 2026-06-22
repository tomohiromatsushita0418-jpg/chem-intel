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
@page {
  size: A4; margin: 22mm 18mm 20mm 18mm;
  @top-left { content: "化学品インテリジェンス・レポート"; font-size: 7.5pt;
    color: #8a96a3; }
  @top-right { content: string(doctitle); font-size: 7.5pt; color: #8a96a3; }
  @bottom-left { content: "社外秘 / CONFIDENTIAL"; font-size: 7pt; color: #b3bcc6; }
  @bottom-right { content: counter(page) " / " counter(pages); font-size: 7.5pt;
    color: #8a96a3; }
}
@page cover { margin: 0;
  @top-left { content: none; } @top-right { content: none; }
  @bottom-left { content: none; } @bottom-right { content: none; }
}
* { font-family: "Noto Sans CJK JP", "Noto Sans JP", "Hiragino Sans",
    "Yu Gothic", "Meiryo", sans-serif; }
body { font-size: 10pt; line-height: 1.65; color: #20272e; }

/* ---- 表紙 ---- */
.cover { page: cover; height: 297mm; position: relative; color: #1b2b3a; }
.cover .band { height: 90mm; background: linear-gradient(135deg,#0f2b46 0%,#1c4a73 100%); }
.cover .kicker { position: absolute; top: 30mm; left: 22mm; color: #9fc2e0;
  font-size: 11pt; letter-spacing: 4px; }
.cover .title { position: absolute; top: 44mm; left: 22mm; right: 22mm;
  color: #ffffff; font-size: 34pt; font-weight: 700; line-height: 1.2; }
.cover .subtitle { position: absolute; top: 74mm; left: 22mm; color: #cfe0f0;
  font-size: 13pt; }
.cover .meta { position: absolute; top: 120mm; left: 22mm; right: 22mm;
  border-collapse: collapse; width: auto; font-size: 11pt; }
.cover .meta td { border: none; padding: 5px 0; }
.cover .meta td.k { color: #6b7884; width: 42mm; }
.cover .meta td.v { color: #1b2b3a; font-weight: 600; }
.cover .rule { position: absolute; top: 112mm; left: 22mm; right: 22mm;
  border-top: 2px solid #0f2b46; }
.cover .foot { position: absolute; bottom: 22mm; left: 22mm; right: 22mm;
  color: #8a96a3; font-size: 8.5pt; border-top: 1px solid #d6dde4; padding-top: 6px; }

/* ---- 本文見出し ---- */
h1 { string-set: doctitle content(); page-break-before: always;
  font-size: 17pt; color: #0f2b46; font-weight: 700;
  border-bottom: 2px solid #0f2b46; padding-bottom: 5px; margin: 0 0 12px; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 12.5pt; color: #1c4a73; margin: 16px 0 6px;
  padding-left: 9px; border-left: 4px solid #1c4a73; }
h3 { font-size: 11pt; color: #2b3a47; margin: 12px 0 4px; }
p { margin: 5px 0; }
strong { color: #0f2b46; }
ul, ol { margin: 5px 0 5px 0; padding-left: 20px; }
li { margin: 2px 0; }

/* ---- 表 ---- */
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9pt; }
th, td { border: 1px solid #d6dde4; padding: 6px 8px; text-align: left;
  vertical-align: top; }
th { background: #0f2b46; color: #fff; font-weight: 600; }
tr:nth-child(even) td { background: #f4f7fa; }

/* ---- その他 ---- */
a { color: #1c4a73; text-decoration: none; }
hr { border: none; border-top: 1px solid #e3e8ed; margin: 16px 0; }
code { background: #eef2f6; padding: 1px 4px; border-radius: 3px; font-size: 9pt; }
blockquote { margin: 8px 0; padding: 8px 12px; background: #fbf7e9;
  border-left: 4px solid #d9b84a; color: #5c5132; font-size: 9.5pt; }
em { color: #6b7884; }
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


def _parse_cover(markdown_text: str) -> tuple[dict, str]:
    """先頭の <!--COVER ... --> を抽出し、表紙メタと本文(コメント除去)を返す。"""
    meta: dict = {}
    m = re.search(r"<!--COVER\s*(.*?)-->", markdown_text, re.DOTALL)
    if m:
        for line in m.group(1).strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                meta[k.strip()] = v.strip()
        markdown_text = markdown_text[: m.start()] + markdown_text[m.end():]
    return meta, markdown_text


def _cover_html(meta: dict) -> str:
    if not meta:
        return ""
    rows = ""
    for k, label in [("cas", "CAS登録番号"), ("formula", "分子式"),
                     ("hs", "HSコード"), ("date", "作成日")]:
        if meta.get(k):
            rows += f'<tr><td class="k">{label}</td><td class="v">{meta[k]}</td></tr>'
    return f"""<div class="cover">
  <div class="band"></div>
  <div class="kicker">CHEMICAL INTELLIGENCE REPORT</div>
  <div class="title">{meta.get('title','')}</div>
  <div class="subtitle">{meta.get('subtitle','化学品インテリジェンス・レポート')}</div>
  <div class="rule"></div>
  <table class="meta">{rows}</table>
  <div class="foot">社外秘 / CONFIDENTIAL ― 本資料は公開情報およびAI調査に基づく参考資料です。
    最終判断は一次情報でご確認ください。</div>
</div>"""


def markdown_to_html(markdown_text: str, title: str = "Chemical Report") -> str:
    meta, rest = _parse_cover(markdown_text)
    cover = _cover_html(meta)
    # 表紙がある場合、本文は最初の番号付きセクション以降だけにして重複を避ける
    if cover:
        m = re.search(r"^#\s*1\.", rest, re.MULTILINE)
        if m:
            rest = rest[m.start():]
    body = md_lib.markdown(
        rest, extensions=["tables", "fenced_code", "sane_lists", "nl2br"]
    )
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<title>{title}</title><style>{CSS}</style></head>
<body>{cover}{body}</body></html>"""


def _weasyprint_pdf(markdown_text: str, title: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=markdown_to_html(markdown_text, title)).write_pdf()


def _new_fpdf(font_path: str | None):
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    if font_path:
        for style in ("", "B", "I", "BI"):
            pdf.add_font("CJK", style, font_path)
        pdf.set_font("CJK", size=10)
    else:
        pdf.set_font("helvetica", size=10)
    return pdf


def _break_long_tokens(text: str, n: int = 40) -> str:
    """空白の無い超長文字列（URL等）に改行機会(空白)を挿入。"""
    return re.sub(r"(\S{%d})(?=\S)" % n, r"\1 ", text)


def _fpdf_pdf(markdown_text: str, title: str) -> bytes:
    """純Pythonフォールバック。整形描画→失敗時はテキスト描画で必ずPDFを返す。"""
    _, markdown_text = _parse_cover(markdown_text)  # 表紙コメントを除去
    font_path = _find_font()

    # --- 1) 整形(HTML)描画を試す ---
    try:
        body = md_lib.markdown(markdown_text, extensions=["tables", "sane_lists"])
        # 等幅(Courier)＝日本語非対応なので除去、リンクはテキスト化、長URLは改行可能に
        body = re.sub(r"</?(code|pre|tt|kbd|samp)[^>]*>", "", body)
        body = re.sub(r"<a\b[^>]*>", "", body)
        body = body.replace("</a>", "")
        body = _break_long_tokens(body)
        pdf = _new_fpdf(font_path)
        pdf.write_html(body)
        return bytes(pdf.output())
    except Exception:
        pass

    # --- 2) 確実に出るテキスト描画 ---
    from fpdf.enums import XPos, YPos

    pdf = _new_fpdf(font_path)
    epw = pdf.epw  # 有効ページ幅
    # markdownの装飾記号を軽く除去して読みやすく
    for raw in markdown_text.splitlines():
        line = raw.rstrip()
        line = re.sub(r"`([^`]*)`", r"\1", line)         # inline code
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)  # links→text
        line = _break_long_tokens(line)
        if line.startswith("# "):
            pdf.set_font("CJK" if font_path else "helvetica", "B", 16); line = line[2:]
        elif line.startswith("## "):
            pdf.set_font("CJK" if font_path else "helvetica", "B", 13); line = line[3:]
        elif line.startswith("### "):
            pdf.set_font("CJK" if font_path else "helvetica", "B", 11); line = line[4:]
        else:
            pdf.set_font("CJK" if font_path else "helvetica", "", 10)
        try:
            pdf.multi_cell(epw, 6, line if line else " ",
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        except Exception:
            pdf.ln(6)  # 描画不能な行はスキップして継続
    return bytes(pdf.output())


def to_pdf(markdown_text: str, title: str = "Chemical Report") -> bytes:
    """PDF バイト列を返す。WeasyPrint→fpdf2 の順で試す。"""
    markdown_text = _strip_emoji(markdown_text)
    try:
        return _weasyprint_pdf(markdown_text, title)
    except Exception:
        return _fpdf_pdf(markdown_text, title)
