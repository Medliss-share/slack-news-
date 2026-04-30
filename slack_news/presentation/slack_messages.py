"""Slack 向けメッセージ組み立て（Presentation 層）。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from categorizer import CATEGORY_BADGES, CATEGORY_EMOJIS, CATEGORY_LABELS

from slack_news.domain.article import Article
from slack_news.domain.source_labels import source_display_name

_WEEKDAY_JA = ("月", "火", "水", "木", "金", "土", "日")

_EMPTY_MESSAGES: dict[str, str] = {
    "a": "この時間帯のヘルステックニュースはありませんでした。",
    "b": "この時間帯のITニュースはありませんでした。",
}


def _format_date_header(now: datetime) -> str:
    wd = _WEEKDAY_JA[now.weekday()]
    return f"📅 {now.strftime('%Y-%m-%d')} ({wd}) {now.strftime('%H:%M')}"


def _truncate_summary(summary: str, limit: int = 150) -> str:
    summary = summary.strip()
    if len(summary) <= limit:
        return summary
    truncated = summary[:limit]
    for delimiter in ["。", "\n", ".", "！", "？"]:
        last_pos = truncated.rfind(delimiter)
        if last_pos > int(limit * 0.67):
            truncated = truncated[: last_pos + 1]
            break
    return truncated + "..."


def _append_article_lines(
    lines: list[str],
    articles: list[Article],
    highlight_categories: list[str],
) -> None:
    for idx, article in enumerate(articles, start=1):
        source = source_display_name(article.link)
        source_tag = f"_{source}_"

        extra_badges = [
            CATEGORY_BADGES[c]
            for c in (article.categories or [])
            if c not in highlight_categories and c in CATEGORY_BADGES
        ]
        badge_text = (" " + " ".join(extra_badges)) if extra_badges else ""

        lines.append(f"*{idx}. <{article.link}|{article.title}>*{badge_text}")

        if article.is_event and article.event_start_at:
            event_info = article.event_start_at.strftime("%Y/%m/%d %H:%M")
            if article.event_location:
                event_info += f" / {article.event_location}"
            lines.append(f"   📅 {event_info}")
            lines.append(f"   {source_tag}")
        else:
            lines.append(f"   {source_tag}")
            if article.summary:
                lines.append(f"   {_truncate_summary(article.summary)}")

        if idx < len(articles):
            lines.append("")


def _build_category_message(
    articles: list[Article],
    now: datetime,
    categories: list[str],
    webhook: str = "default",
) -> str:
    date_header = _format_date_header(now)

    if not articles:
        empty_line = _EMPTY_MESSAGES.get(webhook.lower()) if webhook else None
        if not empty_line:
            labels = " / ".join(CATEGORY_LABELS.get(c, c) for c in categories)
            empty_line = f"本時間帯の「{labels}」に該当する新着はありませんでした。"
        return f"{date_header}\n\n{empty_line}"

    lines: list[str] = [date_header, ""]

    seen_ids: set[int] = set()
    for category in categories:
        emoji = CATEGORY_EMOJIS.get(category, "📰")
        label = CATEGORY_LABELS.get(category, category)
        section_articles = [
            a
            for a in articles
            if a.categories and category in a.categories and id(a) not in seen_ids
        ]
        if not section_articles:
            continue

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"{emoji} *{label}* ({len(section_articles)}件)")
        lines.append("")
        _append_article_lines(lines, section_articles, highlight_categories=categories)
        for a in section_articles:
            seen_ids.add(id(a))
        lines.append("")

    leftover = [a for a in articles if id(a) not in seen_ids]
    if leftover:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📰 *その他* ({len(leftover)}件)")
        lines.append("")
        _append_article_lines(lines, leftover, highlight_categories=categories)
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 合計 *{len(articles)}件*")
    return "\n".join(lines).rstrip()


def _build_all_message(articles: list[Article], now: datetime) -> str:
    date_header = _format_date_header(now)
    if not articles:
        return f"{date_header}\n\n本時間帯の新着はありませんでした。"

    lines = [date_header, ""]

    articles_by_source: dict[str, list[Article]] = defaultdict(list)
    for article in articles:
        source = source_display_name(article.link)
        articles_by_source[source].append(article)

    idx = 1
    source_priority = {
        "PR TIMES": 1,
        "医療テックニュース": 2,
        "ヘルステックウォッチ": 3,
        "connpass": 4,
        "TECH PLAY": 4,
        "Google News": 5,
    }

    for source in sorted(articles_by_source.keys(), key=lambda s: source_priority.get(s, 99)):
        if source not in source_priority:
            continue
        source_articles = articles_by_source[source]
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📰 *{source}* ({len(source_articles)}件)")
        lines.append("")

        for article in source_articles:
            lines.append(f"*{idx}. <{article.link}|{article.title}>*")
            if article.summary:
                lines.append(f"   {_truncate_summary(article.summary)}")
            idx += 1
            if idx <= len(articles):
                lines.append("")

    lines.append("")
    footer = f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📊 合計 *{len(articles)}件*の記事を配信"
    lines.append(footer)

    return "\n".join(lines).rstrip()


def build_message(
    articles: list[Article],
    now: datetime,
    categories: list[str] | None = None,
    webhook: str = "default",
) -> str:
    if not categories:
        return _build_all_message(articles, now)
    return _build_category_message(articles, now, categories, webhook=webhook)
