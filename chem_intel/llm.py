"""LLMクライアント + ウェブ検索ヘルパー（マルチプロバイダ）。

- Gemini（無料枠・Google検索グラウンディング）… 既定・推奨
- Anthropic Claude（従量課金・web search tool）
どちらでも research()/synthesize() の戻り値は同じ ResearchResult。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Settings

# 規制・通関セクション共通のプロフェッショナル文体指示
PRO_SYSTEM = (
    "あなたは化学品の規制・通関を専門とする実務コンサルタント。一次情報を重視し、"
    "根拠（政令・告示番号、条文、登録区分等）を併記する。不明点は『要確認』と明記。"
    "文体は実務レポートの『だ・である』調で簡潔・断定的。AIらしい前置きやヘッジ、"
    "絵文字は使わない。見出しと箇条書きで構造化し、重要事項は太字で示す。日本語。"
)


@dataclass
class ResearchResult:
    text: str
    citations: list[dict] = field(default_factory=list)  # {title, url}

    def citations_markdown(self) -> str:
        if not self.citations:
            return ""
        seen, lines = set(), []
        for c in self.citations:
            url = c.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            title = c.get("title") or url
            lines.append(f"- [{title}]({url})")
        return "\n".join(lines)


# ============================ Anthropic ============================
def _anthropic_client(settings: Settings):
    from anthropic import Anthropic

    return Anthropic(api_key=settings.anthropic_api_key)


def _anthropic_extract(message) -> ResearchResult:
    text_parts: list[str] = []
    citations: list[dict] = []
    for block in message.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(block.text)
            for cit in getattr(block, "citations", None) or []:
                citations.append(
                    {"title": getattr(cit, "title", None), "url": getattr(cit, "url", None)}
                )
        elif btype == "web_search_tool_result":
            for item in getattr(block, "content", None) or []:
                url = getattr(item, "url", None)
                if url:
                    citations.append({"title": getattr(item, "title", None), "url": url})
    return ResearchResult(text="".join(text_parts).strip(), citations=citations)


def _anthropic_research(settings, prompt, system, use_web, model, max_tokens) -> ResearchResult:
    client = _anthropic_client(settings)
    kwargs: dict = {
        "model": model or settings.research_model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    if use_web:
        kwargs["tools"] = [
            {"type": "web_search_20250305", "name": "web_search",
             "max_uses": settings.web_search_max_uses}
        ]
    message = client.messages.create(**kwargs)
    return _anthropic_extract(message)


def _anthropic_synthesize(settings, prompt, max_tokens) -> str:
    client = _anthropic_client(settings)
    message = client.messages.create(
        model=settings.synthesis_model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in message.content if getattr(b, "type", None) == "text").strip()


# ============================ Gemini ============================
def _gemini_client(settings: Settings):
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


def _gemini_extract(resp) -> ResearchResult:
    text = getattr(resp, "text", None) or ""
    citations: list[dict] = []
    try:
        for cand in getattr(resp, "candidates", None) or []:
            gm = getattr(cand, "grounding_metadata", None)
            for chunk in (getattr(gm, "grounding_chunks", None) or []) if gm else []:
                web = getattr(chunk, "web", None)
                if web and getattr(web, "uri", None):
                    citations.append({"title": getattr(web, "title", None), "url": web.uri})
    except Exception:
        pass
    return ResearchResult(text=text.strip(), citations=citations)


# 過負荷(503)・レート(429)時に順に試す予備モデル
_GEMINI_FALLBACKS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
_TRANSIENT = ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED",
              "high demand", "overloaded", "rate limit")


def _is_transient(err: Exception) -> bool:
    s = str(err)
    return any(t.lower() in s.lower() for t in _TRANSIENT)


def _gemini_generate(settings, prompt, system, use_web, model, max_tokens):
    """503/429を自動リトライ＋予備モデルへフォールバックして生成。"""
    import time

    from google.genai import types

    client = _gemini_client(settings)
    cfg_kwargs: dict = {"max_output_tokens": max_tokens}
    if system:
        cfg_kwargs["system_instruction"] = system
    if use_web:
        cfg_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    cfg = types.GenerateContentConfig(**cfg_kwargs)

    # 試行するモデル順（指定→既定→予備）
    models: list[str] = []
    for m in [model, settings.gemini_model, *_GEMINI_FALLBACKS]:
        if m and m not in models:
            models.append(m)

    last_err: Exception | None = None
    for mdl in models:
        for attempt in range(3):  # 各モデル最大3回
            try:
                return client.models.generate_content(
                    model=mdl, contents=prompt, config=cfg
                )
            except Exception as e:  # noqa: BLE001
                last_err = e
                if _is_transient(e) and attempt < 2:
                    time.sleep(2 * (attempt + 1))  # 2s,4s バックオフ
                    continue
                break  # 非一時エラー→次モデルへ
    raise last_err if last_err else RuntimeError("Gemini生成に失敗")


def _gemini_research(settings, prompt, system, use_web, model, max_tokens) -> ResearchResult:
    return _gemini_extract(
        _gemini_generate(settings, prompt, system, use_web, model, max_tokens)
    )


def _gemini_synthesize(settings, prompt, max_tokens) -> str:
    resp = _gemini_generate(settings, prompt, None, False, None, max_tokens)
    return (getattr(resp, "text", None) or "").strip()


# ============================ 共通インターフェース ============================
def research(
    settings: Settings,
    prompt: str,
    *,
    system: str | None = None,
    use_web: bool = True,
    model: str | None = None,
    max_tokens: int = 8000,
) -> ResearchResult:
    """ウェブ検索付きで調査。プロバイダは settings.provider で自動選択。"""
    provider = settings.provider
    if provider is None:
        return ResearchResult(text="*(AIキー未設定のため調査をスキップ)*")
    try:
        if provider == "gemini":
            return _gemini_research(settings, prompt, system, use_web, model, max_tokens)
        return _anthropic_research(settings, prompt, system, use_web, model, max_tokens)
    except Exception:
        # 生のAPIエラーは出さず、後段で再試行できる旨だけ示す
        return ResearchResult(
            text="> 本セクションは一時的なアクセス集中のため取得できませんでした。"
            "再生成で解消します。"
        )


def synthesize(settings: Settings, prompt: str, *, max_tokens: int = 4000) -> str:
    """ウェブ検索なしで要約・合成。"""
    provider = settings.provider
    if provider is None:
        return "*(AIキー未設定)*"
    try:
        if provider == "gemini":
            return _gemini_synthesize(settings, prompt, max_tokens)
        return _anthropic_synthesize(settings, prompt, max_tokens)
    except Exception:
        return ""
