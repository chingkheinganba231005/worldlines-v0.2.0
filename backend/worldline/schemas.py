"""Versioned metadata contracts; dataset fields stay explicit and extensible."""
from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Snapshot(BaseModel):
    model_config = ConfigDict(extra='allow', strict=True)
    mode: str
    history: list[dict[str, Any]] = Field(min_length=1)
    references: Any = None
    methodology: Any = None

    @field_validator('mode')
    @classmethod
    def valid_mode(cls, value):
        if value not in {'demo', 'synthetic', 'historical', 'historical_sample', 'live', 'replay', 'synthetic_demo'}:
            raise ValueError('unknown snapshot mode')
        return value

    @field_validator('history')
    @classmethod
    def dated_history(cls, values):
        dates = []
        for value in values:
            stamp = value.get('date')
            if not isinstance(stamp, str):
                raise ValueError('each history row requires a date')
            parsed = date.fromisoformat(stamp)
            if parsed.isoformat() != stamp:
                raise ValueError('date must be YYYY-MM-DD')
            dates.append(stamp)
        if dates != sorted(set(dates)):
            raise ValueError('history dates must be unique and ascending')
        return values

class ProviderRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str
    raw_source_id: str
    source_provider: Literal['gdelt2'] = 'gdelt2'
    event_time_utc: str
    available_at_utc: str
    observed_at_utc: str
    ingested_at_utc: str
    source_url: str | None
    source_citation: str
    publisher: str | None
    label: str
    label_kind: Literal['generated_actor_action_label'] = 'generated_actor_action_label'
    domain: Literal['sociopolitical'] = 'sociopolitical'
    language: None = None
    verification_status: Literal['provisional'] = 'provisional'
    independent_source_count: None = None
    source_diversity_count: int = Field(ge=0)
    is_synthetic: bool = False
    parser_version: str
    source_checksum: str
    metadata_rights: str
    credibility_flags: list[str]
    raw_metadata: dict[str, str]
