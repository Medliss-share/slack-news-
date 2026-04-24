from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from fetcher import Article, fetch_all_feeds
from filter import filter_articles
from notifier import post_message
from storage import load_sent_urls, save_sent_urls
from extrasources import (
    fetch_medicaltech,
    fetch_htwatch,
    fetch_google_news,
    fetch_connpass,
    fetch_general_tech_google_news,
    fetch_general_tech_rss,
    fetch_healthtech_priority_google_news,
)
from categorizer import (
    ALL_CATEGORIES,
    CATEGORY_BADGES,
    CATEGORY_COMPETITOR,
    CATEGORY_CONFERENCE,
    CATEGORY_EMOJIS,
    CATEGORY_GENERAL_TECH,
    CATEGORY_HEALTHTECH,
    CATEGORY_LABELS,
    categorize_articles,
    normalize_category,
)

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


def _get_source_name(link: str) -> str:
    """URLからソース名を取得する。"""
    if "prtimes.jp" in link:
        return "PR TIMES"
    elif "news.google.com" in link:
        return "Google News"
    elif "medicaltech-news.com" in link:
        return "医療テックニュース"
    elif "ht-watch.com" in link:
        return "ヘルステックウォッチ"
    elif "connpass.com" in link:
        return "connpass"
    elif "publickey1.jp" in link or "publickey2.jp" in link:
        return "Publickey"
    elif "itmedia.co.jp" in link:
        return "ITmedia"
    elif "zdnet" in link:
        return "ZDNet Japan"
    elif "codezine.jp" in link:
        return "CodeZine"
    else:
        return "その他"


def _categorize_keywords(keywords: list[str], medical_keywords: list[str], it_keywords: list[str]) -> tuple[list[str], list[str]]:
    """キーワードを医療系とIT系に分類する。"""
    med_kw_lower = [kw.lower() for kw in medical_keywords]
    it_kw_lower = [kw.lower() for kw in it_keywords]
    
    medical_matched = []
    it_matched = []
    
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in med_kw_lower:
            medical_matched.append(kw)
        if kw_lower in it_kw_lower:
            it_matched.append(kw)
    
    return medical_matched, it_matched


def _truncate_summary(summary: str, limit: int = 150) -> str:
    """概要を limit 文字程度で文の途中を避けつつ切り詰める。"""
    summary = summary.strip()
    if len(summary) <= limit:
        return summary
    truncated = summary[:limit]
    for delimiter in ['。', '\n', '.', '！', '？']:
        last_pos = truncated.rfind(delimiter)
        if last_pos > int(limit * 0.67):
            truncated = truncated[:last_pos + 1]
            break
    return truncated + "..."


_WEEKDAY_JA = ("月", "火", "水", "木", "金", "土", "日")


def _format_date_header(now: datetime) -> str:
    """シンプルな日付ヘッダー: 📅 2026-04-25 (金) 21:00"""
    wd = _WEEKDAY_JA[now.weekday()]
    return f"📅 {now.strftime('%Y-%m-%d')} ({wd}) {now.strftime('%H:%M')}"


def build_message(
    articles: list[Article],
    now: datetime,
    categories: list[str] | None = None,
    webhook: str = "default",
) -> str:
    """配信用メッセージを組み立てる。

    categories が空または None の場合は "all"（従来互換・ソース別グループ表示）。
    categories が指定されている場合は、カテゴリ単位のセクションで表示する。
    webhook は空メッセージ時の文言切り替えに使う。
    """
    if not categories:
        return _build_all_message(articles, now)
    return _build_category_message(articles, now, categories, webhook=webhook)


# webhook 別の「該当なし」文言
_EMPTY_MESSAGES: dict[str, str] = {
    "a": "この時間帯のヘルステックニュースはありませんでした。",
    "b": "この時間帯のITニュースはありませんでした。",
}


def _build_category_message(
    articles: list[Article],
    now: datetime,
    categories: list[str],
    webhook: str = "default",
) -> str:
    """カテゴリ指定モードのSlackメッセージ。

    ヘッダーは日付のみ（「まとめ」等の固定タイトルなし）。
    各カテゴリごとにセクション分割して表示する。
    """
    date_header = _format_date_header(now)

    if not articles:
        empty_line = _EMPTY_MESSAGES.get(webhook.lower()) if webhook else None
        if not empty_line:
            labels = " / ".join(CATEGORY_LABELS.get(c, c) for c in categories)
            empty_line = f"本時間帯の「{labels}」に該当する新着はありませんでした。"
        return f"{date_header}\n\n{empty_line}"

    lines: list[str] = [date_header, ""]

    # カテゴリごとにグルーピングして出力
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

    # どのカテゴリにも属さなかった残り（実質発生しない想定だが保険）
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


def _append_article_lines(
    lines: list[str],
    articles: list[Article],
    highlight_categories: list[str],
) -> None:
    """記事一覧を lines に追記する（カテゴリメッセージ用の共通関数）。"""
    for idx, article in enumerate(articles, start=1):
        source = _get_source_name(article.link)
        source_tag = f"_{source}_"

        # 記事が該当する "ハイライト対象外" のカテゴリをバッジ併記
        extra_badges = [
            CATEGORY_BADGES[c]
            for c in (article.categories or [])
            if c not in highlight_categories and c in CATEGORY_BADGES
        ]
        badge_text = (" " + " ".join(extra_badges)) if extra_badges else ""

        lines.append(f"*{idx}. <{article.link}|{article.title}>*{badge_text}")

        # イベントは開催日時・場所を追記
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


def _build_all_message(articles: list[Article], now: datetime) -> str:
    """カテゴリ無指定（従来互換）のSlackメッセージ。ソース別に表示。"""
    date_header = _format_date_header(now)
    if not articles:
        return f"{date_header}\n\n本時間帯の新着はありませんでした。"

    lines = [date_header, ""]

    # ソース別にグループ化
    from collections import defaultdict
    articles_by_source = defaultdict(list)
    for article in articles:
        source = _get_source_name(article.link)
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
        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
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


def _normalize_title(title: str) -> str:
    """タイトルを正規化して比較用にする。"""
    import re
    # 記号、空白、改行を削除して小文字に変換
    # 日本語の文字も含めるように改善
    normalized = re.sub(r'[\s\u3000\u00A0\u2000-\u200B\u2028\u2029\uFEFF]', '', title.lower())
    # 一般的な記号を削除
    normalized = re.sub(r'[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]', '', normalized)
    return normalized


def _calculate_title_similarity(title1: str, title2: str) -> float:
    """2つのタイトルの類似度を計算する（0.0-1.0）。"""
    norm1 = _normalize_title(title1)
    norm2 = _normalize_title(title2)
    
    if not norm1 or not norm2:
        return 0.0
    
    # 完全一致
    if norm1 == norm2:
        return 1.0
    
    # 短い方が長い方に含まれている場合（部分一致）
    shorter = min(len(norm1), len(norm2))
    longer = max(len(norm1), len(norm2))
    
    if shorter >= 10:  # 10文字以上の場合のみ部分一致をチェック
        if len(norm1) <= len(norm2):
            if norm1 in norm2:
                # 部分一致の場合は、短い方の長さ / 長い方の長さで類似度を計算
                # ただし、最低でも0.7以上にする（短いタイトルが長いタイトルの一部なら高類似度）
                base_similarity = len(norm1) / len(norm2)
                return max(base_similarity, 0.7)
        else:
            if norm2 in norm1:
                base_similarity = len(norm2) / len(norm1)
                return max(base_similarity, 0.7)
    
    # 先頭部分の一致もチェック（短い方の80%以上が長い方の先頭と一致する場合）
    if shorter >= 5:
        overlap_length = min(shorter, int(shorter * 0.8))
        if len(norm1) <= len(norm2):
            if norm1[:overlap_length] == norm2[:overlap_length]:
                return 0.75  # 先頭が一致している場合は高類似度
        else:
            if norm2[:overlap_length] == norm1[:overlap_length]:
                return 0.75
    
    # 共通文字数をカウント（順序は考慮しない）
    common_chars = sum(1 for c in set(norm1) if c in norm2)
    total_chars = len(set(norm1) | set(norm2))
    
    if total_chars == 0:
        return 0.0
    
    # Jaccard類似度（文字集合の類似度）
    jaccard_similarity = common_chars / total_chars
    
    # 長さの類似度も考慮
    shorter = min(len(norm1), len(norm2))
    longer = max(len(norm1), len(norm2))
    length_similarity = shorter / longer if longer > 0 else 0.0
    
    # 共通部分文字列の長さを考慮（最長共通部分列の簡易版）
    # 3文字以上の共通部分文字列があるかチェック
    common_substring_score = 0.0
    for i in range(len(norm1) - 2):
        substring = norm1[i:i+3]
        if substring in norm2:
            common_substring_score = 0.2
            break
    
    # 重み付き平均
    similarity = (jaccard_similarity * 0.5) + (length_similarity * 0.3) + common_substring_score
    
    return min(similarity, 1.0)  # 1.0を超えないようにする


def _get_source_priority(link: str) -> int:
    """ソースの優先度を返す（数値が小さいほど優先度が高い）。"""
    if "prtimes.jp" in link:
        return 1  # PR TIMESが最優先
    elif "medicaltech-news.com" in link:
        return 2
    elif "ht-watch.com" in link:
        return 3
    elif "news.google.com" in link:
        return 5  # Google News を最下位にする
    else:
        return 5  # 未知のソースもGoogle Newsと同じ最下位扱い


def deduplicate_articles(articles: list[Article]) -> list[Article]:
    """URLとタイトルの重複を除去する（PR TIMESを最優先）。"""
    # まずURLで重複を除去
    seen_urls: set[str] = set()
    url_deduplicated: list[Article] = []
    for article in articles:
        if not article.link:
            continue
        # URLを正規化（末尾のスラッシュやクエリパラメータを考慮）
        normalized_url = article.link.rstrip("/").split("?")[0]
        if normalized_url not in seen_urls:
            seen_urls.add(normalized_url)
            url_deduplicated.append(article)
    
    # タイトルの重複を除去（優先度の高いソースを残す）
    # 類似度の閾値（0.7以上で重複とみなす）
    SIMILARITY_THRESHOLD = 0.7
    
    deduplicated: list[Article] = []
    # タイトルの正規化版をキャッシュして効率化
    title_cache: dict[str, str] = {}
    
    for article in url_deduplicated:
        if not article.title:
            continue
        
        # タイトルを正規化
        normalized_title = _normalize_title(article.title)
        title_cache[article.title] = normalized_title
        
        # 既に追加された記事と類似度をチェック
        is_duplicate = False
        for existing_article in deduplicated:
            if not existing_article.title:
                continue
            
            # 完全一致チェック（正規化後）
            existing_normalized = title_cache.get(existing_article.title, _normalize_title(existing_article.title))
            if normalized_title == existing_normalized:
                # 完全一致の場合は重複とみなす
                similarity = 1.0
            else:
                # 類似度を計算
                similarity = _calculate_title_similarity(article.title, existing_article.title)
            
            if similarity >= SIMILARITY_THRESHOLD:
                # 重複と判定された場合、優先度の高い方を残す
                existing_priority = _get_source_priority(existing_article.link)
                new_priority = _get_source_priority(article.link)
                
                if new_priority < existing_priority:
                    # 新しい記事の方が優先度が高い場合、既存の記事を置き換え
                    deduplicated.remove(existing_article)
                    deduplicated.append(article)
                    logger.info(
                        "Replaced duplicate article (similarity: %.2f, kept from %s): %s",
                        similarity,
                        _get_source_name(article.link),
                        article.title[:50],
                    )
                else:
                    # 既存の記事の方が優先度が高い場合、新しい記事をスキップ
                    logger.info(
                        "Skipped duplicate article (similarity: %.2f, kept from %s): %s",
                        similarity,
                        _get_source_name(existing_article.link),
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


def filter_by_time_range(articles: list[Article], now: datetime, hours_before: int = 6) -> list[Article]:
    """指定された時間範囲内に公開された記事のみをフィルタリングする。
    
    Args:
        articles: フィルタリング対象の記事リスト
        now: 現在時刻（JST）
        hours_before: 現在時刻から何時間前までを含めるか（デフォルト: 6時間）
    
    Returns:
        フィルタリング後の記事リスト
    """
    if hours_before <= 0:
        return articles
    
    time_start = now - timedelta(hours=hours_before)
    
    filtered: list[Article] = []
    skipped_no_date = 0
    skipped_old = 0
    
    for article in articles:
        # 開催予定イベント（connpass等）は published ベースの時間範囲フィルタをバイパス
        if article.is_event:
            filtered.append(article)
            continue

        if article.published_at is None:
            # 公開日時が不明な記事は除外（古い記事の可能性が高い）
            skipped_no_date += 1
            logger.debug("Skipping article with no published_at: %s", article.title[:50])
            continue
        
        # タイムゾーンを統一（JSTに変換）
        article_time = article.published_at
        if article_time.tzinfo is None:
            # タイムゾーン情報がない場合は、JSTと仮定
            article_time = article_time.replace(tzinfo=timezone(timedelta(hours=9)))
        else:
            # JSTに変換
            article_time = article_time.astimezone(timezone(timedelta(hours=9)))
        
        # 時間範囲内かチェック
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
    """記事をソートする。優先キーワード（電子カルテ）を含む記事を優先し、その後公開日時でソート。"""
    # 優先キーワード
    PRIORITY_KEYWORD = "電子カルテ"
    
    def sort_key(article: Article) -> tuple[int, float]:
        """ソートキー: (優先度, 公開日時)"""
        # 優先キーワードを含むかチェック
        text = f"{article.title} {article.summary or ''}".lower()
        has_priority = PRIORITY_KEYWORD.lower() in text
        # 優先度: 0=優先キーワードあり、1=なし
        priority = 0 if has_priority else 1
        # 公開日時（新しい順）
        timestamp = article.published_at.timestamp() if article.published_at else float("-inf")
        return (priority, -timestamp)  # タイムスタンプは負数にして降順にする
    
    return sorted(articles, key=sort_key)


def _resolve_webhook_url(webhook: str) -> str | None:
    """--webhook 引数から実際の URL を解決する。"""
    webhook = (webhook or "default").lower()
    if webhook == "a":
        return config.SLACK_WEBHOOK_URL_A or config.SLACK_WEBHOOK_URL
    if webhook == "b":
        return config.SLACK_WEBHOOK_URL_B or config.SLACK_WEBHOOK_URL
    return config.SLACK_WEBHOOK_URL


def _parse_categories(category_arg: str) -> list[str]:
    """--category 引数を正規化する。all または空文字なら [] を返す（従来互換）。

    エイリアス（`tech` → `healthtech`）も解決する。
    """
    if not category_arg or category_arg.lower() == "all":
        return []
    parts = [normalize_category(c.strip()) for c in category_arg.split(",") if c.strip()]
    valid = [c for c in parts if c in ALL_CATEGORIES]
    if not valid:
        return []
    # 順序は指定順を維持（重複は除去）
    seen: set[str] = set()
    ordered: list[str] = []
    for c in valid:
        if c not in seen:
            ordered.append(c)
            seen.add(c)
    return ordered


def run(
    dry_run: bool = False,
    storage_path: Path | None = None,
    max_items: int | None = None,
    manual: bool = False,
    category: str = "all",
    webhook: str = "default",
) -> int:
    storage_path = storage_path or config.SENT_URLS_PATH
    categories = _parse_categories(category)

    # 手動実行時は5件に制限、それ以外は指定された max_items またはデフォルト値
    if manual:
        max_items = 5
    elif max_items is None:
        # カテゴリ指定時は MAX_ARTICLES_PER_CATEGORY、all は MAX_ARTICLES_PER_POST
        max_items = (
            config.MAX_ARTICLES_PER_CATEGORY
            if categories
            else config.MAX_ARTICLES_PER_POST
        )

    # webhook 指定からどちら系のソースを取得するかを決める
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

    # -----------------------------------------------------------------------
    # ヘルステック系ソース（Channel A / default 向け）: 医療×IT フィルタ対象
    # -----------------------------------------------------------------------
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
                    med_count, it_count, both_count,
                )
                fetched.extend(rss_articles)
        else:
            logger.info("RSS_FEEDS が空のため、RSS取得をスキップします。")

        # 医療×IT ソース（medicaltech / htwatch / googlenews）
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
                med_c, it_c, both_c,
            )
            fetched.extend(ht_articles)

        # Channel A 専用: 医療DX/ヘルステック資金調達 Google News 優先クエリ（ゲートバイパス）
        try:
            ht_priority = fetch_healthtech_priority_google_news(
                config.HEALTHTECH_PRIORITY_GOOGLE_NEWS_QUERIES,
                timeout=config.FETCH_TIMEOUT,
            )
            fetched.extend(ht_priority)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to fetch healthtech-priority Google News: %s", exc)

    # -----------------------------------------------------------------------
    # 一般IT 系ソース + connpass（Channel B / default 向け）: 医療×IT バイパス
    # -----------------------------------------------------------------------
    if want_general_tech_sources:
        # PR TIMES（Channel B 一般ITの主ソース。キーワードは GENERAL_TECH_KEYWORDS で絞り込み）
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

        # Google News（.env で GENERAL_TECH_GOOGLE_NEWS_QUERIES を指定したときのみ）
        if config.GENERAL_TECH_GOOGLE_NEWS_QUERIES:
            try:
                gt_gn = fetch_general_tech_google_news(
                    config.GENERAL_TECH_GOOGLE_NEWS_QUERIES,
                    timeout=config.FETCH_TIMEOUT,
                )
                fetched.extend(gt_gn)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to fetch general-tech Google News: %s", exc)

        # 追加の一般IT RSS（Publickey 等。.env の GENERAL_TECH_RSS_URLS）
        if config.GENERAL_TECH_RSS_URLS:
            try:
                gt_rss = fetch_general_tech_rss(
                    config.GENERAL_TECH_RSS_URLS,
                    timeout=config.FETCH_TIMEOUT,
                )
                fetched.extend(gt_rss)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to fetch general-tech RSS: %s", exc)

        # connpass（イベント: オンライン/広島・7日以内）
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

    # Channel A のときは "医療DX らしさ" を必須化（矯正歯科/美容系や一般クリニックIT化ネタを排除）
    medical_dx_required = webhook_lower == "a"
    medical_dx_keywords_arg = (
        config.MEDICAL_DX_KEYWORDS if medical_dx_required else None
    )
    # Channel A / default のときはヘルステック企業ホワイトリストを渡して、
    # 該当企業名の記事は医療×IT / 医療DX ゲートをバイパス（漏れを減らす）
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

    # カテゴリ分類（all モードでも後続処理のためにタグ付けしておく）
    filtered = categorize_articles(
        filtered,
        healthtech_keywords=config.HEALTHTECH_TECH_KEYWORDS,
        competitor_keywords=config.COMPETITOR_ACTION_KEYWORDS,
        conference_keywords=config.CONFERENCE_KEYWORDS,
        general_tech_keywords=config.GENERAL_TECH_KEYWORDS,
    )

    # カテゴリ指定があれば該当カテゴリのいずれかに属する記事のみに絞る
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

    # 日時フィルタリング（指定時間範囲の記事のみを対象）
    now = datetime.now(timezone(timedelta(hours=9)))
    logger.info("Applying time window: last %d hour(s) (now: %s)", config.TIME_RANGE_HOURS, now.strftime("%Y-%m-%d %H:%M:%S JST"))
    filtered = filter_by_time_range(filtered, now, hours_before=config.TIME_RANGE_HOURS)
    logger.info("After time range filtering: %d articles", len(filtered))
    
    filtered = deduplicate_articles(filtered)
    logger.info("After deduplication: %d articles", len(filtered))
    filtered = sort_articles(filtered)

    # 手動実行時は送信済みURLのチェックをスキップし、Google Newsを除外
    if manual:
        logger.info("Manual mode: skipping sent URL check, excluding Google News, limiting to %d articles", max_items)
        # Google Newsを除外
        filtered_without_google = [a for a in filtered if a.link and "news.google.com" not in a.link]
        logger.info("Excluded Google News: %d articles remaining (from %d total)", len(filtered_without_google), len(filtered))
        new_articles = filtered_without_google
        if len(new_articles) > max_items:
            new_articles = new_articles[:max_items]
    else:
        # 送信済みURLをチェック（同じ日の別の時間帯でも重複を防ぐ）
        sent_map = load_sent_urls(storage_path)
        logger.info("Loaded %d sent URLs from storage", len(sent_map))
        
        new_articles = []
        skipped_count = 0
        for article in filtered:
            if not article.link:
                continue
            # URLを正規化してチェック（既存データとの互換性のため、元のURLと正規化URLの両方をチェック）
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

    # nowは既に定義済み（日時フィルタリングで使用）
    message = build_message(new_articles, now, categories=categories, webhook=webhook_lower)

    logger.info("New articles: %d (after dedupe and limit)", len(new_articles))

    # 配信先 Webhook を解決
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

    success = post_message(webhook_url, message, timeout=config.FETCH_TIMEOUT)
    if not success:
        logger.error("Slack 送信に失敗しました (webhook=%s)。", webhook_label)
        return 1
    logger.info("Posted to Slack (webhook=%s)", webhook_label)

    # 送信済みURLを保存（手動実行時も保存して、定時実行時に重複を防ぐ）
    if new_articles:
        sent_map = load_sent_urls(storage_path)  # 最新の状態を再読み込み
        timestamp = now.isoformat()
        for article in new_articles:
            # URLを正規化して保存（重複チェックと同じ形式にする）
            normalized_url = article.link.rstrip("/").split("?")[0]
            sent_map[normalized_url] = timestamp
        save_sent_urls(sent_map, storage_path)
        if manual:
            logger.info("Manual mode: saved %d sent URLs to %s (to prevent duplicate in scheduled runs)", len(new_articles), storage_path)
        else:
            logger.info("Saved %d sent URLs to %s", len(new_articles), storage_path)

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="医療×ITニュースをフィルタしてSlackに投稿します。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Slack に送らず標準出力にメッセージを表示する",
    )
    parser.add_argument(
        "--storage-path",
        type=Path,
        help=f"配信済みURL保存先 (デフォルト: {config.SENT_URLS_PATH})",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        help=f"1回の投稿件数上限 (デフォルト: {config.MAX_ARTICLES_PER_POST})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="詳細ログを有効にする",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="手動実行モード（送信済みURLチェックをスキップし、5件に制限）",
    )
    parser.add_argument(
        "--category",
        default="all",
        help=(
            "配信カテゴリ（カンマ区切り複数指定可）: "
            "healthtech=ヘルステック技術動向, general_tech=一般IT技術動向, "
            "competitor=競合動向, conference=カンファレンス/イベント, "
            "all=全件ソース別まとめ "
            "(tech は healthtech のエイリアス) "
            "(例: --category competitor,healthtech,conference) (default: all)"
        ),
    )
    parser.add_argument(
        "--webhook",
        choices=["default", "a", "b"],
        default="default",
        help=(
            "配信先 Slack Webhook を選択: "
            "a=SLACK_WEBHOOK_URL_A（ヘルステック＝競合/ヘルステック技術動向/ヘルステックカンファレンス, 朝）, "
            "b=SLACK_WEBHOOK_URL_B（一般IT技術動向+カンファレンス/イベント, 夜）, "
            "default=SLACK_WEBHOOK_URL (default: default)"
        ),
    )
    return parser.parse_args()


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s %(levelname)s %(name)s - %(message)s"
    if config.LOG_FILE:
        handlers = [
            logging.StreamHandler(),
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        ]
        logging.basicConfig(level=level, format=log_format, handlers=handlers)
    else:
        logging.basicConfig(level=level, format=log_format)


if __name__ == "__main__":
    args = parse_args()
    configure_logging(args.verbose)
    exit_code = run(
        dry_run=args.dry_run,
        storage_path=args.storage_path,
        max_items=args.max_items,
        manual=args.manual,
        category=args.category,
        webhook=args.webhook,
    )
    raise SystemExit(exit_code)
