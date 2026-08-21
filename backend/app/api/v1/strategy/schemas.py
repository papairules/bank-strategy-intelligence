from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.application.strategy import (
    CrossDomainStrategicSignal,
    StrategicCoverageContext,
)


class StrategicSignalsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    generated_at: datetime
    generated_signal_count: int = Field(ge=0)
    coverage_context: StrategicCoverageContext
    signals: list[CrossDomainStrategicSignal]
    limitations: list[str]
