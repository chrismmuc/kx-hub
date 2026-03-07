"""Pydantic models for the newsletter pipeline."""

from pydantic import BaseModel


class CuratedSource(BaseModel):
    title: str
    url: str
    source_type: str  # article, book, podcast
    summary: str
    reason: str = ""
    author: str = ""


class HotNewsItem(BaseModel):
    title: str
    url: str
    summary: str


class CurationResult(BaseModel):
    filtered_sources: list[CuratedSource]
    hot_news: list[HotNewsItem]
    curator_notes: str = ""


class NewsletterDraft(BaseModel):
    html: str
    plain_text: str
    subject: str
    curated_sources: list[CuratedSource]
    hot_news: list[HotNewsItem]
    dry_run: bool = True
    created_at: str
    period_start: str
    period_end: str
    gcs_url: str = ""
    reader_url: str = ""
    image_url: str = ""
