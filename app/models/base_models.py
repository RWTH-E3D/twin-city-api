from pydantic import BaseModel, field_validator
from typing import List, Optional
from app.core.config import settings


class Link(BaseModel):
    href: str
    rel: Optional[str] = None
    type: Optional[str] = None
    title: Optional[str] = None

    @field_validator("href")
    @classmethod
    def prepend_basepath(cls, v: str) -> str:
        if not v.startswith(("http://", "https://", settings.BASE_PATH)):
            return f"{settings.BASE_PATH}{v if v.startswith('/') else f'/{v}'}"
        return v


class LandingPage(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    links: List[Link]


class ConformanceClasses(BaseModel):
    conformsTo: List[str]
