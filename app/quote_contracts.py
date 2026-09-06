"""Bounded quote inputs; monetary outputs are always calculated by application code."""

from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from app.contracts import DTO

SKU = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class QuoteLine(DTO):
    sku: SKU
    quantity: Decimal = Field(gt=0, le=1000000, max_digits=15, decimal_places=3)
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=2)


class QuoteTask(DTO):
    title: str = Field(min_length=3, max_length=200)
    team_id: str = Field(pattern="^(procurement|operations)$")
    assignee_id: str = Field(min_length=1, max_length=100)
    due_at: AwareDatetime
    acceptance_criteria: str = Field(min_length=3, max_length=1200)


class QuoteDraft(DTO):
    catalog_version_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    customer: str = Field(default="", max_length=300)
    accompanying_text: str = Field(default="", max_length=4000)
    request_text: str = Field(default="", max_length=8000)
    source_document_id: str | None = Field(default=None, max_length=100)
    source_document_version: int | None = Field(default=None, ge=1)
    lines: list[QuoteLine] = Field(min_length=1, max_length=100)
    task: QuoteTask | None = None

    @field_validator("title", "customer", "accompanying_text", "request_text")
    @classmethod
    def exportable_text(cls, value):
        if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
            raise ValueError("text contains unsupported control characters")
        return value

    @model_validator(mode="after")
    def source_pair(self):
        if bool(self.source_document_id) != bool(self.source_document_version):
            raise ValueError("source document id and version must be supplied together")
        if len({line.sku for line in self.lines}) != len(self.lines):
            raise ValueError("duplicate quote SKU")
        return self


class QuoteRevision(QuoteDraft):
    version: int = Field(ge=1)


class QuoteProposal(DTO):
    version: int = Field(ge=1)


class QuoteSuggestionRequest(DTO):
    catalog_version_id: str = Field(min_length=1, max_length=100)
    request_text: str = Field(default="", max_length=8000)
    source_document_id: str | None = Field(default=None, max_length=100)
    source_document_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def source_or_text(self):
        if bool(self.source_document_id) != bool(self.source_document_version):
            raise ValueError("source document id and version must be supplied together")
        if not self.request_text.strip() and not self.source_document_id:
            raise ValueError("request text or source document is required")
        return self


class QuoteSuggestion(DTO):
    lines: list[QuoteLine] = Field(default_factory=list, max_length=100)
    unresolved: list[Annotated[str, StringConstraints(max_length=500)]] = Field(
        default_factory=list, max_length=100
    )
    accompanying_text: str = Field(default="", max_length=4000)
