from typing import Literal

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    document_id: str
    page_count: int


class SampleRequest(BaseModel):
    name: str


class EvaluateRequest(BaseModel):
    questions: list[str]
    choices: list[str] = []  # set => classify each page into these; empty => extract text chunks
    api_key: str = ''
    model: Literal['jev', 'atom'] = 'jev'
    page_limit: int | None = Field(default=None, ge=1, le=200, strict=True)
