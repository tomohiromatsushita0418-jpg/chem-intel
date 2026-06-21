"""財務省 貿易統計・関税の要約。

HSコードの特定、日本の輸出入実績、実行関税率(MFN/EPA)、規制品目該当性を
ウェブ検索で確認し、財務省・税関の一次情報リンクを添える。
"""
from __future__ import annotations

from .identity import ChemicalIdentity
from .llm import ResearchResult, research

CUSTOMS_STATS = "https://www.customs.go.jp/toukei/info/"
TARIFF_SCHEDULE = "https://www.customs.go.jp/tariff/"
STATS_SEARCH = "https://www.customs.go.jp/toukei/srch/index.htm"


def analyze(settings, ident: ChemicalIdentity, hs_hint: str | None = None) -> ResearchResult:
    name = ident.display_name
    cas = ident.cas or "（CAS不明）"
    hs_line = f"\nユーザー指定のHSコード候補: {hs_hint}" if hs_hint else ""
    prompt = f"""あなたは日本の輸出入実務・関税分類(HSコード)の専門家です。次の物質について、
財務省 貿易統計および税関の一次情報をウェブ検索で確認し、正確にまとめてください。

対象物質: {name} / CAS: {cas} / 分子式: {ident.molecular_formula or '不明'}{hs_line}

出力（Markdown、日本語）:
## HSコード分類
- 最も妥当なHSコード（6桁/9桁）と品名、分類根拠。複数候補があれば併記。
## 日本の輸出入実績
- 財務省貿易統計に基づく直近の輸入量・輸出量・主要相手国（分かる範囲で数値と年）。
## 関税率
- 実行関税率（基本/WTO協定/暫定）と主要EPA特恵税率。無税なら明記。
## 輸出入の規制・手続
- 外為法（輸出貿易管理令・キャッチオール規制該当性）、輸入規制、必要な許認可。
## 実務メモ
- 商社営業として通関・調達で注意すべき点を3〜5行。

数値は出典年を明記し、不確かなものは「要確認」と明示。推測で断定しないこと。"""

    res = research(settings, prompt, max_tokens=5000)
    res.text += (
        f"\n\n**🔗 財務省・税関で直接確認:** "
        f"[貿易統計]({CUSTOMS_STATS}) / "
        f"[統計検索]({STATS_SEARCH}) / "
        f"[実行関税率表]({TARIFF_SCHEDULE})"
    )
    return res
