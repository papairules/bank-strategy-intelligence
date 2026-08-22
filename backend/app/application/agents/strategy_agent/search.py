from __future__ import annotations

import logging
import re
import warnings
from urllib.parse import urlparse

from openai import OpenAI

from .models import SearchResults, Source

logger = logging.getLogger(__name__)

_REPORT_YEAR_PATTERN = re.compile(
    r"\b(20\d{2})\s+(?:annual\s+report|form\s+10-k)\b", re.IGNORECASE
)
_URL_REPORT_YEAR_PATTERN = re.compile(
    r"/(20\d{2})/(?:[^/]+/)*(?:annual[-_]?report|report)", re.IGNORECASE
)


def _publisher(url: str) -> str | None:
    return urlparse(url).netloc.removeprefix("www.") or None


def _canonical(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.netloc.lower().removeprefix('www.')}{parsed.path.rstrip('/')}"


def _check_source_metadata(source: Source) -> None:
    title_match = _REPORT_YEAR_PATTERN.search(source.title)
    url_match = _URL_REPORT_YEAR_PATTERN.search(urlparse(source.url).path)
    if title_match and url_match and title_match.group(1) != url_match.group(1):
        logger.warning(
            "[source_retriever] ambiguous report years for %s "
            "(title=%s, url_path=%s); publication date was not inferred",
            source.url,
            title_match.group(1),
            url_match.group(1),
        )


def _tool_urls(value: object) -> set[str]:
    if hasattr(value, "model_dump"):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            value = value.model_dump()
    if isinstance(value, dict):
        found = {str(value["url"])} if isinstance(value.get("url"), str) else set()
        for child in value.values():
            found.update(_tool_urls(child))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for child in value:
            found.update(_tool_urls(child))
        return found
    return set()


def search_web(
    query: str,
    client: OpenAI,
    model: str,
    max_results: int = 4,
) -> list[dict]:
    """Run OpenAI web search and retain only URLs present in tool citations."""
    prompt = f"""Search the web for: {query}
Return up to {max_results} useful results. Prefer original company/investor/filing sources,
then Reuters, Bloomberg, FT, WSJ, and reputable trade news. For every result return its real
canonical URL, title, publisher, source type, publication date when visible, and a concise
fact-rich content summary. Preserve explicit metadata from the retrieved page. A report year or
URL year is not necessarily its publication date: return publication_date only when a complete
calendar date is explicitly shown, in YYYY-MM-DD form. Otherwise return null. Never construct,
complete, or guess a partial date or report year."""
    kwargs = dict(
        model=model,
        input=prompt,
        text_format=SearchResults,
        include=["web_search_call.action.sources"],
    )
    try:
        response = client.responses.parse(tools=[{"type": "web_search"}], **kwargs)
    except Exception as first_error:
        logger.debug("web_search failed; trying compatibility tool: %s", first_error)
        response = client.responses.parse(
            tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
            **kwargs,
        )
    parsed = response.output_parsed
    if not parsed:
        return []
    cited_urls = {_canonical(url) for url in _tool_urls(response.output)}
    normalized: list[dict] = []
    for item in parsed.results[:max_results]:
        if not item.url or not item.content.strip() or _canonical(item.url) not in cited_urls:
            continue
        data = item.model_dump()
        data["publisher"] = item.publisher or _publisher(item.url)
        _check_source_metadata(Source.model_validate(data))
        normalized.append(data)
    return normalized


def source_priority(source: Source) -> int:
    ranks = {
        "earnings_release": 0,
        "quarterly_report": 1,
        "annual_report": 2,
        "sec_filing": 3,
        "investor_presentation": 4,
        "earnings_call": 5,
        "company_announcement": 6,
        "company_strategy_page": 6,
        "leadership_statement": 7,
        "news": 8,
        "industry_research": 9,
        "other": 10,
    }
    return ranks[source.source_type]
