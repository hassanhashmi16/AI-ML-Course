"""CodeTrail's settings: one validated boundary between the environment and app.

Project 3 read os.getenv values directly. Pydantic Settings now loads .env,
converts types, and rejects invalid values. Importing this file makes no network
calls or directories; offline development does not require provider credentials.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor configuration to the project, even when Python runs from another cwd.
BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Environment variables override the project .env file and these defaults."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",  # Never accidentally read another project's .env.
        env_file_encoding="utf-8",
        extra="forbid",  # Catch misspelled setting names inside our .env file.
        hide_input_in_errors=True,  # Validation errors must not echo secret input.
    )

    # Empty secrets allow offline checks; live integrations validate their needs.
    # SecretStr masks values in representations; repr=False omits these fields.
    github_token: SecretStr = Field(default=SecretStr(""), repr=False)
    gemini_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    groq_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    cohere_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    langsmith_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    langsmith_tracing: bool = False
    langsmith_project: str = "codetrail"

    # Explicit defaults checked against provider docs on 16 October 2026.
    # These are configuration choices, not a claim of tested account access.
    gen_model: str = Field(default="gemini-3.7-flash", min_length=1)
    # Dense embeddings: local FastEmbed by default (no API key, no quota --
    # the model is fixed-dimension). Switch to "google" to use GEMINI_API_KEY
    # with embed_model/embed_dim instead.
    embed_provider: Literal["fastembed", "google"] = "fastembed"
    fastembed_embed_model: str = Field(default="BAAI/bge-small-en-v1.5", min_length=1)
    embed_model: str = Field(default="gemini-embedding-001", min_length=1)
    embed_dim: int = Field(default=768, gt=0)
    sparse_model: str = Field(default="Qdrant/bm25", min_length=1)
    rerank_model: str = Field(default="rerank-v4.0-fast", min_length=1)

    # Positive limits prevent accidental zero-size results or unbounded work.
    retrieve_k: int = Field(default=20, gt=0)
    rerank_k: int = Field(default=5, gt=0)
    max_files: int = Field(default=40, gt=0)
    max_commits: int = Field(default=60, gt=0)
    max_discussions: int = Field(default=10, gt=0)
    max_comments: int = Field(default=20, gt=0)
    max_tool_calls: int = Field(default=12, gt=0)
    max_retrieval_rounds: int = Field(default=2, ge=0)  # Zero disables refinement.
    max_answer_revisions: int = Field(default=1, ge=0)
    max_run_seconds: float = Field(default=120, gt=0)
    token_budget: int = Field(default=40000, gt=0)
    max_output_tokens: int = Field(default=2048, gt=0)
    github_timeout_seconds: float = Field(default=20, gt=0)

    # No runtime directories are created merely by importing configuration.
    data_dir: Path = BASE_DIR / "data"
    reports_dir: Path = BASE_DIR / "reports"

    @model_validator(mode="after")
    def validate_pipeline(self) -> "Settings":
        """Check relationships between fields, then normalize relative paths."""
        if self.rerank_k > self.retrieve_k:
            raise ValueError("RERANK_K must not exceed RETRIEVE_K")
        if self.max_output_tokens > self.token_budget:
            raise ValueError("MAX_OUTPUT_TOKENS must not exceed TOKEN_BUDGET")
        # Joining an absolute override keeps that absolute path; a relative one
        # is anchored to CodeTrail, so changing the shell's cwd changes nothing.
        self.data_dir = (BASE_DIR / self.data_dir).resolve()
        self.reports_dir = (BASE_DIR / self.reports_dir).resolve()
        return self


# Other modules import this instance instead of reading environment variables.
settings = Settings()
