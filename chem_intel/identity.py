"""PubChem (無料・キー不要) を使った化学物質の同定。

名前 / CAS / SMILES などから CID を解決し、別名・分子式・分子量・CAS・
構造識別子を取得する。NITE/法規制/貿易の各モジュールはこの結果を起点に動く。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
HEADERS = {"User-Agent": "chem-intel/1.0 (chemical trade research tool)"}
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")


@dataclass
class ChemicalIdentity:
    query: str
    query_type: str  # name | cas | hs | smiles
    cid: int | None = None
    iupac_name: str | None = None
    title: str | None = None  # PubChem 推奨表示名
    cas: str | None = None
    molecular_formula: str | None = None
    molecular_weight: str | None = None
    canonical_smiles: str | None = None
    inchikey: str | None = None
    synonyms: list[str] = field(default_factory=list)
    found: bool = False
    note: str = ""

    @property
    def display_name(self) -> str:
        return self.title or self.iupac_name or self.query

    def primary_terms(self) -> list[str]:
        """検索クエリに使う代表語（英名/CAS/和名候補）。"""
        terms: list[str] = []
        for t in [self.title, self.iupac_name, self.cas, self.query]:
            if t and t not in terms:
                terms.append(t)
        # 日本語別名があれば1つ拾う
        for s in self.synonyms:
            if any("一" <= ch <= "鿿" or "゠" <= ch <= "ヿ" for ch in s):
                terms.append(s)
                break
        return terms


def detect_query_type(q: str) -> str:
    q = q.strip()
    if CAS_RE.match(q):
        return "cas"
    if re.match(r"^\d{4}(\.\d{2}){0,2}$", q) or re.match(r"^\d{6,10}$", q):
        return "hs"
    return "name"


def _get(url: str, timeout: int = 20):
    return requests.get(url, headers=HEADERS, timeout=timeout)


def _cid_from(query: str, namespace: str) -> int | None:
    try:
        r = _get(f"{PUG}/compound/{namespace}/{requests.utils.quote(query)}/cids/JSON")
        if r.ok:
            ids = r.json().get("IdentifierList", {}).get("CID", [])
            return ids[0] if ids else None
    except Exception:
        return None
    return None


def _properties(cid: int) -> dict:
    props = (
        "IUPACName,MolecularFormula,MolecularWeight,"
        "CanonicalSMILES,InChIKey,Title"
    )
    try:
        r = _get(f"{PUG}/compound/cid/{cid}/property/{props}/JSON")
        if r.ok:
            rows = r.json().get("PropertyTable", {}).get("Properties", [])
            return rows[0] if rows else {}
    except Exception:
        return {}
    return {}


def _synonyms(cid: int) -> list[str]:
    try:
        r = _get(f"{PUG}/compound/cid/{cid}/synonyms/JSON")
        if r.ok:
            info = r.json().get("InformationList", {}).get("Information", [])
            return info[0].get("Synonym", []) if info else []
    except Exception:
        return []
    return []


def _pick_cas(synonyms: list[str]) -> str | None:
    for s in synonyms:
        if CAS_RE.match(s.strip()):
            return s.strip()
    return None


def resolve(query: str) -> ChemicalIdentity:
    """名前 / CAS / SMILES から同定。HS コードは PubChem では引けないので
    name 扱いに委ねる（呼び出し側で別途 HS を保持する想定）。"""
    query = query.strip()
    qtype = detect_query_type(query)
    ident = ChemicalIdentity(query=query, query_type=qtype)

    cid = None
    if qtype == "cas":
        cid = _cid_from(query, "name")  # CAS も name 名前空間で引ける
    elif qtype in ("name",):
        cid = _cid_from(query, "name")
    elif qtype == "smiles":
        cid = _cid_from(query, "smiles")

    if not cid and qtype != "hs":
        cid = _cid_from(query, "name")

    if not cid:
        ident.note = "PubChem で同定できませんでした（HSコード検索や、別名・英語名でお試しください）。"
        return ident

    ident.cid = cid
    props = _properties(cid)
    ident.iupac_name = props.get("IUPACName")
    ident.title = props.get("Title")
    ident.molecular_formula = props.get("MolecularFormula")
    ident.molecular_weight = props.get("MolecularWeight")
    ident.canonical_smiles = props.get("CanonicalSMILES")
    ident.inchikey = props.get("InChIKey")
    syns = _synonyms(cid)
    ident.synonyms = syns[:40]
    ident.cas = query if qtype == "cas" else _pick_cas(syns)
    ident.found = True
    return ident
