"""レポート生成のオーケストレーション。

同定 → 各セクションを並列調査 → 貿易データ整形 → サマリー合成 → 結合。
進捗は progress(step_name, ratio) コールバックで通知。
"""
from __future__ import annotations

import datetime
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import comtrade, customs_jp, deep_research, nite, regulations
from .config import Settings
from .identity import ChemicalIdentity, resolve
from .llm import ResearchResult, research, synthesize


def enrich_identity(settings: Settings, ident: ChemicalIdentity) -> ChemicalIdentity:
    """PubChem で同定できなかった場合（日本語名など）、LLMで英名/CASを引き、
    その CAS で PubChem を再照会して情報を補完する。"""
    if ident.found or not settings.has_llm:
        return ident
    res = research(
        settings,
        f"化学品『{ident.query}』の英語名(English chemical name)とCAS番号を、"
        f"次の1行形式だけで答えてください（説明不要）: NAME=<英名> | CAS=<CAS番号>",
        max_tokens=300,
    )
    text = res.text
    cas_m = re.search(r"CAS\s*=\s*([\d-]+)", text)
    name_m = re.search(r"NAME\s*=\s*([^|\n]+)", text)
    cas = cas_m.group(1).strip() if cas_m else None
    eng = name_m.group(1).strip() if name_m else None
    new = None
    if cas:
        new = resolve(cas)
    if (not new or not new.found) and eng:
        new = resolve(eng)
    if new and new.found:
        new.query = ident.query  # 元のクエリ表示を保持
        new.query_type = ident.query_type
        return new
    # それでもダメなら元クエリを表示名として研究は続行
    if eng:
        ident.title = eng
    if cas:
        ident.cas = cas
    return ident


def guess_hs6(settings: Settings, ident: ChemicalIdentity) -> str | None:
    """HSコード6桁を推定（貿易データ取得用）。"""
    res = research(
        settings,
        f"化学品『{ident.display_name}』(CAS {ident.cas or '不明'})の最も妥当な"
        f"HSコードを6桁の数字のみで答えてください。説明不要、数字6桁だけ。",
        max_tokens=500,
    )
    m = re.search(r"\b(\d{6})\b", res.text.replace(".", ""))
    return m.group(1) if m else None


def _trade_markdown(snap: comtrade.TradeSnapshot) -> str:
    if not snap.ok:
        return (
            f"UN Comtrade からの自動取得はできませんでした"
            f"（HS {snap.hs_code or '?'}）。{snap.note}\n\n"
            "TradeMap でのご確認: https://www.trademap.org/"
        )
    lines = [
        f"**HSコード:** {snap.hs_code} / **対象年:** {snap.year}（UN Comtrade）",
        "",
    ]
    if snap.world_export_usd:
        lines.append(f"- 世界輸出総額: 約 {snap.world_export_usd/1e9:,.2f} 十億USD")
    if snap.world_import_usd:
        lines.append(f"- 世界輸入総額: 約 {snap.world_import_usd/1e9:,.2f} 十億USD")
    if snap.avg_unit_price_usd_per_kg:
        lines.append(f"- 参考単価（輸出加重平均）: 約 {snap.avg_unit_price_usd_per_kg:,.2f} USD/kg")
    lines.append("")
    if snap.top_exporters:
        lines.append("**主要輸出国 TOP10**\n")
        lines.append("| 国 | 輸出額(百万USD) | 単価(USD/kg) |")
        lines.append("|---|---:|---:|")
        for f in snap.top_exporters[:10]:
            up = f"{f.unit_price_usd_per_kg:,.2f}" if f.unit_price_usd_per_kg else "—"
            lines.append(f"| {f.country} | {f.value_usd/1e6:,.1f} | {up} |")
        lines.append("")
    if snap.top_importers:
        lines.append("**主要輸入国 TOP10**\n")
        lines.append("| 国 | 輸入額(百万USD) | 単価(USD/kg) |")
        lines.append("|---|---:|---:|")
        for f in snap.top_importers[:10]:
            up = f"{f.unit_price_usd_per_kg:,.2f}" if f.unit_price_usd_per_kg else "—"
            lines.append(f"| {f.country} | {f.value_usd/1e6:,.1f} | {up} |")
        lines.append("")
    lines.append("_出典: UN Comtrade Database (comtradeplus.un.org)_")
    return "\n".join(lines)


def _identity_markdown(ident: ChemicalIdentity) -> str:
    rows = [
        ("表示名", ident.display_name),
        ("IUPAC名", ident.iupac_name),
        ("CAS番号", ident.cas),
        ("分子式", ident.molecular_formula),
        ("分子量", ident.molecular_weight),
        ("SMILES", ident.canonical_smiles),
        ("InChIKey", ident.inchikey),
        ("PubChem CID", ident.cid),
    ]
    md = "| 項目 | 値 |\n|---|---|\n"
    for k, v in rows:
        if v:
            md += f"| {k} | {v} |\n"
    if ident.synonyms:
        md += f"\n**別名（抜粋）:** {', '.join(ident.synonyms[:12])}\n"
    if ident.cid:
        md += f"\n**一次情報:** [PubChem 化合物ページ](https://pubchem.ncbi.nlm.nih.gov/compound/{ident.cid})\n"
    return md


def _noop(*_a, **_k):
    pass


def generate(
    settings: Settings,
    query: str,
    *,
    hs_code: str | None = None,
    progress=_noop,
) -> dict:
    """フルレポートを生成して dict を返す。"""
    progress("化学物質を同定中 (PubChem)…", 0.05)
    ident = resolve(query)
    if not ident.found:
        progress("日本語名などを解決中 (AI)…", 0.1)
        ident = enrich_identity(settings, ident)

    # 無料枠の回数制限(5/分・モデル別/日)に収めるため、調査は2回の呼び出しに集約
    progress("商業インテリジェンスを調査中（市場・競争・価格）…", 0.2)
    commercial = deep_research.commercial(settings, ident)

    progress("規制・通関・物流を調査中（NITE/財務省/REACH）…", 0.45)
    compliance = regulations.compliance(settings, ident, hs_code)

    # 規制パートの「HSCODE: nnnnnn」からHSコードを取得（無ければユーザー指定）
    progress("世界貿易データを取得中 (UN Comtrade)…", 0.7)
    m = re.search(r"HSCODE[:：]\s*(\d{6})", compliance.text)
    hs6 = hs_code or (m.group(1) if m else None)
    snap = comtrade.get_trade(hs6, settings.comtrade_key) if hs6 else comtrade.TradeSnapshot(hs_code="")
    trade_md = _trade_markdown(snap)
    # 本文からHSCODE指示行を除去
    compliance_text = re.sub(r"\n?\*{0,2}HSCODE[:：].*", "", compliance.text)

    all_citations = list(commercial.citations) + list(compliance.citations)

    # エグゼクティブサマリー合成（3回目の呼び出し）
    progress("エグゼクティブ・サマリーを生成中…", 0.85)
    combined = f"{commercial.text[:9000]}\n\n{compliance_text[:7000]}"
    summary = synthesize(
        settings,
        f"""あなたは大手戦略コンサルティングファームのシニアコンサルタントです。
化学品『{ident.display_name}』に関する以下の調査資料をもとに、経営層・事業責任者向けの
エグゼクティブ・サマリーを作成してください。

要件:
- プロフェッショナルで簡潔な「だ・である」調の断定的な文体。AIらしい前置きや
  「〜と思われます」等の冗長表現は禁止。
- 数値・固有名詞を主語にした、示唆に富む文章。
- 構成（この見出しを使う）:
  **要旨**（3〜4文で全体像）/ **市場環境**（規模・成長・価格動向）/
  **競争構造**（主要プレイヤー・需給）/ **規制・物流上の論点** /
  **示唆と推奨アクション**（商社としての商機・リスクと打ち手を3点）
- 各項目は箇条書きを活用し、要点を太字で強調。
- 資料に無い数値は創作しない。

--- 調査資料 ---
{combined[:18000]}""",
        max_tokens=2500,
    )
    if not summary:
        summary = "_（サマリーは再生成時に作成されます）_"

    # 結合（プロフェッショナル・レポート体裁）
    now = datetime.datetime.now().strftime("%Y年%m月%d日")
    cas = ident.cas or "—"
    formula = ident.molecular_formula or "—"
    hs_disp = snap.hs_code or hs6 or "—"
    md = f"""<!--COVER
title={ident.display_name}
subtitle=化学品インテリジェンス・レポート
cas={cas}
formula={formula}
hs={hs_disp}
date={now}
-->

# 化学品インテリジェンス・レポート

## {ident.display_name}

| 項目 | 内容 |
|---|---|
| 対象物質 | {ident.display_name} |
| CAS登録番号 | {cas} |
| 分子式 | {formula} |
| HSコード | {hs_disp} |
| 作成日 | {now} |
| データソース | PubChem・NITE CHRIP・財務省貿易統計・UN Comtrade・ECHA／一次情報＋AI調査 |

---

# 1. エグゼクティブ・サマリー
{summary}

---

# 2. 物質同定情報
{_identity_markdown(ident)}

---

# 3. 製品・市場・競争環境・価格
{commercial.text}

---

# 4. 世界貿易フロー（UN Comtrade）
{trade_md}

---

# 5. 規制・通関・物流
{compliance_text}

**一次情報リンク:** [NITE CHRIP]({nite.CHRIP_TOP}) ／ [財務省 貿易統計]({customs_jp.CUSTOMS_STATS}) ／ [実行関税率表]({customs_jp.TARIFF_SCHEDULE})

---

# 出典・参考資料
{_dedupe_citations_md(all_citations)}

---

*免責事項：本レポートは公開情報およびAIによる調査を基に作成した参考資料である。
規制適合・取引可否の最終判断は、必ず一次情報（NITE CHRIP・財務省・ECHA・各社SDS等）
により確認されたい。*
"""
    progress("完了", 1.0)
    return {
        "identity": ident,
        "markdown": md,
        "citations": _dedupe_citations(all_citations),
        "hs_code": snap.hs_code or hs6 or "",
    }


def _dedupe_citations(cits: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in cits:
        url = c.get("url")
        if url and url not in seen:
            seen.add(url)
            out.append(c)
    return out


def _clean_title(c: dict) -> str:
    """出典の表示名。タイトルが無ければドメイン名を使う（長いリダイレクトURLは隠す）。"""
    t = (c.get("title") or "").strip()
    if t:
        return t
    url = c.get("url", "")
    m = re.search(r"https?://([^/]+)", url)
    return m.group(1) if m else "出典"


def _dedupe_citations_md(cits: list[dict]) -> str:
    out = _dedupe_citations(cits)
    if not out:
        return "_（自動収集された出典はありません）_"
    return "\n".join(
        f"{i}. [{_clean_title(c)}]({c['url']})" for i, c in enumerate(out, 1)
    )
