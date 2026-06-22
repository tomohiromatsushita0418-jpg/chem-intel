"""集中設定。環境変数 / Streamlit secrets の両方から読む。"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get(key: str, default: str | None = None) -> str | None:
    """環境変数を優先し、無ければ Streamlit secrets を見る。"""
    val = os.environ.get(key)
    if val:
        return val
    try:
        import streamlit as st  # 遅延 import（CLIからも使えるように）

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default


@dataclass
class Settings:
    # --- AIプロバイダ（どちらか一方でOK） ---
    gemini_api_key: str | None      # Google Gemini（無料枠あり・推奨）
    anthropic_api_key: str | None   # Anthropic Claude（従量課金）
    # ディープリサーチ／法規制要約に使うモデル（web search 対応）
    research_model: str
    # 最終サマリー合成に使うモデル
    synthesis_model: str
    # Gemini 用モデル
    gemini_model: str
    # UN Comtrade の subscription key（無くても動くが推奨）
    comtrade_key: str | None
    # 履歴永続化用。設定が無ければローカル SQLite に保存。
    database_url: str | None
    # web search の最大呼び出し回数（コスト制御）
    web_search_max_uses: int

    @property
    def provider(self) -> str | None:
        """利用するAIプロバイダ。Gemini を優先（無料枠のため）。"""
        if self.gemini_api_key:
            return "gemini"
        if self.anthropic_api_key:
            return "anthropic"
        return None

    @property
    def has_llm(self) -> bool:
        return self.provider is not None


def load_settings() -> Settings:
    return Settings(
        gemini_api_key=_get("GEMINI_API_KEY"),
        anthropic_api_key=_get("ANTHROPIC_API_KEY"),
        research_model=_get("RESEARCH_MODEL", "claude-sonnet-4-6"),
        synthesis_model=_get("SYNTHESIS_MODEL", "claude-opus-4-8"),
        gemini_model=_get("GEMINI_MODEL", "gemini-flash-latest"),
        comtrade_key=_get("COMTRADE_KEY"),
        database_url=_get("DATABASE_URL"),
        web_search_max_uses=int(_get("WEB_SEARCH_MAX_USES", "8")),
    )
