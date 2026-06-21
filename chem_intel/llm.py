"""Anthropic Claude クライアント + ウェブ検索ヘルパー。

web search server tool を使って、出典付きの調査結果テキストを返す。
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


def _client(settings: Settings):
    from anthropic import Anthropic

    return Anthropic(api_key=settings.anthropic_api_key)


def _extract(message) -> ResearchResult:
    """Messages API のレスポンスから本文と引用を抽出。"""
    text_parts: list[str] = []
    citations: list[dict] = []
    for block in message.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(block.text)
            for cit in getattr(block, "citations", None) or []:
                citations.append(
                    {
                        "title": getattr(cit, "title", None),
                        "url": getattr(cit, "url", None),
                    }
                )
        elif btype == "web_search_tool_result":
            for item in getattr(block, "content", None) or []:
                url = getattr(item, "url", None)
                if url:
                    citations.append(
                        {"title": getattr(item, "title", None), "url": url}
                    )
    return ResearchResult(text="".join(text_parts).strip(), citations=citations)


def research(
    settings: Settings,
    prompt: str,
    *,
    system: str | None = None,
    use_web: bool = True,
    model: str | None = None,
    max_tokens: int = 8000,
) -> ResearchResult:
    """ウェブ検索付きで Claude に調査させる。"""
    if not settings.has_llm:
        return ResearchResult(text="*(ANTHROPIC_API_KEY 未設定のため調査をスキップ)*")

    client = _client(settings)
    kwargs: dict = {
        "model": model or settings.research_model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    if use_web:
        kwargs["tools"] = [
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": settings.web_search_max_uses,
            }
        ]
    try:
        message = client.messages.create(**kwargs)
        return _extract(message)
    except Exception as e:  # API エラーでもアプリ全体は止めない
        return ResearchResult(text=f"*(調査中にエラー: {e})*")


def synthesize(settings: Settings, prompt: str, *, max_tokens: int = 4000) -> str:
    """ウェブ検索なしで要約・合成（エグゼクティブサマリー等）。"""
    if not settings.has_llm:
        return "*(ANTHROPIC_API_KEY 未設定)*"
    client = _client(settings)
    try:
        message = client.messages.create(
            model=settings.synthesis_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            b.text for b in message.content if getattr(b, "type", None) == "text"
        ).strip()
    except Exception as e:
        return f"*(合成中にエラー: {e})*"
