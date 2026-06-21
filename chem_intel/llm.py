"""LLMクライアント + ウェブ検索ヘルパー（マルチプロバイダ）。

- Gemini（無料枠・Google検索グラウンディング）… 既定・推奨
- Anthropic Claude（従量課金・web search tool）
どちらでも research()/synthesize() の戻り値は同じ ResearchResult。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Settings


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


def _gemini_research(settings, prompt, system, use_web, model, max_tokens) -> ResearchResult:
    from google.genai import types

    client = _gemini_client(settings)
    cfg_kwargs: dict = {"max_output_tokens": max_tokens}
    if system:
        cfg_kwargs["system_instruction"] = system
    if use_web:
        cfg_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    resp = client.models.generate_content(
        model=model or settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(**cfg_kwargs),
    )
    return _gemini_extract(resp)


def _gemini_synthesize(settings, prompt, max_tokens) -> str:
    from google.genai import types

    client = _gemini_client(settings)
    resp = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=max_tokens),
    )
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
    except Exception as e:
        return ResearchResult(text=f"*(調査中にエラー: {e})*")


def synthesize(settings: Settings, prompt: str, *, max_tokens: int = 4000) -> str:
    """ウェブ検索なしで要約・合成。"""
    provider = settings.provider
    if provider is None:
        return "*(AIキー未設定)*"
    try:
        if provider == "gemini":
            return _gemini_synthesize(settings, prompt, max_tokens)
        return _anthropic_synthesize(settings, prompt, max_tokens)
    except Exception as e:
        return f"*(合成中にエラー: {e})*"
