"""記事リストの重複除去・時間窓・ソート（ドメイン寄りの加工）。"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from slack_news.domain.article import Article
from slack_news.domain.source_labels import source_display_name

logger = logging.getLogger(__name__)


def _normalize_title(title: str) -> str:
    """タイトルを正規化して比較用にする。"""
    normalized = re.sub(r"[\s\u3000\u00A0\u2000-\u200B\u2028\u2029\uFEFF]", "", title.lower())
    normalized = re.sub(r"[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]", "", normalized)
    return normalized


def _calculate_title_similarity(title1: str, title2: str) -> float:
    """2つのタイトルの類似度を計算する（0.0-1.0）。"""
    norm1 = _normalize_title(title1)
    norm2 = _normalize_title(title2)

    if not norm1 or not norm2:
        return 0.0

    if norm1 == norm2:
        return 1.0

    shorter = min(len(norm1), len(norm2))
    longer = max(len(norm1), len(norm2))

    if shorter >= 10:
        if len(norm1) <= len(norm2):
            if norm1 in norm2:
                base_similarity = len(norm1) / len(norm2)
                return max(base_similarity, 0.7)
        else:
            if norm2 in norm1:
                base_similarity = len(norm2) / len(norm1)
                return max(base_similarity, 0.7)

    if shorter >= 5:
        overlap_length = min(shorter, int(shorter * 0.8))
        if len(norm1) <= len(norm2):
            if norm1[:overlap_length] == norm2[:overlap_length]:
                return 0.75
        else:
            if norm2[:overlap_length] == norm1[:overlap_length]:
                return 0.75

    common_chars = sum(1 for c in set(norm1) if c in norm2)
    total_chars = len(set(norm1) | set(norm2))

    if total_chars == 0:
        return 0.0

    jaccard_similarity = common_chars / total_chars

    shorter = min(len(norm1), len(norm2))
    longer = max(len(norm1), len(norm2))
    length_similarity = shorter / longer if longer > 0 else 0.0

    common_substring_score = 0.0
    for i in range(len(norm1) - 2):
        substring = norm1[i : i + 3]
        if substring in norm2:
            common_substring_score = 0.2
            break

    similarity = (jaccard_similarity * 0.5) + (length_similarity * 0.3) + common_substring_score

    return min(similarity, 1.0)


def _get_source_priority(link: str) -> int:
    """ソースの優先度を返す（数値が小さいほど優先度が高い）。"""
    if "prtimes.jp" in link:
        return 1
    if "medicaltech-news.com" in link:
        return 2
    if "ht-watch.com" in link:
        return 3
    if "news.google.com" in link:
        return 5
    return 5


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    """URLとタイトルの重複を除去する（PR TIMESを最優先）。"""
    seen_urls: set[str] = set()
    url_deduplicated: list[Article] = []
    for article in articles:
        if not article.link:
            continue
        normalized_url = article.link.rstrip("/").split("?")[0]
        if normalized_url not in seen_urls:
            seen_urls.add(normalized_url)
            url_deduplicated.append(article)

    SIMILARITY_THRESHOLD = 0.7

    deduplicated: list[Article] = []
    title_cache: dict[str, str] = {}

    for article in url_deduplicated:
        if not article.title:
            continue

        normalized_title = _normalize_title(article.title)
        title_cache[article.title] = normalized_title

        is_duplicate = False
        for existing_article in deduplicated:
            if not existing_article.title:
                continue

            existing_normalized = title_cache.get(
                existing_article.title, _normalize_title(existing_article.title)
            )
            if normalized_title == existing_normalized:
                similarity = 1.0
            else:
                similarity = _calculate_title_similarity(article.title, existing_article.title)

            if similarity >= SIMILARITY_THRESHOLD:
                existing_priority = _get_source_priority(existing_article.link)
                new_priority = _get_source_priority(article.link)

                if new_priority < existing_priority:
                    deduplicated.remove(existing_article)
                    deduplicated.append(article)
                    logger.info(
                        "Replaced duplicate article (similarity: %.2f, kept from %s): %s",
                        similarity,
                        source_display_name(article.link),
                        article.title[:50],
                    )
                else:
                    logger.info(
                        "Skipped duplicate article (similarity: %.2f, kept from %s): %s",
                        similarity,
                        source_display_name(existing_article.link),
                        article.title[:50],
                    )
                is_duplicate = True
                break

        if not is_duplicate:
            deduplicated.append(article)

    removed_count = len(articles) - len(deduplicated)
    if removed_count > 0:
        logger.info("Removed %d duplicate articles (by URL and title)", removed_count)
    return deduplicated


def filter_by_time_range(
    articles: list[Article], now: datetime, hours_before: int = 6
) -> list[Article]:
    """指定された時間範囲内に公開された記事のみをフィルタリングする。"""
    if hours_before <= 0:
        return articles

    time_start = now - timedelta(hours=hours_before)

    filtered: list[Article] = []
    skipped_no_date = 0
    skipped_old = 0

    for article in articles:
        if article.is_event:
            filtered.append(article)
            continue

        if article.published_at is None:
            skipped_no_date += 1
            logger.debug("Skipping article with no published_at: %s", article.title[:50])
            continue

        article_time = article.published_at
        if article_time.tzinfo is None:
            article_time = article_time.replace(tzinfo=timezone(timedelta(hours=9)))
        else:
            article_time = article_time.astimezone(timezone(timedelta(hours=9)))

        if time_start <= article_time <= now:
            filtered.append(article)
        else:
            skipped_old += 1
            logger.debug(
                "Skipping article outside time range (published: %s, range: %s - %s): %s",
                article_time.strftime("%Y-%m-%d %H:%M"),
                time_start.strftime("%Y-%m-%d %H:%M"),
                now.strftime("%Y-%m-%d %H:%M"),
                article.title[:50],
            )

    if skipped_no_date > 0:
        logger.info("Skipped %d articles with no published_at", skipped_no_date)
    if skipped_old > 0:
        logger.info("Skipped %d articles outside time range (%d hours before)", skipped_old, hours_before)

    return filtered


def sort_articles(articles: list[Article]) -> list[Article]:
    """電子カルテを含む記事を優先し、その後公開日時でソート。"""
    PRIORITY_KEYWORD = "電子カルテ"

    def sort_key(article: Article) -> tuple[int, float]:
        text = f"{article.title} {article.summary or ''}".lower()
        has_priority = PRIORITY_KEYWORD.lower() in text
        priority = 0 if has_priority else 1
        timestamp = article.published_at.timestamp() if article.published_at else float("-inf")
        return (priority, -timestamp)

    return sorted(articles, key=sort_key)
