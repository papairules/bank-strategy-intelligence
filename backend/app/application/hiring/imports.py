from typing import Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.application.hiring.collection import CollectedJob
from backend.app.domain.organization import OrganizationIdentity


class CanonicalJobIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization: OrganizationIdentity
    source_id: str = Field(pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
    external_job_id: str = Field(min_length=1, max_length=300)

    @field_validator("source_id", "external_job_id")
    @classmethod
    def strip_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source identity values must not be blank")
        return value

    @property
    def source_scoped_job_id(self) -> str:
        return f"{self.source_id}:{self.external_job_id}"

    @property
    def job_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, f"bsi:job:v1:{self._identity_value}")

    @property
    def evidence_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, f"bsi:evidence:v1:{self._identity_value}")

    @property
    def _identity_value(self) -> str:
        return "|".join(
            (self.organization.key, self.source_id, self.external_job_id)
        )


class CanonicalJobImport(CollectedJob):
    """Organization-neutral adapter output built from existing domain models."""

    model_config = ConfigDict(extra="forbid")

    identity: CanonicalJobIdentity

    @model_validator(mode="after")
    def validate_canonical_identity(self) -> Self:
        if self.posting.organization != self.identity.organization.display_name:
            raise ValueError("posting organization must match canonical organization")
        if self.posting.source_job_id != self.identity.source_scoped_job_id:
            raise ValueError("posting source_job_id must contain the scoped source identity")
        if self.posting.job_id != self.identity.job_id:
            raise ValueError("posting job_id must match canonical identity")
        if self.evidence.evidence_id != self.identity.evidence_id:
            raise ValueError("evidence_id must match canonical identity")
        if self.posting.source_url != self.evidence.source_url:
            raise ValueError("posting source_url must match evidence source_url")
        metadata = self.evidence.provenance_metadata
        expected = {
            "organization_key": self.identity.organization.key,
            "source_id": self.identity.source_id,
            "external_job_id": self.identity.external_job_id,
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ValueError("evidence provenance must preserve canonical source identity")
        return self
