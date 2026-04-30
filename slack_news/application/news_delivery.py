"""ニュース取得から Slack 投稿までのユースケース（Application 層のオーケストレーション）。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from categorizer import (
    ALL_CATEGORIES,
    categorize_articles,
    normalize_category,
)
from extrasources import (
    fetch_connpass,
    fetch_general_tech_google_news,
    fetch_general_tech_rss,
    fetch_google_news,
    fetch_healthtech_priority_google_news,
    fetch_htwatch,
    fetch_medicaltech,
)
from fetcher import fetch_all_feeds
from filter import filter_articles

from slack_news.application.article_pipeline import (
    deduplicate_articles,
    filter_by_time_range,
    sort_articles,
)
from slack_news.domain.article import Article
from slack_news.interfaces.ports import SentUrlRepository, SlackNotifier
from slack_news.presentation.slack_messages import build_message

logger = logging.getLogger(__name__)


def _count_keyword_hits(articles: list[Article]) -> tuple[int, int, int]:
    med_kw = [kw.lower() for kw in config.MEDICAL_KEYWORDS]
    it_kw = [kw.lower() for kw in config.IT_KEYWORDS]
    med_count = it_count = both_count = 0
    for a in articles:
        text = f"{a.title} {a.summary or ''}".lower()
        has_med = any(kw in text for kw in med_kw)
        has_it = any(kw in text for kw in it_kw)
        med_count += has_med
        it_count += has_it
        both_count += has_med and has_it
    return med_count, it_count, both_count


def _resolve_webhook_url(webhook: str) -> str | None:
    webhook = (webhook or "default").lower()
    if webhook == "a":
        return config.SLACK_WEBHOOK_URL_A or config.SLACK_WEBHOOK_URL
    if webhook == "b":
        return config.SLACK_WEBHOOK_URL_B or config.SLACK_WEBHOOK_URL
    return config.SLACK_WEBHOOK_URL


def _parse_categories(category_arg: str) -> list[str]:
    if not category_arg or category_arg.lower() == "all":
        return []
    parts = [normalize_category(c.strip()) for c in category_arg.split(",") if c.strip()]
    valid = [c for c in parts if c in ALL_CATEGORIES]
    if not valid:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for c in valid:
        if c not in seen:
            ordered.append(c)
            seen.add(c)
    return ordered


class NewsDeliveryUseCase:
    """医療×ITニュースを集め、フィルタし、Slack に投稿する。"""

    def __init__(self, *, slack: SlackNotifier, sent_urls: SentUrlRepository) -> None:
        self._slack = slack
        self._sent_urls = sent_urls

    def run(
        self,
        *,
        dry_run: bool = False,
        storage_path: Path | None = None,
        max_items: int | None = None,
        manual: bool = False,
        category: str = "all",
        webhook: str = "default",
    ) -> int:
        storage_path = storage_path or config.SENT_URLS_PATH
        categories = _parse_categories(category)

        if manual:
            max_items = 5
        elif max_items is None:
            max_items = (
                config.MAX_ARTICLES_PER_CATEGORY
                if categories
                else config.MAX_ARTICLES_PER_POST
            )

        webhook_lower = (webhook or "default").lower()
        want_healthtech_sources = webhook_lower in ("default", "a")
        want_general_tech_sources = webhook_lower in ("default", "b")
        logger.info(
            "Source routing: webhook=%s -> healthtech=%s, general_tech/events=%s",
            webhook_lower,
            want_healthtech_sources,
            want_general_tech_sources,
        )

        fetched: list[Article] = []

        if want_healthtech_sources:
            feed_urls = config.RSS_FEEDS
            if feed_urls:
                logger.info("Starting fetch for %d RSS feed(s)", len(feed_urls))
                rss_articles = fetch_all_feeds(feed_urls, timeout=config.FETCH_TIMEOUT)
                if not rss_articles:
                    logger.warning("RSSフィードから記事を取得できませんでした。")
                else:
                    med_count, it_count, both_count = _count_keyword_hits(rss_articles)
                    logger.info(
                        "RSS keyword hits (before exclude): med=%d it=%d both=%d",
                        med_count,
                        it_count,
                        both_count,
                    )
                    fetched.extend(rss_articles)
            else:
                logger.info("RSS_FEEDS が空のため、RSS取得をスキップします。")

            healthtech_extra_keys = {"medicaltech", "htwatch", "googlenews", "google-news"}
            healthtech_sources = [
                s for s in config.EXTRA_SOURCES if s.lower() in healthtech_extra_keys
            ]
            if healthtech_sources:
                logger.info("Fetching healthtech web sources: %s", ", ".join(healthtech_sources))
            ht_articles: list[Article] = []
            for src in healthtech_sources:
                try:
                    if src.lower() == "medicaltech":
                        articles = fetch_medicaltech(timeout=config.FETCH_TIMEOUT)
                        ht_articles.extend(articles)
                        logger.info("Fetched %d articles from medicaltech-news", len(articles))
                    elif src.lower() == "htwatch":
                        articles = fetch_htwatch(timeout=config.FETCH_TIMEOUT)
                        ht_articles.extend(articles)
                        logger.info("Fetched %d articles from ht-watch", len(articles))
                    elif src.lower() in ("googlenews", "google-news"):
                        articles = fetch_google_news(timeout=config.FETCH_TIMEOUT)
                        ht_articles.extend(articles)
                        logger.info("Fetched %d articles from Google News", len(articles))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to fetch from %s: %s", src, exc)
            if ht_articles:
                med_c, it_c, both_c = _count_keyword_hits(ht_articles)
                logger.info(
                    "Healthtech scraping keyword hits (before exclude): med=%d it=%d both=%d",
                    med_c,
                    it_c,
                    both_c,
                )
                fetched.extend(ht_articles)

            try:
                ht_priority = fetch_healthtech_priority_google_news(
                    config.HEALTHTECH_PRIORITY_GOOGLE_NEWS_QUERIES,
                    timeout=config.FETCH_TIMEOUT,
                )
                fetched.extend(ht_priority)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to fetch healthtech-priority Google News: %s", exc)

        if want_general_tech_sources:
            if config.GENERAL_TECH_PRTIMES_RSS_URLS:
                try:
                    gt_pr = fetch_general_tech_rss(
                        config.GENERAL_TECH_PRTIMES_RSS_URLS,
                        timeout=config.FETCH_TIMEOUT,
                    )
                    fetched.extend(gt_pr)
                    logger.info(
                        "Fetched %d articles from general-tech PR TIMES (%d feed(s))",
                        len(gt_pr),
                        len(config.GENERAL_TECH_PRTIMES_RSS_URLS),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to fetch general-tech PR TIMES: %s", exc)

            if config.GENERAL_TECH_GOOGLE_NEWS_QUERIES:
                try:
                    gt_gn = fetch_general_tech_google_news(
                        config.GENERAL_TECH_GOOGLE_NEWS_QUERIES,
                        timeout=config.FETCH_TIMEOUT,
                    )
                    fetched.extend(gt_gn)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to fetch general-tech Google News: %s", exc)

            if config.GENERAL_TECH_RSS_URLS:
                try:
                    gt_rss = fetch_general_tech_rss(
                        config.GENERAL_TECH_RSS_URLS,
                        timeout=config.FETCH_TIMEOUT,
                    )
                    fetched.extend(gt_rss)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to fetch general-tech RSS: %s", exc)

            if "connpass" in {s.lower() for s in config.EXTRA_SOURCES}:
                try:
                    cn_articles = fetch_connpass(
                        timeout=config.FETCH_TIMEOUT,
                        allowed_locations=config.EVENT_LOCATIONS,
                        lookahead_days=config.EVENT_LOOKAHEAD_DAYS,
                    )
                    fetched.extend(cn_articles)
                    logger.info("Fetched %d events from connpass (after filter)", len(cn_articles))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to fetch connpass: %s", exc)

        if not fetched:
            logger.warning("すべてのソースから記事を取得できませんでした。")
        else:
            logger.info("Total fetched articles: %d", len(fetched))

        medical_dx_required = webhook_lower == "a"
        medical_dx_keywords_arg = (
            config.MEDICAL_DX_KEYWORDS if medical_dx_required else None
        )
        company_allowlist_arg = (
            config.HEALTHTECH_COMPANY_ALLOWLIST if want_healthtech_sources else None
        )
        if medical_dx_required:
            logger.info(
                "Channel A: enabling medical-DX required gate (%d keywords) + company allowlist (%d companies)",
                len(config.MEDICAL_DX_KEYWORDS),
                len(config.HEALTHTECH_COMPANY_ALLOWLIST),
            )

        filtered = filter_articles(
            fetched,
            medical_keywords=config.MEDICAL_KEYWORDS,
            it_keywords=config.IT_KEYWORDS,
            exclude_keywords=config.EXCLUDE_KEYWORDS,
            exclude_domains=config.EXCLUDE_DOMAINS,
            general_tech_keywords=config.GENERAL_TECH_KEYWORDS,
            medical_dx_keywords=medical_dx_keywords_arg,
            company_allowlist=company_allowlist_arg,
        )
        logger.info("After keyword filtering: %d articles", len(filtered))

        filtered = categorize_articles(
            filtered,
            healthtech_keywords=config.HEALTHTECH_TECH_KEYWORDS,
            competitor_keywords=config.COMPETITOR_ACTION_KEYWORDS,
            conference_keywords=config.CONFERENCE_KEYWORDS,
            general_tech_keywords=config.GENERAL_TECH_KEYWORDS,
        )

        if categories:
            before = len(filtered)
            filtered = [
                a
                for a in filtered
                if a.categories and any(c in a.categories for c in categories)
            ]
            logger.info(
                "Category filter (%s): %d articles (from %d)",
                ",".join(categories),
                len(filtered),
                before,
            )

        now = datetime.now(timezone(timedelta(hours=9)))
        logger.info(
            "Applying time window: last %d hour(s) (now: %s)",
            config.TIME_RANGE_HOURS,
            now.strftime("%Y-%m-%d %H:%M:%S JST"),
        )
        filtered = filter_by_time_range(filtered, now, hours_before=config.TIME_RANGE_HOURS)
        logger.info("After time range filtering: %d articles", len(filtered))

        filtered = deduplicate_articles(filtered)
        logger.info("After deduplication: %d articles", len(filtered))
        filtered = sort_articles(filtered)

        if manual:
            logger.info(
                "Manual mode: skipping sent URL check, excluding Google News, limiting to %d articles",
                max_items,
            )
            filtered_without_google = [
                a for a in filtered if a.link and "news.google.com" not in a.link
            ]
            logger.info(
                "Excluded Google News: %d articles remaining (from %d total)",
                len(filtered_without_google),
                len(filtered),
            )
            new_articles = filtered_without_google
            if len(new_articles) > max_items:
                new_articles = new_articles[:max_items]
        else:
            sent_map = self._sent_urls.load(storage_path)
            logger.info("Loaded %d sent URLs from storage", len(sent_map))

            new_articles = []
            skipped_count = 0
            for article in filtered:
                if not article.link:
                    continue
                normalized_url = article.link.rstrip("/").split("?")[0]
                if article.link in sent_map or normalized_url in sent_map:
                    skipped_count += 1
                    logger.debug("Skipping already sent article: %s", article.title[:50])
                    continue
                new_articles.append(article)

            if skipped_count > 0:
                logger.info("Skipped %d already sent articles (from previous time slots)", skipped_count)

            if len(new_articles) > max_items:
                new_articles = new_articles[:max_items]

        message = build_message(new_articles, now, categories=categories, webhook=webhook_lower)

        logger.info("New articles: %d (after dedupe and limit)", len(new_articles))

        webhook_url = _resolve_webhook_url(webhook)
        webhook_label = webhook.lower() if webhook else "default"

        if dry_run:
            logger.info(
                "Dry-run mode: message not sent to Slack (intended webhook: %s)",
                webhook_label,
            )
            print(message)
            return 0

        if not webhook_url:
            logger.error("Slack Webhook URL が未設定です (webhook=%s)", webhook_label)
            return 1

        success = self._slack.post(webhook_url, message, timeout=config.FETCH_TIMEOUT)
        if not success:
            logger.error("Slack 送信に失敗しました (webhook=%s)。", webhook_label)
            return 1
        logger.info("Posted to Slack (webhook=%s)", webhook_label)

        if new_articles:
            sent_map = self._sent_urls.load(storage_path)
            timestamp = now.isoformat()
            for article in new_articles:
                normalized_url = article.link.rstrip("/").split("?")[0]
                sent_map[normalized_url] = timestamp
            self._sent_urls.save(storage_path, sent_map)
            if manual:
                logger.info(
                    "Manual mode: saved %d sent URLs to %s (to prevent duplicate in scheduled runs)",
                    len(new_articles),
                    storage_path,
                )
            else:
                logger.info("Saved %d sent URLs to %s", len(new_articles), storage_path)

        return 0
