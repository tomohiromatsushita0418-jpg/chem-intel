"""UN Comtrade API による世界貿易データ取得（TradeMap の無料代替）。

HSコード(6桁)単位で、主要国の 輸出/輸入 額・数量・単価を集計する。
- COMTRADE_KEY あり → 本番エンドポイント
- 無し → public preview（主要国を一括クエリ、レート制限あり）
preview では国名(reporterDesc)が空で返るため、ローカルの M49 コード表で補完する。
"""
from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass, field

import requests

BASE = "https://comtradeapi.un.org"
HEADERS = {"User-Agent": "chem-intel/1.0"}

# 主要な化学品貿易国（M49 数値コード → 国名）。preview の国名欠落を補完。
COUNTRY: dict[int, str] = {
    842: "米国", 156: "中国", 276: "ドイツ", 392: "日本", 410: "韓国",
    699: "インド", 528: "オランダ", 56: "ベルギー", 251: "フランス", 826: "英国",
    380: "イタリア", 724: "スペイン", 76: "ブラジル", 490: "台湾", 702: "シンガポール",
    764: "タイ", 458: "マレーシア", 360: "インドネシア", 682: "サウジアラビア",
    643: "ロシア", 124: "カナダ", 484: "メキシコ", 616: "ポーランド", 792: "トルコ",
    757: "スイス", 36: "オーストラリア", 710: "南アフリカ", 784: "UAE",
    704: "ベトナム", 40: "オーストリア", 752: "スウェーデン",
    344: "香港", 152: "チリ", 32: "アルゼンチン", 620: "ポルトガル",
    203: "チェコ", 348: "ハンガリー", 246: "フィンランド", 578: "ノルウェー",
}
REPORTERS = ",".join(str(c) for c in COUNTRY)


@dataclass
class CountryFlow:
    country: str
    value_usd: float
    net_weight_kg: float | None = None

    @property
    def unit_price_usd_per_kg(self) -> float | None:
        if self.net_weight_kg and self.net_weight_kg > 0:
            return self.value_usd / self.net_weight_kg
        return None


@dataclass
class TradeSnapshot:
    hs_code: str
    year: int | None = None
    top_exporters: list[CountryFlow] = field(default_factory=list)
    top_importers: list[CountryFlow] = field(default_factory=list)
    world_export_usd: float | None = None
    world_import_usd: float | None = None
    avg_unit_price_usd_per_kg: float | None = None
    ok: bool = False
    note: str = ""


def _endpoint(key: str | None) -> tuple[str, dict]:
    if key:
        return (f"{BASE}/data/v1/get", {"Ocp-Apim-Subscription-Key": key})
    return (f"{BASE}/public/v1/preview", {})


def _fetch(hs6: str, flow: str, year: int, key: str | None) -> list[dict]:
    base, hdr = _endpoint(key)
    params = {
        "reporterCode": REPORTERS,
        "period": str(year),
        "partnerCode": "0",       # World
        "partner2Code": "0",
        "cmdCode": hs6,
        "flowCode": flow,         # X=輸出, M=輸入
        "customsCode": "C00",
        "motCode": "0",
    }
    r = requests.get(f"{base}/C/A/HS", headers={**HEADERS, **hdr}, params=params, timeout=45)
    if not r.ok:
        raise RuntimeError(f"Comtrade HTTP {r.status_code}")
    return r.json().get("data", []) or []


def _aggregate(rows: list[dict]) -> tuple[list[CountryFlow], float]:
    val_by: dict[int, float] = defaultdict(float)
    wgt_by: dict[int, float] = defaultdict(float)
    name_by: dict[int, str] = {}
    for row in rows:
        code = row.get("reporterCode")
        if code in (0, None):
            continue
        val_by[code] += float(row.get("primaryValue") or 0)
        wgt_by[code] += float(row.get("netWgt") or 0)
        desc = row.get("reporterDesc")
        if desc:
            name_by[code] = desc
    flows: list[CountryFlow] = []
    total = 0.0
    for code, val in val_by.items():
        name = COUNTRY.get(code) or name_by.get(code) or str(code)
        wgt = wgt_by.get(code) or None
        flows.append(CountryFlow(country=name, value_usd=val, net_weight_kg=wgt))
        total += val
    flows.sort(key=lambda f: f.value_usd, reverse=True)
    return flows, total


def get_trade(hs_code: str, key: str | None = None, year: int | None = None) -> TradeSnapshot:
    hs6 = "".join(c for c in (hs_code or "") if c.isdigit())[:6]
    snap = TradeSnapshot(hs_code=hs6)
    if len(hs6) < 6:
        snap.note = "6桁のHSコードが必要です（例: 290111）。"
        return snap

    years = [year] if year else [datetime.date.today().year - y for y in (2, 3, 4)]
    for yr in years:
        try:
            exports = _fetch(hs6, "X", yr, key)
            imports = _fetch(hs6, "M", yr, key)
            if not exports and not imports:
                continue
            exp_flows, exp_total = _aggregate(exports)
            imp_flows, imp_total = _aggregate(imports)
            snap.year = yr
            snap.top_exporters = exp_flows[:15]
            snap.top_importers = imp_flows[:15]
            snap.world_export_usd = exp_total or None
            snap.world_import_usd = imp_total or None
            tot_val = sum(f.value_usd for f in exp_flows if f.net_weight_kg)
            tot_wgt = sum(f.net_weight_kg for f in exp_flows if f.net_weight_kg)
            if tot_wgt > 0:
                snap.avg_unit_price_usd_per_kg = tot_val / tot_wgt
            snap.ok = True
            snap.note = "主要国ベース（preview）" if not key else "全申告国ベース"
            return snap
        except Exception as e:
            snap.note = f"取得エラー({yr}): {e}"
            continue
    if not snap.ok and not snap.note:
        snap.note = "対象年のデータが見つかりませんでした。"
    return snap
