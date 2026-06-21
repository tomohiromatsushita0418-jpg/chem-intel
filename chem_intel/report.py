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
        md += f"\n🔗 [PubChem で見る](https://pubchem.ncbi.nlm.nih.gov/compound/{ident.cid})\n"
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

    # 並列で各調査を実行
    progress("各セクションを並列調査中…", 0.15)
    tasks: dict[str, callable] = {
        "overview": lambda: deep_research.overview(settings, ident),
        "market": lambda: deep_research.market(settings, ident),
        "players": lambda: deep_research.players(settings, ident),
        "pricing": lambda: deep_research.pricing_trends(settings, ident),
        "nite": lambda: nite.analyze(settings, ident),
        "customs": lambda: customs_jp.analyze(settings, ident, hs_code),
        "reg_global": lambda: regulations.analyze_global(settings, ident),
        "logistics": lambda: regulations.analyze_logistics(settings, ident),
    }
    results: dict[str, ResearchResult] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fn): key for key, fn in tasks.items()}
        done = 0
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception as e:
                results[key] = ResearchResult(text=f"*(調査失敗: {e})*")
            done += 1
            progress(f"調査中… ({done}/{len(tasks)})", 0.15 + 0.6 * done / len(tasks))

    # 貿易データ
    progress("世界貿易データを取得中 (UN Comtrade)…", 0.8)
    hs6 = hs_code or guess_hs6(settings, ident)
    snap = comtrade.get_trade(hs6, settings.comtrade_key) if hs6 else comtrade.TradeSnapshot(hs_code="")
    trade_md = _trade_markdown(snap)

    # 引用を集約
    all_citations: list[dict] = []
    for r in results.values():
        all_citations.extend(r.citations)

    # エグゼクティブサマリー合成
    progress("エグゼクティブサマリーを生成中…", 0.9)
    combined = "\n\n".join(
        f"## {k}\n{results[k].text[:2500]}" for k in results
    )
    summary = synthesize(
        settings,
        f"""以下は化学品『{ident.display_name}』の調査資料です。これを読んで、
化学品商社の営業がひと目で要点を掴めるエグゼクティブサマリーを、Markdownで
作成してください。構成: ①この物質は何か（2-3行）②市場のポイント（規模/成長/価格）
③主要メーカー・需要 ④規制・物流の注意点 ⑤商社としての商機・リスク。
箇条書き中心、各項目簡潔に。資料に無い情報は創作しないこと。

--- 資料 ---
{combined[:18000]}""",
        max_tokens=2500,
    )

    # 結合
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    md = f"""# 化学品インテリジェンスレポート：{ident.display_name}

_生成日時: {now}　|　クエリ: `{query}`_

---

## 📋 エグゼクティブサマリー
{summary}

---

## 🧪 物質同定情報
{_identity_markdown(ident)}

---

## 📖 概要・性状・用途
{results['overview'].text}

---

## 📊 世界市場・需給
{results['market'].text}

---

## 🌐 世界貿易データ（UN Comtrade）
{trade_md}

---

## 🏭 主要メーカー・ユーザー・サプライチェーン
{results['players'].text}

---

## 💰 価格・トレンド・リスク・商機
{results['pricing'].text}

---

## ⚖️ 日本の規制（NITE CHRIP / 各省庁）
{results['nite'].text}

---

## 🛃 輸出入・関税（財務省 貿易統計）
{results['customs'].text}

---

## 🌍 海外規制（REACH/TSCA/各国）
{results['reg_global'].text}

---

## 🚚 物流・輸送規制
{results['logistics'].text}

---

## 🔗 主要出典
{_dedupe_citations_md(all_citations)}

---

_本レポートは公開情報とAIによる調査を基にした参考資料です。最終的な規制判断・
取引判断は一次情報（NITE CHRIP・財務省・ECHA・SDS等）で必ずご確認ください。_
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


def _dedupe_citations_md(cits: list[dict]) -> str:
    out = _dedupe_citations(cits)
    if not out:
        return "_（自動収集された出典はありません）_"
    return "\n".join(f"- [{c.get('title') or c['url']}]({c['url']})" for c in out)
