from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_OFFICE_", env_file=".env", extra="forbid")
    mode: Literal["demo", "local_ollama", "compatible_http"] = "demo"
    data_mode: Literal["demo", "pilot"] = "demo"
    data_dir: Path = Path(".runtime/data")
    org_timezone: str = "Europe/Moscow"
    qdrant_url: str = "http://127.0.0.1:6333"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    ollama_embedding_model: str = "mxbai-embed-large"
    agent_runtime_url: str = ""
    inference_base_url: str = ""
    inference_model: str = ""
    compatible_contract_verified: bool = False
    embedding_provider: Literal["demo", "ollama"] = "demo"
    allowed_hosts: list[str] = [
        "127.0.0.1",
        "localhost",
        "::1",
        "qdrant",
        "host.docker.internal",
        "agent-runtime",
        "model-gateway",
    ]
    cookie_secure: bool = False
    session_seconds: int = Field(default=28800, ge=60, le=86400)
    credential_days: int = Field(default=30, ge=1, le=365)
    max_upload_bytes: int = Field(default=131072, ge=1024, le=1048576)
    max_binary_upload_bytes: int = Field(default=10485760, ge=131072, le=10485760)
    max_queue: int = Field(default=100, ge=1, le=1000)
    provider_timeout: float = Field(default=45, ge=1, le=60)
    lease_seconds: int = Field(default=300, ge=240, le=600)

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir.resolve() / 'office.db'}"

    def check_url(self, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme not in {"http", "https"}
            or url.hostname not in self.allowed_hosts
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("Endpoint must use an administrator-allowed host, without credentials")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        ZoneInfo(self.org_timezone)
        self.check_url(self.qdrant_url)
        self.check_url(self.ollama_base_url)
        if self.mode == "demo" and self.embedding_provider != "demo":
            raise ValueError("Demo must not call model services")
        if self.mode != "demo" and self.embedding_provider == "demo":
            raise ValueError("Real generation requires explicitly selected real embeddings")
        if self.agent_runtime_url:
            self.check_url(self.agent_runtime_url)
        if self.mode == "compatible_http" and self.inference_base_url:
            self.check_url(self.inference_base_url)
        return self
