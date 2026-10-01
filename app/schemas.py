from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .config import PLATFORMS


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=5, max_length=6000)
    instruction: str = Field(default='', max_length=3000)
    asset_ids: list[str] = Field(min_length=1, max_length=4)
    platforms: list[str] = Field(min_length=1, max_length=3)
    mode: Literal['ark', 'mock'] = 'ark'

    @field_validator('platforms')
    @classmethod
    def valid_platforms(cls, values):
        if len(set(values)) != len(values) or any(p not in PLATFORMS for p in values):
            raise ValueError('请选择不重复的有效平台')
        return values

    @field_validator('name', 'description')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('内容不能为空')
        return value.strip()

class Review(BaseModel):
    interrupt_id: str
    version: int = Field(ge=1)
    action: Literal['approve', 'revise', 'retopic']
    topic_id: str | None = None
    article: str | None = Field(default=None, max_length=16000)
    feedback: str = Field(default='', max_length=3000)

class Topic(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=100)
    angle: str = Field(min_length=1, max_length=500)
    outline: str = Field(min_length=1, max_length=1000)

class Topics(BaseModel):
    topics: list[Topic] = Field(min_length=3, max_length=3)

class Summary(BaseModel):
    summary: str = Field(min_length=1, max_length=1500)
    image_prompt: str = Field(min_length=1, max_length=3000)
    caption: str = Field(min_length=1, max_length=120)
