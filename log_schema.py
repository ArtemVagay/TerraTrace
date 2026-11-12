"""Pydantic описывает, какие данные получает и возвращает API."""

from pydantic import BaseModel, Field


class TextLogRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5 * 1024 * 1024)


class Finding(BaseModel):
    rule_id: str
    title: str
    category: str
    explanation: str
    steps: list[str]
    known_pattern: bool


class EventGroup(BaseModel):
    id: str
    level: str
    source: str
    message: str
    exception_type: str | None
    count: int
    first_line: int
    last_line: int
    first_time: str | None
    last_time: str | None
    related_mods: list[str]
    excerpt: str
    finding: Finding


class Summary(BaseModel):
    total_lines: int
    total_events: int
    errors: int
    warnings: int
    unique_errors: int
    problem_groups: int


class AnalysisReport(BaseModel):
    id: str
    filename: str
    analyzed_at: str
    tml_version: str | None
    mods: list[str]
    summary: Summary
    groups: list[EventGroup]
    notices: list[str]
    redactions: int
    omitted_groups: int
