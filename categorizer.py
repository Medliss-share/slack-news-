"""
記事をカテゴリに分類する。

4つのカテゴリ:
- healthtech: ヘルステック特化の IT 技術動向（FHIR / SaMD / 電子カルテ / 医療AI 等）
- general_tech: 一般IT 技術動向（AIエージェント / セキュリティ / システム開発 等、医療×IT フィルタをバイパス）
- competitor: 競合動向（資金調達・提携・プロダクト動向等）
- conference: カンファレンス・イベント

1つの記事は複数カテゴリに同時に該当しうる。

後方互換:
- `tech` は `healthtech` のエイリアスとして扱う（--category tech でも動く）。
"""
from __future__ import annotations

import logging
from typing import Iterable

from fetcher import Article

logger = logging.getLogger(__name__)

CATEGORY_HEALTHTECH = "healthtech"
CATEGORY_GENERAL_TECH = "general_tech"
CATEGORY_COMPETITOR = "competitor"
CATEGORY_CONFERENCE = "conference"

# 後方互換: 旧 "tech" を healthtech のエイリアスとして扱う
CATEGORY_TECH = CATEGORY_HEALTHTECH

ALL_CATEGORIES: tuple[str, ...] = (
    CATEGORY_HEALTHTECH,
    CATEGORY_GENERAL_TECH,
    CATEGORY_COMPETITOR,
    CATEGORY_CONFERENCE,
)

# CLI から渡ってきた旧カテゴリ名を新カテゴリ名に正規化
CATEGORY_ALIASES: dict[str, str] = {
    "tech": CATEGORY_HEALTHTECH,
}


def normalize_category(name: str) -> str:
    """エイリアスを正規のカテゴリ名に変換する。"""
    return CATEGORY_ALIASES.get(name.lower(), name.lower())


def _match_any(text: str, keywords: Iterable[str]) -> bool:
    lowered_text = text.lower()
    for kw in keywords:
        if not kw:
            continue
        if kw.lower() in lowered_text:
            return True
    return False


def _source_based_categories(link: str | None) -> list[str]:
    """URL ドメインから、そのソースで自動付与するカテゴリを返す。

    connpass のイベントはキーワードに関わらず conference カテゴリを付与する
    （connpass fetcher 側で既に categories=['conference'] を付与しているが、
    他の経路で流入した場合の保険として残す）。
    """
    if not link:
        return []
    link_lower = link.lower()
    if "connpass.com" in link_lower:
        return [CATEGORY_CONFERENCE]
    return []


def categorize_article(
    article: Article,
    healthtech_keywords: Iterable[str],
    competitor_keywords: Iterable[str],
    conference_keywords: Iterable[str],
    general_tech_keywords: Iterable[str],
) -> list[str]:
    """単一記事のカテゴリを返す。複数該当しうる。

    分岐:
    - `is_event=True` (connpass) → `conference`
    - `is_general_tech=True` (一般ITソース) → `general_tech` (+ conference があれば併記)
    - それ以外 (医療×IT 通過記事) → healthtech / competitor / conference のタグ付け
    """
    existing = list(article.categories or [])

    # connpass イベントは既存タグを尊重（fetch_connpass で厳密にタグ付与されているため）
    if article.is_event and existing:
        return existing

    text = f"{article.title} {article.summary or ''}"

    # 一般IT ソース由来の記事 → general_tech 固定（+ conference キーワードにも該当すれば追加）
    if article.is_general_tech:
        cats: list[str] = [CATEGORY_GENERAL_TECH]
        if _match_any(text, conference_keywords):
            cats.append(CATEGORY_CONFERENCE)
        for c in existing:
            if c not in cats:
                cats.append(c)
        return cats

    # 通常記事（医療×IT 通過記事 or ホワイトリスト/優先クエリ由来）
    categories: list[str] = list(_source_based_categories(article.link))
    # 事前付与されたカテゴリ（ホワイトリスト経由の healthtech 等）を保持
    for c in existing:
        if c not in categories:
            categories.append(c)

    if _match_any(text, healthtech_keywords) and CATEGORY_HEALTHTECH not in categories:
        categories.append(CATEGORY_HEALTHTECH)
    if _match_any(text, competitor_keywords) and CATEGORY_COMPETITOR not in categories:
        categories.append(CATEGORY_COMPETITOR)
    if _match_any(text, conference_keywords) and CATEGORY_CONFERENCE not in categories:
        categories.append(CATEGORY_CONFERENCE)

    return categories


def categorize_articles(
    articles: Iterable[Article],
    healthtech_keywords: Iterable[str],
    competitor_keywords: Iterable[str],
    conference_keywords: Iterable[str],
    general_tech_keywords: Iterable[str],
) -> list[Article]:
    """記事リスト全件にカテゴリタグを付与する。Article.categories を上書きする。"""
    ht_kw = list(healthtech_keywords)
    comp_kw = list(competitor_keywords)
    conf_kw = list(conference_keywords)
    gt_kw = list(general_tech_keywords)

    result: list[Article] = []
    ht_n = gt_n = comp_n = conf_n = none_n = 0

    for article in articles:
        cats = categorize_article(article, ht_kw, comp_kw, conf_kw, gt_kw)
        article.categories = cats
        if CATEGORY_HEALTHTECH in cats:
            ht_n += 1
        if CATEGORY_GENERAL_TECH in cats:
            gt_n += 1
        if CATEGORY_COMPETITOR in cats:
            comp_n += 1
        if CATEGORY_CONFERENCE in cats:
            conf_n += 1
        if not cats:
            none_n += 1
        result.append(article)

    logger.info(
        "Categorized articles: healthtech=%d general_tech=%d competitor=%d conference=%d uncategorized=%d (total=%d)",
        ht_n,
        gt_n,
        comp_n,
        conf_n,
        none_n,
        len(result),
    )
    return result


def filter_by_category(
    articles: Iterable[Article],
    category: str,
) -> list[Article]:
    """指定カテゴリに該当する記事のみ返す。category='all' は全件通す。"""
    if category == "all":
        return list(articles)
    category = normalize_category(category)
    return [a for a in articles if a.categories and category in a.categories]


CATEGORY_LABELS: dict[str, str] = {
    CATEGORY_HEALTHTECH: "ヘルステック技術動向",
    CATEGORY_GENERAL_TECH: "一般IT技術動向",
    CATEGORY_COMPETITOR: "競合動向",
    CATEGORY_CONFERENCE: "カンファレンス・イベント",
}

CATEGORY_EMOJIS: dict[str, str] = {
    CATEGORY_HEALTHTECH: "🏥",
    CATEGORY_GENERAL_TECH: "🧠",
    CATEGORY_COMPETITOR: "⚔️",
    CATEGORY_CONFERENCE: "📅",
}

CATEGORY_BADGES: dict[str, str] = {
    CATEGORY_HEALTHTECH: "[ヘルステック]",
    CATEGORY_GENERAL_TECH: "[一般IT]",
    CATEGORY_COMPETITOR: "[競合]",
    CATEGORY_CONFERENCE: "[イベント]",
}
