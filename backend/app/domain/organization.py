import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator


def organization_key(display_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", display_name).encode("ascii", "ignore").decode()
    key = re.sub(r"[^a-z0-9]+", "_", normalized.casefold()).strip("_")
    if not key:
        raise ValueError("organization display name must contain letters or numbers")
    return key


class OrganizationIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    display_name: str = Field(min_length=1, max_length=200)

    @field_validator("key", "display_name")
    @classmethod
    def strip_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("organization identity values must not be blank")
        return value

    @classmethod
    def from_display_name(cls, display_name: str) -> "OrganizationIdentity":
        display_name = display_name.strip()
        return cls(key=organization_key(display_name), display_name=display_name)
