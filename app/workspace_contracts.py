from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Setup(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    token: str = Field(min_length=20, max_length=256)
    company_name: str = Field(min_length=1, max_length=120)
    owner_display_name: str = Field(min_length=1, max_length=120)
    timezone: str = "Europe/Moscow"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Unknown timezone") from exc
        return value


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    display_name: str = Field(min_length=1, max_length=120)
    role: Literal["owner", "manager", "employee"] = "employee"
    team_id: Literal["operations", "procurement"] = "operations"


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Literal["owner", "manager", "employee"] | None = None
    team_id: Literal["operations", "procurement"] | None = None
    active: bool | None = None
