from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import TypedDict
from urllib.parse import urlparse, urlunparse

from langgraph.graph import END, START, StateGraph
from openai import OpenAI

from .models import (
    Evidence,
    EvidenceBatch,
    ResearchPlan,
    Source,
    StrategicSignal,
    StrategicSignalDrafts,
    StrategyAgentOutput,
)
from .prompts import (
    EVIDENCE_EXTRACTION_PROMPT,
    RESEARCH_PLANNER_PROMPT,
    STRATEGY_INFERENCE_PROMPT,
    STRATEGY_QUALITY_PROMPT,
)
from .search import search_web, source_priority

logger = logging.getLogger(__name__)


class StrategyState(TypedDict):
    company: str
    question: str
    time_horizon: str | None
    research_queries: list[str]
    sources: list[dict]
    evidence: list[dict]
    strategic_signals: list[dict]
    final_output: dict


class StrategyWorkflow:
    """Configured LangGraph node collection for one integrated strategy service."""

    def __init__(self, *, model: str, client_factory: Callable[[], OpenAI]) -> None:
        self.model = model
        self._client_factory = client_factory
        self._openai_client: OpenAI | None = None

    def client(self) -> OpenAI:
        if self._openai_client is None:
            self._openai_client = self._client_factory()
        return self._openai_client

    def research_planner(self, state: StrategyState) -> dict:
        try:
            response = self.client().responses.parse(
                model=self.model,
                instructions=RESEARCH_PLANNER_PROMPT,
                input=(
                    f"Company: {state['company']}\nQuestion: {state['question']}\n"
                    f"Time horizon: {state.get('time_horizon') or 'unspecified'}"
                ),
                text_format=ResearchPlan,
            )
            plan = response.output_parsed
        except Exception as exc:
            logger.warning("[research_planner] OpenAI call failed: %s", exc)
            plan = None
        queries = plan.queries if plan else []
        logger.info("[research_planner] generated %d queries", len(queries))
        return {"research_queries": queries}

    def source_retriever(self, state: StrategyState) -> dict:
        queries = state.get("research_queries", [])
        if not queries:
            logger.info("[source_retriever] retrieved 0 unique sources")
            return {"sources": []}
        try:
            client = self.client()
        except Exception as exc:
            logger.warning("[source_retriever] OpenAI client failed: %s", exc)
            return {"sources": []}
        unique: dict[str, Source] = {}
        for query in queries:
            try:
                for raw in search_web(query, client, self.model):
                    source = Source.model_validate(raw)
                    unique.setdefault(_canonical_url(source.url), source)
            except Exception as exc:
                logger.warning("[source_retriever] query failed (%s): %s", query, exc)
        sources = sorted(unique.values(), key=source_priority)[:20]
        for index, source in enumerate(sources, 1):
            source.source_id = f"SRC_{index:03d}"
        logger.info("[source_retriever] retrieved %d unique sources", len(sources))
        return {"sources": [source.model_dump() for source in sources]}

    def evidence_extractor(self, state: StrategyState) -> dict:
        sources = state.get("sources", [])
        if not sources:
            logger.info("[evidence_extractor] extracted 0 evidence items")
            return {"evidence": []}
        try:
            response = self.client().responses.parse(
                model=self.model,
                instructions=EVIDENCE_EXTRACTION_PROMPT,
                input=json.dumps(
                    {
                        "company": state["company"],
                        "question": state["question"],
                        "sources": sources,
                    }
                ),
                text_format=EvidenceBatch,
            )
            batch = response.output_parsed
        except Exception as exc:
            logger.warning("[evidence_extractor] OpenAI call failed: %s", exc)
            batch = None
        valid_sources = {item["source_id"]: item for item in sources}
        evidence: list[Evidence] = []
        for item in (batch.evidence if batch else []):
            source = valid_sources.get(item.source_id)
            if not source:
                continue
            item.source_url = source["url"]
            item.source_type = source["source_type"]
            item.publication_date = source.get("publication_date")
            item.evidence_id = f"EV_{len(evidence) + 1:03d}"
            evidence.append(item)
        logger.info("[evidence_extractor] extracted %d evidence items", len(evidence))
        return {"evidence": [item.model_dump() for item in evidence]}

    def strategy_inference(self, state: StrategyState) -> dict:
        evidence = state.get("evidence", [])
        if not evidence:
            logger.info("[strategy_inference] identified 0 candidate signals")
            return {"strategic_signals": []}
        try:
            response = self.client().responses.parse(
                model=self.model,
                instructions=STRATEGY_INFERENCE_PROMPT,
                input=json.dumps(
                    {
                        "company": state["company"],
                        "question": state["question"],
                        "time_horizon": state.get("time_horizon"),
                        "evidence": evidence,
                    }
                ),
                text_format=StrategicSignalDrafts,
            )
            drafts = response.output_parsed
        except Exception as exc:
            logger.warning("[strategy_inference] OpenAI call failed: %s", exc)
            drafts = None
        valid_ids = {item["evidence_id"] for item in evidence}
        signals = []
        for signal in (drafts.signals if drafts else []):
            ids = list(
                dict.fromkeys(
                    item for item in signal.supporting_evidence_ids if item in valid_ids
                )
            )
            if ids:
                signal.supporting_evidence_ids = ids
                signals.append(signal.model_dump())
        logger.info("[strategy_inference] identified %d candidate signals", len(signals))
        return {"strategic_signals": signals}

    def strategy_quality(self, state: StrategyState) -> dict:
        candidates = state.get("strategic_signals", [])
        if not candidates:
            logger.info("[strategy_quality] retained 0 strategic signals")
            return {"strategic_signals": []}
        evidence_lookup = {
            item["evidence_id"]: item for item in state.get("evidence", [])
        }
        review_input = []
        for candidate in candidates:
            supporting = [
                evidence_lookup[evidence_id]
                for evidence_id in candidate.get("supporting_evidence_ids", [])
                if evidence_id in evidence_lookup
            ]
            if supporting:
                review_input.append(
                    {"candidate": candidate, "supporting_evidence": supporting}
                )
        if not review_input:
            logger.info("[strategy_quality] retained 0 strategic signals")
            return {"strategic_signals": []}
        try:
            response = self.client().responses.parse(
                model=self.model,
                instructions=STRATEGY_QUALITY_PROMPT,
                input=json.dumps(
                    {
                        "company": state["company"],
                        "question": state["question"],
                        "time_horizon": state.get("time_horizon"),
                        "candidate_signals": review_input,
                    }
                ),
                text_format=StrategicSignalDrafts,
            )
            reviewed = response.output_parsed
        except Exception as exc:
            logger.warning(
                "[strategy_quality] OpenAI call failed; applying deterministic gate: %s",
                exc,
            )
            reviewed_signals = candidates
        else:
            reviewed_signals = [
                signal.model_dump() for signal in (reviewed.signals if reviewed else [])
            ]
        allowed_ids = {
            evidence_id
            for candidate in candidates
            for evidence_id in candidate.get("supporting_evidence_ids", [])
        }
        signals = []
        for raw_signal in reviewed_signals:
            ids = list(
                dict.fromkeys(
                    evidence_id
                    for evidence_id in raw_signal["supporting_evidence_ids"]
                    if evidence_id in evidence_lookup and evidence_id in allowed_ids
                )
            )
            items = [
                Evidence.model_validate(evidence_lookup[evidence_id])
                for evidence_id in ids
            ]
            if (
                ids
                and _passes_minimum_evidence(items)
                and _passes_question_strength(state["question"], items)
                and _passes_temporal_consistency(items)
                and not _is_self_negating(raw_signal["hypothesis"])
            ):
                signals.append({**raw_signal, "supporting_evidence_ids": ids})
        logger.info("[strategy_quality] retained %d strategic signals", len(signals))
        return {"strategic_signals": signals}

    def confidence_scorer(self, state: StrategyState) -> dict:
        lookup = {
            item["evidence_id"]: Evidence.model_validate(item)
            for item in state.get("evidence", [])
        }
        signals = []
        for raw in state.get("strategic_signals", []):
            items = [
                lookup[item]
                for item in raw["supporting_evidence_ids"]
                if item in lookup
            ]
            if not items:
                continue
            breakdown = _confidence_breakdown(items)
            signals.append(
                StrategicSignal(
                    **raw,
                    confidence=round(min(sum(breakdown.values()), 1.0), 2),
                    confidence_breakdown=breakdown,
                    evidence=items,
                ).model_dump()
            )
        logger.info("[confidence_scorer] scored %d signals", len(signals))
        return {"strategic_signals": signals}

    @staticmethod
    def final_output(state: StrategyState) -> dict:
        signals = [
            StrategicSignal.model_validate(item)
            for item in state.get("strategic_signals", [])
        ]
        output = StrategyAgentOutput(
            company=state["company"],
            question=state["question"],
            time_horizon=state.get("time_horizon"),
            strategic_signals=signals,
            message=(
                None
                if signals
                else "Insufficient evidence to identify a reliable strategic direction."
            ),
        )
        return {"final_output": output.model_dump(exclude_none=True)}

    def compile(self):
        workflow = StateGraph(StrategyState)
        nodes = [
            ("research_planner", self.research_planner),
            ("source_retriever", self.source_retriever),
            ("evidence_extractor", self.evidence_extractor),
            ("strategy_inference", self.strategy_inference),
            ("strategy_quality", self.strategy_quality),
            ("confidence_scorer", self.confidence_scorer),
            ("final_output", self.final_output),
        ]
        for name, node in nodes:
            workflow.add_node(name, node)
        workflow.add_edge(START, "research_planner")
        workflow.add_edge("research_planner", "source_retriever")
        workflow.add_edge("source_retriever", "evidence_extractor")
        workflow.add_edge("evidence_extractor", "strategy_inference")
        workflow.add_edge("strategy_inference", "strategy_quality")
        workflow.add_edge("strategy_quality", "confidence_scorer")
        workflow.add_edge("confidence_scorer", "final_output")
        workflow.add_edge("final_output", END)
        return workflow.compile()


def build_graph(
    *,
    model: str,
    api_key: str,
    client_factory: Callable[[], OpenAI] | None = None,
):
    factory = client_factory or (lambda: OpenAI(api_key=api_key))
    return StrategyWorkflow(model=model, client_factory=factory).compile()


def initial_state(
    *, company: str, question: str, time_horizon: str | None
) -> StrategyState:
    return {
        "company": company,
        "question": question,
        "time_horizon": time_horizon,
        "research_queries": [],
        "sources": [],
        "evidence": [],
        "strategic_signals": [],
        "final_output": {},
    }


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower().removeprefix("www."),
            parsed.path.rstrip("/"),
            "",
            "",
            "",
        )
    )


_TIER_1_SOURCE_TYPES = {
    "earnings_release",
    "quarterly_report",
    "annual_report",
    "sec_filing",
    "investor_presentation",
    "earnings_call",
    "company_strategy_page",
    "company_announcement",
}
_FORWARD_GUIDANCE_PATTERN = re.compile(
    r"\b(?:we\s+(?:will|plan|expect|intend|aim|are\s+expanding|continue)|"
    r"our\s+(?:priority|plan|strategy|focus)\s+is|"
    r"(?:plans?|expects?|intends?|aims?|targets?)\s+to|"
    r"(?:will|would)\s+(?:invest|expand|grow|transform|simplify|reduce|optimize|"
    r"reallocate|exit|continue)|remains?\s+(?:a|our|the)\s+(?:top\s+)?priority)\b",
    re.IGNORECASE,
)


def _passes_minimum_evidence(items: list[Evidence]) -> bool:
    if len(items) >= 2 and len({item.source_id for item in items}) >= 2:
        return True
    return any(
        item.source_type in _TIER_1_SOURCE_TYPES
        and bool(_FORWARD_GUIDANCE_PATTERN.search(item.statement))
        for item in items
    )


_SELF_NEGATING_HYPOTHESIS_PATTERN = re.compile(
    r"\b(?:not|isn['’]t|does\s+not|rather\s+than)\b.{0,100}\b"
    r"(?:major|standalone|current|near-term)\b.{0,60}\bpriority\b",
    re.IGNORECASE,
)
_MAJOR_PRIORITY_QUESTION_PATTERN = re.compile(
    r"\bmajor\b.{0,80}\b(?:priority|priorities)\b|"
    r"\b(?:priority|priorities)\b.{0,80}\bmajor\b",
    re.IGNORECASE,
)
_YES_NO_QUESTION_PATTERN = re.compile(
    r"^\s*(?:is|are|was|were|will|would|can|could|does|do|did|has|have|should)\b",
    re.IGNORECASE,
)
_EXPLICIT_PRIORITY_EVIDENCE_PATTERN = re.compile(
    r"\b(?:major|top|core|key|primary|principal)\s+(?:business\s+|strategic\s+|"
    r"investment\s+)?(?:priority|priorities|focus|initiative)|"
    r"\b(?:priority|priorities)\s+(?:is|are|include|remain|continues?\s+to\s+be)\b",
    re.IGNORECASE,
)
_COMPLETED_ACTIVITY_PATTERN = re.compile(
    r"\b(?:completed?|fully\s+exited|has\s+rebuilt|had\s+completed|previously)\b",
    re.IGNORECASE,
)
_ACTIVE_ACTIVITY_PATTERN = re.compile(
    r"\b(?:is|are|continues?|remain(?:s)?|currently)\s+(?:focused|focusing|investing|"
    r"increasing|expanding|building|changing|reducing|simplifying|transforming|optimizing|"
    r"modernizing|prioritizing|advancing|executing|bringing|shifting|realigning|consolidating)\b",
    re.IGNORECASE,
)


def _is_self_negating(hypothesis: str) -> bool:
    return bool(_SELF_NEGATING_HYPOTHESIS_PATTERN.search(hypothesis))


def _passes_question_strength(question: str, items: list[Evidence]) -> bool:
    if (
        not _YES_NO_QUESTION_PATTERN.search(question)
        or not _MAJOR_PRIORITY_QUESTION_PATTERN.search(question)
    ):
        return True
    return any(
        _EXPLICIT_PRIORITY_EVIDENCE_PATTERN.search(item.statement) for item in items
    )


def _passes_temporal_consistency(items: list[Evidence]) -> bool:
    has_completed = any(
        _COMPLETED_ACTIVITY_PATTERN.search(item.statement) for item in items
    )
    if not has_completed:
        return True
    return any(
        _FORWARD_GUIDANCE_PATTERN.search(item.statement)
        or _ACTIVE_ACTIVITY_PATTERN.search(item.statement)
        for item in items
    )


def _recent(publication_date: str | None) -> bool:
    if not publication_date:
        return False
    try:
        value = datetime.fromisoformat(
            publication_date.replace("Z", "+00:00")
        ).date()
    except ValueError:
        return False
    return value >= date.today() - timedelta(days=548)


def _confidence_breakdown(items: list[Evidence]) -> dict[str, float]:
    official_types = {
        "earnings_release",
        "annual_report",
        "quarterly_report",
        "sec_filing",
        "investor_presentation",
        "company_announcement",
        "company_strategy_page",
    }
    leadership_types = {
        "earnings_release",
        "earnings_call",
        "leadership_statement",
    }
    external_types = {"news", "industry_research"}
    return {
        "official_source": 0.30
        if any(item.source_type in official_types for item in items)
        else 0.0,
        "leadership_or_earnings": 0.25
        if any(item.source_type in leadership_types for item in items)
        else 0.0,
        "multiple_sources": 0.20
        if len({item.source_id for item in items}) >= 2
        else 0.0,
        "independent_confirmation": 0.15
        if any(item.source_type in external_types for item in items)
        else 0.0,
        "recency": 0.10 if any(_recent(item.publication_date) for item in items) else 0.0,
    }
