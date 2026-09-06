from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Actor(DTO):
    id: str
    organization_id: str
    role: Literal["owner", "manager", "employee"]
    team_id: str


class Command(DTO):
    text: str = Field(min_length=3, max_length=4000)
    team_id: Literal["procurement", "operations"] | None = None
    due_at: AwareDatetime | None = None
    assignee_id: str | None = Field(default=None, min_length=1, max_length=100)


class ProposedTask(DTO):
    title: str = Field(min_length=3, max_length=200)
    team_id: Literal["procurement", "operations"]
    due_at: AwareDatetime
    acceptance_criteria: str = Field(min_length=3, max_length=1200)
    assignee_id: str | None = Field(default=None, min_length=1, max_length=100)


class TaskPlan(DTO):
    source_ref: str = Field(max_length=100)
    proposed_tasks: list[ProposedTask] = Field(default_factory=list, max_length=8)
    missing_fields: list[str] = Field(default_factory=list, max_length=5)
    proposed_messages: list[str] = Field(default_factory=list, max_length=3)
    warnings: list[str] = Field(default_factory=list, max_length=8)


class Decision(DTO):
    decision: Literal["approve", "reject"]
    version: int = Field(ge=1)
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class Clarification(DTO):
    version: int = Field(ge=1)
    team_id: Literal["procurement", "operations"]
    due_at: AwareDatetime

    assignee_id: str | None = Field(default=None, min_length=1, max_length=100)


class TaskUpdate(DTO):
    status: Literal["todo", "in_progress", "blocked", "done"]
    result: str = Field(default="", max_length=2000)


class Query(DTO):
    query: str = Field(min_length=2, max_length=1000)


class DocumentACL(DTO):
    roles: list[Literal["owner", "manager", "employee"]] = Field(min_length=1, max_length=3)
    revoked: bool = False


class Login(DTO):
    token: str = Field(min_length=20, max_length=256)


class EvidenceRef(DTO):
    source_id: str
    version: int
    content_hash: str
    fragment: str
    observed_at: str
    status: str
    url: str
    score: float


class GroundedAnswer(DTO):
    answer: str = Field(max_length=4000)
    source_ids: list[str] = Field(default_factory=list, max_length=5)
    insufficient_evidence: bool = False


class MetricResult(DTO):
    metric_id: str
    name: str
    value: str | None
    unit: str
    currency: str | None
    formula_id: str
    formula_version: int = 1
    formula: str
    input_refs: list[dict[str, str | int]]
    as_of: str
    last_sync_at: str
    completeness: Literal["complete", "partial", "unknown"]
    freshness: Literal["fresh", "stale", "unknown"]
    kind: Literal["observed", "calculated", "forecast"]
    warnings: list[str]
    synthetic: bool = True


class CapabilityStatus(DTO):
    module: str
    implementation: Literal["planned", "partial", "implemented"]
    validation: Literal["not_run", "unit", "integration", "local_llm", "on_device"]
    mode: str
    checked_at: datetime | None = None
    test_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
