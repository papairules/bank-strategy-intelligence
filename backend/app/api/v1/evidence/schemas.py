from pydantic import ConfigDict

from backend.app.application.evidence import (
    EvidenceSummary,
    UnifiedEvidenceDetail,
    UnifiedEvidencePage,
)


class EvidenceSummaryResponse(EvidenceSummary):
    model_config = ConfigDict(extra="forbid")


class EvidenceRecordsResponse(UnifiedEvidencePage):
    model_config = ConfigDict(extra="forbid")


class EvidenceDetailResponse(UnifiedEvidenceDetail):
    model_config = ConfigDict(extra="forbid")
