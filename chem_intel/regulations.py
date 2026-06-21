"""海外規制・物流規制の要約。

REACH/CLP(EU)、TSCA(米)、中国・韓国・その他主要国の化学物質規制、
および輸送規制(国連番号・IMDG/IATA/ADR・容器包装)をウェブ検索で確認。
"""
from __future__ import annotations

from .identity import ChemicalIdentity
from .llm import ResearchResult, research


def analyze_global(settings, ident: ChemicalIdentity) -> ResearchResult:
    name = ident.display_name
    cas = ident.cas or "（CAS不明）"
    prompt = f"""あなたは各国の化学物質規制の専門家です。次の物質の「海外」規制状況を、
ECHA等の一次情報をウェブ検索で確認し、正確にまとめてください。

対象物質: {name} / CAS: {cas}

出力（Markdown、日本語）:
## EU
- REACH（登録状況・登録トン数帯・SVHC候補/認可対象 Annex XIV・制限 Annex XVII 該当）
- CLP（調和分類 Annex VI のハザードクラス・H文言）
## 米国
- TSCA（インベントリ収載・重要新規利用規則SNUR・規制状況）
## アジア
- 中国（新化学物質環境管理弁法/危険化学品目録）、韓国（K-REACH）、台湾・東南アジア（分かる範囲）
## 国際条約
- ロッテルダム条約/ストックホルム条約/モントリオール議定書 等の該当
## 実務メモ
- 輸出先別に営業が注意すべき登録・届出の要点を3〜5行。

該当区分・トン数帯・指定日は出典付きで。不明は「要確認」。推測で断定しない。"""
    return research(settings, prompt, max_tokens=5000)


def analyze_logistics(settings, ident: ChemicalIdentity) -> ResearchResult:
    name = ident.display_name
    cas = ident.cas or "（CAS不明）"
    prompt = f"""あなたは危険物輸送の専門家です。次の物質の輸送・物流規制をウェブ検索で
確認し、正確にまとめてください。

対象物質: {name} / CAS: {cas}

出力（Markdown、日本語）:
## 危険物分類
- 国連番号(UN番号)・正式品名(PSN)・国連分類(クラス/等級)・容器等級(PG)・副次危険性
## モード別規制
- 海上(IMDG)、航空(IATA-DGR：旅客/貨物便の可否・数量制限)、陸上(日本の消防法/危規則、欧州ADR)
## 容器・表示
- 推奨容器、UN規格容器の要否、ラベル/マーク、混載禁止
## 保管
- 危険物倉庫の要否、保管温度・分離保管の注意
## 実務メモ
- フォワーダー手配・SDS手配で営業が注意すべき点を3〜5行。

UN番号やクラスは必ず根拠付きで。非危険物なら「非危険物（該当なし）」と明記。"""
    return research(settings, prompt, max_tokens=4500)
