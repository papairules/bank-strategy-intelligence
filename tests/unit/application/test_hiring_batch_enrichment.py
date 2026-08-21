import asyncio
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from backend.app.application.hiring import (
    BatchEnrichmentIdentity,
    BatchEnrichmentStatus,
    EnrichmentFailureCode,
    EnrichmentModelMetadata,
    EnrichmentSeniority,
    HiringBatchEnrichmentRequest,
    HiringBatchEnrichmentService,
    HiringEnrichmentError,
    HiringEnrichmentResult,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType


IDENTITY = BatchEnrichmentIdentity(provider="vertex_gemini", model="gemini-2.5-flash", prompt_schema_version="hiring-enrichment-v3")


def records(count=3, organization="Example Bank"):
    items = []
    for index in range(count):
        evidence_id = UUID(int=index + 1)
        posting = JobPosting(job_id=UUID(int=100 + index), organization=organization, source_job_id=f"R-{index}", title=f"Role {index}", description="Use SQL for analytics.", location="Charlotte, NC", country="US", posted_date=date(2026, 8, index + 1), source_url=f"https://example.test/{index}", evidence_id=evidence_id)
        evidence = Evidence(evidence_id=evidence_id, source_url=posting.source_url, source_type=SourceType.CAREER_SITE, retrieved_at=datetime(2026, 8, 20, tzinfo=timezone.utc), source_excerpt="Use SQL for analytics.", collector_identity="test")
        items.append((posting, evidence))
    return items


def enrichment(posting, evidence, *, model=IDENTITY.model, schema=IDENTITY.prompt_schema_version):
    return HiringEnrichmentResult(job_id=posting.job_id, evidence_id=evidence.evidence_id, seniority_level=EnrichmentSeniority.UNKNOWN, is_leadership=False, confidence=.5, model_metadata=EnrichmentModelMetadata(provider=IDENTITY.provider, model=model, prompt_schema_version=schema, enrichment_timestamp=datetime(2026, 8, 21, tzinfo=timezone.utc), model_confidence=.5))


class Read:
    def __init__(self, items): self.jobs=[item[0] for item in items]; self.evidence={item[1].evidence_id:item[1] for item in items}
    def list_jobs_for_analytics(self, organization): return [job for job in self.jobs if job.organization == organization]
    def get_evidence(self, evidence_id): return self.evidence.get(evidence_id)


class Enricher:
    def __init__(self, failures=None, mismatch=False): self.calls=[]; self.failures=failures or {}; self.mismatch=mismatch
    async def enrich(self, posting, evidence):
        self.calls.append(posting.job_id)
        if posting.job_id in self.failures: raise self.failures[posting.job_id]
        result=enrichment(posting,evidence)
        return result.model_copy(update={"job_id":uuid4()}) if self.mismatch else result


class Persistence:
    def __init__(self, existing=None, fail=False): self.current=set(existing or []); self.saved=[]; self.fail=fail
    def key(self, job_id, evidence_id, provider, model, prompt_schema_version): return (job_id,evidence_id,provider,model,prompt_schema_version)
    def has_current(self, **values): return self.key(**values) in self.current
    def save(self, value):
        if self.fail: raise RuntimeError("database secret")
        self.saved.append(value)
        m=value.model_metadata
        self.current.add(self.key(value.job_id,value.evidence_id,m.provider,m.model,m.prompt_schema_version))


def run(service, **values):
    return asyncio.run(service.execute(HiringBatchEnrichmentRequest(organization="Example Bank", **values)))


def create(items=None, **kwargs):
    items=items or records(); read=Read(items); enricher=kwargs.get("enricher",Enricher()); persistence=kwargs.get("persistence",Persistence())
    return HiringBatchEnrichmentService(read,enricher,persistence,IDENTITY),read,enricher,persistence


def test_dry_run_discovers_candidates_without_provider_or_writes():
    service,_,provider,persistence=create()
    result=run(service,dry_run=True,max_jobs=2)
    assert (result.discovered_jobs,result.eligible_jobs,result.planned_jobs,result.attempted_jobs,result.deferred_jobs)==(3,3,2,0,1)
    assert provider.calls == [] and persistence.saved == []
    assert [item.status for item in result.outcomes] == [BatchEnrichmentStatus.PLANNED,BatchEnrichmentStatus.PLANNED,BatchEnrichmentStatus.DEFERRED_LIMIT]


def test_existing_current_is_skipped_but_historical_version_is_eligible():
    items=records(2); current={(items[0][0].job_id,items[0][1].evidence_id,IDENTITY.provider,IDENTITY.model,IDENTITY.prompt_schema_version)}
    persistence=Persistence(current); service,_,provider,_=create(items,persistence=persistence)
    result=run(service,dry_run=True,max_jobs=2)
    assert result.existing_enrichment_skips == 1 and result.eligible_jobs == 1
    historical=enrichment(*items[1],model="older-model",schema="v2"); persistence.save(historical)
    assert run(service,dry_run=True,max_jobs=2).eligible_jobs == 1
    assert provider.calls == []


def test_success_is_called_once_persisted_and_repeated_run_is_idempotent():
    service,_,provider,persistence=create(records(1))
    first=run(service,dry_run=False,max_jobs=1)
    second=run(service,dry_run=False,max_jobs=1)
    assert first.enriched_jobs == 1 and first.attempted_jobs == 1
    assert second.existing_enrichment_skips == 1 and second.attempted_jobs == 0
    assert len(provider.calls) == len(persistence.saved) == 1


@pytest.mark.parametrize("continue_on_error,expected_calls,stopped", [(True,2,False),(False,1,True)])
def test_failure_policy_isolates_or_stops(continue_on_error,expected_calls,stopped):
    items=records(2); failure=HiringEnrichmentError(EnrichmentFailureCode.PROVIDER_UNAVAILABLE,"provider secret")
    provider=Enricher({items[0][0].job_id:failure}); service,_,_,persistence=create(items,enricher=provider)
    result=run(service,dry_run=False,max_jobs=2,continue_on_error=continue_on_error)
    assert len(provider.calls)==expected_calls and result.stopped_early is stopped
    assert result.failed_jobs == 1 and all(item.message != "provider secret" for item in result.outcomes)
    assert len(persistence.saved) == (1 if continue_on_error else 0)


def test_validation_identity_mismatch_and_provider_validation_are_not_persisted():
    for provider in [Enricher(mismatch=True),Enricher({records(1)[0][0].job_id:HiringEnrichmentError(EnrichmentFailureCode.VALIDATION_FAILURE,"unsafe")})]:
        items=records(1); provider.failures = {items[0][0].job_id: next(iter(provider.failures.values()))} if provider.failures else {}
        service,_,_,persistence=create(items,enricher=provider)
        result=run(service,dry_run=False,max_jobs=1)
        assert result.failed_jobs == 1 and persistence.saved == []
        assert result.outcomes[0].status == BatchEnrichmentStatus.FAILED_VALIDATION


def test_persistence_failure_is_sanitized_and_not_counted_enriched():
    service,_,provider,persistence=create(records(1),persistence=Persistence(fail=True))
    result=run(service,dry_run=False,max_jobs=1)
    assert len(provider.calls)==1 and persistence.saved == []
    assert result.enriched_jobs==0 and result.outcomes[0].status==BatchEnrichmentStatus.FAILED_PERSISTENCE
    assert "secret" not in result.outcomes[0].message


def test_missing_and_unusable_evidence_are_skipped():
    items=records(2); read=Read(items); read.evidence.pop(items[0][1].evidence_id)
    read.jobs[1]=read.jobs[1].model_copy(update={"description":" "}); read.evidence[items[1][1].evidence_id]=items[1][1].model_copy(update={"source_excerpt":" "})
    provider=Enricher(); persistence=Persistence(); service=HiringBatchEnrichmentService(read,provider,persistence,IDENTITY)
    result=run(service,dry_run=False,max_jobs=2)
    assert result.no_evidence_skips==1 and result.unusable_evidence_skips==1
    assert result.attempted_jobs==0 and provider.calls==[] and persistence.saved==[]


def test_evidence_identity_mismatch_is_skipped_before_provider():
    items=records(1); read=Read(items); read.evidence[items[0][1].evidence_id]=items[0][1].model_copy(update={"evidence_id":uuid4()})
    provider=Enricher(); persistence=Persistence(); service=HiringBatchEnrichmentService(read,provider,persistence,IDENTITY)
    result=run(service,dry_run=False,max_jobs=1)
    assert result.evidence_mismatch_skips == 1
    assert result.outcomes[0].status == BatchEnrichmentStatus.SKIPPED_EVIDENCE_MISMATCH
    assert provider.calls == [] and persistence.saved == []


def test_max_jobs_organization_isolation_and_deterministic_order():
    items=records(4)+records(1,"Other Bank"); service,_,provider,_=create(items)
    first=run(service,dry_run=False,max_jobs=2); assert first.discovered_jobs==4 and first.attempted_jobs==2 and len(provider.calls)==2
    dry1=run(create(records(4))[0],dry_run=True,max_jobs=2); dry2=run(create(list(reversed(records(4))))[0],dry_run=True,max_jobs=2)
    assert [item.job_id for item in dry1.outcomes] == [item.job_id for item in dry2.outcomes]


def test_request_bounds_are_conservative():
    with pytest.raises(ValidationError): HiringBatchEnrichmentRequest(organization="Bank",max_jobs=0)
    with pytest.raises(ValidationError): HiringBatchEnrichmentRequest(organization="Bank",max_jobs=26)
