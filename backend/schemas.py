from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    document_id: str
    page_count: int


class SampleRequest(BaseModel):
    name: str


class EvaluateRequest(BaseModel):
    questions: list[str]
    api_key: str = ''
    page_limit: int | None = Field(default=None, ge=1, le=200, strict=True)
