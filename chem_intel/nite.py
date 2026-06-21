"""NITE CHRIP 連携：日本の化学物質規制を要約。

CHRIP は公開APIが無いため、直リンクを提示しつつ、Claude のウェブ検索で
化審法・安衛法・毒劇法・化管法(PRTR)・GHS分類などを出典付きで要約する。
"""
from __future__ import annotations

from urllib.parse import quote

from .identity import ChemicalIdentity
from .llm import ResearchResult, research

CHRIP_TOP = "https://www.chem-info.nite.go.jp/chem/chrip/chrip_search/systemTop"


def chrip_search_url(ident: ChemicalIdentity) -> str:
    term = ident.cas or ident.display_name
    return (
        "https://www.chem-info.nite.go.jp/chem/chrip/chrip_search/"
        f"sltMate?s='{quote(term)}'"
    )


def analyze(settings, ident: ChemicalIdentity) -> ResearchResult:
    name = ident.display_name
    cas = ident.cas or "（CAS不明）"
    prompt = f"""あなたは日本の化学物質規制の専門家です。次の物質について、NITE CHRIP
（化学物質総合情報提供システム）と各省庁の一次情報をウェブ検索で確認し、
日本国内の規制状況を正確に、漏れなくまとめてください。

対象物質: {name} / CAS番号: {cas} / 分子式: {ident.molecular_formula or '不明'}

必ず次の各法令について「該当の有無・区分・指定内容・規制の要点」を箇条書きで:
1. 化審法（優先評価化学物質/監視化学物質/第一種・第二種特定化学物質 等）
2. 安衛法（労働安全衛生法：名称等表示・通知義務、特化則、有機則 等）
3. 毒劇法（毒物及び劇物取締法：毒物/劇物の指定）
4. 化管法（PRTR/SDS：第一種・第二種指定化学物質）
5. 消防法（危険物の類別・指定数量）※該当する場合
6. 大気汚染防止法/水質汚濁防止法 等の環境法令（該当する場合）
7. GHS分類（健康有害性・環境有害性の主要区分）

各項目は「根拠（公布・政令番号・告示等）」が分かれば併記。不明な点は推測せず
「要確認」と明記。最後に、商社の営業担当が顧客に説明する際の実務上の注意点を
3〜5行でまとめてください。日本語で、Markdown 見出し・箇条書きで出力。"""

    res = research(settings, prompt, max_tokens=6000)
    # CHRIP への直リンクを末尾に追加
    res.text += (
        f"\n\n**🔗 NITE CHRIP で直接確認:** "
        f"[CHRIP検索]({chrip_search_url(ident)}) / "
        f"[CHRIPトップ]({CHRIP_TOP})"
    )
    return res
