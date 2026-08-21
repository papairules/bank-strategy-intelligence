from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WellsFargoSearchSummary(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    title: str | None = None
    external_path: str | None = Field(default=None, validation_alias="externalPath")
    locations_text: str | None = Field(default=None, validation_alias="locationsText")
    posted_on: str | None = Field(default=None, validation_alias="postedOn")
    bullet_fields: list[str] = Field(default_factory=list, validation_alias="bulletFields")


class WellsFargoJobPostingInfo(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    title: str | None = None
    job_description: str | None = Field(default=None, validation_alias="jobDescription")
    location: str | None = None
    additional_locations: list[str] = Field(default_factory=list, validation_alias="additionalLocations")
    start_date: str | None = Field(default=None, validation_alias="startDate")
    time_type: str | None = Field(default=None, validation_alias="timeType")
    job_req_id: str | None = Field(default=None, validation_alias="jobReqId")
    external_url: str | None = Field(default=None, validation_alias="externalUrl")
    country: dict[str, Any] = Field(default_factory=dict)
    job_requisition_location: dict[str, Any] = Field(default_factory=dict, validation_alias="jobRequisitionLocation")


class WellsFargoJobDetail(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    job_posting_info: WellsFargoJobPostingInfo = Field(validation_alias="jobPostingInfo")
    hiring_organization: dict[str, Any] = Field(default_factory=dict, validation_alias="hiringOrganization")


class WellsFargoRawPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    search_summary: WellsFargoSearchSummary
    job_detail: WellsFargoJobDetail
