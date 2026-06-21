"""化学品インテリジェンス — Streamlit アプリ。

検索（名前/CAS/HS）→ 自動ディープリサーチ → 分厚いレポート表示 →
PDF出力 → 履歴保存・再表示。
"""
from __future__ import annotations

import datetime
import json

import streamlit as st

from chem_intel import pdf_export, report, storage
from chem_intel.config import load_settings
from chem_intel.identity import detect_query_type

st.set_page_config(
    page_title="化学品インテリジェンス",
    page_icon="🧪",
    layout="wide",
)

settings = load_settings()
storage.init(settings)


def _filename(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40]
    return f"chem_report_{safe}_{datetime.datetime.now():%Y%m%d_%H%M}.pdf"


def show_report(markdown: str, display_name: str):
    st.markdown(markdown, unsafe_allow_html=True)
    st.divider()
    try:
        pdf_bytes = pdf_export.to_pdf(markdown, title=display_name)
        st.download_button(
            "📄 このレポートをPDFでダウンロード",
            data=pdf_bytes,
            file_name=_filename(display_name),
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception as e:
        st.warning(
            f"PDF生成に失敗しました（{e}）。下のMarkdownをコピーしてご利用ください。"
        )
        st.download_button(
            "⬇️ Markdownでダウンロード",
            data=markdown.encode("utf-8"),
            file_name=_filename(display_name).replace(".pdf", ".md"),
            mime="text/markdown",
            use_container_width=True,
        )


# ---------------- サイドバー：履歴 ----------------
with st.sidebar:
    st.header("🗂 検索履歴")
    hist_search = st.text_input("履歴を検索（名前/CAS/HS）", key="hist_search")
    history = storage.list_history(settings, hist_search or None, limit=100)
    if not history:
        st.caption("まだ履歴はありません。")
    for item in history:
        label = f"{item.display_name}"
        meta = " / ".join(filter(None, [item.cas, item.hs_code]))
        with st.container():
            if st.button(
                f"📑 {label}",
                key=f"open_{item.id}",
                use_container_width=True,
            ):
                st.session_state["view_id"] = item.id
            cap = item.created_at.strftime("%Y-%m-%d %H:%M")
            st.caption(f"{cap}　{meta}")

    st.divider()
    if not settings.has_llm:
        st.error(
            "AIキーが未設定です。GEMINI_API_KEY（無料・推奨）または "
            "ANTHROPIC_API_KEY を設定してください。"
        )
    else:
        st.caption(f"🤖 AIエンジン: **{settings.provider}**")
    if not settings.comtrade_key:
        st.caption("💡 COMTRADE_KEY 設定で貿易データの取得が安定します。")


# ---------------- メイン ----------------
st.title("🧪 化学品インテリジェンス")
st.caption(
    "新規化学品の特徴・規制・貿易・市場を自動で網羅調査し、分厚いレポートを生成します。"
)

col1, col2 = st.columns([3, 1])
with col1:
    query = st.text_input(
        "化学品名 / CAS番号 / HSコード で検索",
        placeholder="例: アクリロニトリル / 107-13-1 / 2926.10",
    )
with col2:
    hs_override = st.text_input("HSコード（任意）", placeholder="例: 292610")

run = st.button("🔍 レポート生成", type="primary", use_container_width=True)

if run and query.strip():
    st.session_state.pop("view_id", None)
    qtype = detect_query_type(query)
    st.info(f"クエリ種別: **{qtype}** として処理します。")
    progress_bar = st.progress(0.0)
    status = st.empty()

    def _progress(msg: str, ratio: float):
        status.write(f"⏳ {msg}")
        progress_bar.progress(min(max(ratio, 0.0), 1.0))

    with st.spinner("調査中…（数分かかる場合があります）"):
        result = report.generate(
            settings,
            query.strip(),
            hs_code=(hs_override.strip() or None),
            progress=_progress,
        )

    ident = result["identity"]
    # 履歴に保存
    rid = storage.save_report(
        settings,
        query=query.strip(),
        query_type=qtype,
        display_name=ident.display_name,
        cas=ident.cas,
        hs_code=result.get("hs_code"),
        formula=ident.molecular_formula,
        markdown=result["markdown"],
        citations=result["citations"],
    )
    status.success("✅ レポート生成完了（履歴に保存しました）")
    progress_bar.empty()
    show_report(result["markdown"], ident.display_name)

elif st.session_state.get("view_id"):
    rep = storage.get_report(settings, st.session_state["view_id"])
    if rep:
        st.success(f"履歴を表示中: {rep.display_name}（{rep.created_at:%Y-%m-%d %H:%M}）")
        c1, c2 = st.columns([1, 1])
        with c2:
            if st.button("🗑 この履歴を削除", use_container_width=True):
                storage.delete_report(settings, rep.id)
                st.session_state.pop("view_id", None)
                st.rerun()
        show_report(rep.markdown, rep.display_name)
    else:
        st.warning("レポートが見つかりませんでした。")
else:
    st.markdown(
        """
### 使い方
1. 上の検索欄に **化学品名・CAS番号・HSコード** のいずれかを入力
2. **レポート生成** をクリック（PubChemで同定 → 並列ディープリサーチ）
3. 生成された分厚いレポートを確認し、**PDF出力**
4. 過去の調査は左の **検索履歴** からいつでも再表示

#### このレポートに含まれる内容
- 物質同定（CAS/分子式/別名/構造）
- 概要・性状・用途
- 世界市場・需給・生産量
- **世界貿易データ（UN Comtrade：国別輸出入・単価）**
- 主要メーカー・ユーザー・サプライチェーン
- 価格・トレンド・リスク・商機
- 日本の規制（NITE CHRIP / 化審法・安衛法・毒劇法・消防法 等）
- 輸出入・関税（財務省 貿易統計）
- 海外規制（REACH/TSCA/各国）
- 物流・輸送規制（UN番号/IMDG/IATA 等）
"""
    )
