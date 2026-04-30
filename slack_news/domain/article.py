"""ニュース記事エンティティ（ドメイン）。外部I/Oを持たない。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Article:
    title: str
    link: str
    published: str | None = None
    summary: str | None = None
    published_at: datetime | None = None
    matched_keywords: list[str] | None = None
    categories: list[str] | None = None
    is_event: bool = False
    event_start_at: datetime | None = None
    event_location: str | None = None
    is_general_tech: bool = False
    is_healthtech_priority: bool = False
