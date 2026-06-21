"""ディープリサーチ：世界の市場・サプライチェーン情報を出典付きで網羅。

メーカー・ユーザー・生産量・需要・用途・価格・トレンド・代替品・地政学リスク等を、
複数回のウェブ検索で「とにかく分厚く・正確に」収集する。
"""
from __future__ import annotations

from .identity import ChemicalIdentity
from .llm import ResearchResult, research

SYSTEM = (
    "あなたは化学品専門商社のシニアアナリストです。一次情報・業界レポート・"
    "企業IR・統計を重視し、数値には必ず出典年を付け、不確実な情報は断定せず"
    "『推定』『要確認』と明記します。日本語で、商社営業がそのまま顧客提案に使える"
    "実務的で具体的な内容を、長く厚く書きます。"
)


def _run(settings, prompt: str, max_tokens: int = 8000) -> ResearchResult:
    return research(settings, prompt, system=SYSTEM, max_tokens=max_tokens)


def overview(settings, ident: ChemicalIdentity) -> ResearchResult:
    name = ident.display_name
    cas = ident.cas or "不明"
    return _run(
        settings,
        f"""次の化学品の「概要と性状・用途」をウェブ検索で調べ、詳細にまとめてください。
物質: {name} / CAS: {cas} / 分子式: {ident.molecular_formula or '不明'}

## 概要
- どんな物質か、産業上の位置づけ
## 物理化学的性状
- 外観・沸点/融点・引火点・蒸気圧・水溶性・密度・安定性/反応性（数値で）
## 主な製造プロセス
- 工業的製法、主原料、副生物
## 主要用途（用途別の比率が分かれば%で）
- 各用途の概要と、その川下製品・最終製品
## 安全衛生の要点
- 主な有害性、ばく露管理の勘所
出典リンクを本文に。""",
    )


def market(settings, ident: ChemicalIdentity) -> ResearchResult:
    name = ident.display_name
    cas = ident.cas or "不明"
    return _run(
        settings,
        f"""次の化学品の「世界市場・生産・需要」を徹底的に調べてください。
物質: {name} / CAS: {cas}

## 市場規模
- 世界の市場規模（金額・数量）と直近の成長率(CAGR)、予測。年と出典を明記。
## 生産量・生産能力
- 世界・主要国別の生産量/生産能力、稼働状況。
## 需要
- 地域別・用途別の需要構成、需要ドライバー。
## 需給バランス
- 供給過剰/タイト、新増設・閉鎖の動き。
できる限り具体的な数値（トン、USD）と年・出典を。複数ソースで食い違う場合は併記。""",
    )


def players(settings, ident: ChemicalIdentity) -> ResearchResult:
    name = ident.display_name
    cas = ident.cas or "不明"
    return _run(
        settings,
        f"""次の化学品の「世界の主要プレイヤー」を調べ、表形式中心でまとめてください。
物質: {name} / CAS: {cas}

## 主要メーカー（世界）
- 会社名・本拠国・生産拠点・推定生産能力/シェア・特徴。可能な限り多く（10社以上目標）。
表: | メーカー | 国 | 生産拠点 | 能力/シェア | 備考 |
## 主要ユーザー・川下産業
- 代表的なユーザー企業／需要業界、用途とのひも付け。
## 日本市場のプレイヤー
- 国内メーカー・主要輸入元・主な需要家。
## サプライチェーン構造
- 原料→製造→流通→需要家の流れ、商社の関与余地。
出典リンクを付けること。""",
    )


def pricing_trends(settings, ident: ChemicalIdentity) -> ResearchResult:
    name = ident.display_name
    cas = ident.cas or "不明"
    return _run(
        settings,
        f"""次の化学品の「価格・トレンド・リスク」を調べてください。
物質: {name} / CAS: {cas}

## 価格
- 直近の市況価格レンジ（地域別・グレード別、USD/kg or USD/t）、価格決定要因、原料連動性。
- 過去数年の価格推移の概況。出典・年を明記。
## トレンド・将来性
- 技術動向、規制動向、需要シフト、新用途、ESG/脱炭素の影響。
## リスク要因
- 供給リスク（地政学・原料・特定国依存）、需要リスク、規制リスク、代替品の脅威。
## 代替品・競合品
- 競合する化学品・代替技術と、それぞれの優劣。
## 商社としての着眼点
- 取引機会、ポジショニング、想定マージン感、提案アイデアを具体的に。
価格は必ず「いつ時点・どこ・どのグレード」を明記。断定できないものは推定と明記。""",
    )
