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
from extrasources import fetch_medicaltech, fetch_htwatch, fetch_google_news

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


def build_message(articles: list[Article], now: datetime) -> str:
    if not articles:
        return "🩺🤖 本時間帯の医療×IT新着はありませんでした。"

    header = f"ニュースまとめをお届けします！"
    lines = [header, ""]
    
    # ソース別にグループ化
    from collections import defaultdict
    articles_by_source = defaultdict(list)
    for article in articles:
        source = _get_source_name(article.link)
        articles_by_source[source].append(article)
    
    # 記事をソース別に表示（優先度順）
    idx = 1
    # ソースの優先度順（PR TIMESが最優先、Google Newsが最下位）
    source_priority = {
        "PR TIMES": 1,
        "医療テックニュース": 2,
        "ヘルステックウォッチ": 3,
        "Google News": 5,
    }
    
    for source in sorted(articles_by_source.keys(), key=lambda s: source_priority.get(s, 99)):
        if source not in source_priority:
            # 未知のソースは出さない
            continue
        source_articles = articles_by_source[source]
        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📰 *{source}* ({len(source_articles)}件)")
        lines.append("")
        
        for article in source_articles:
            # タイトルをハイパーリンク形式にする
            lines.append(f"*{idx}. <{article.link}|{article.title}>*")
            
            # 概要（description）があれば表示（最大150文字、文の途中で切らない）
            if article.summary:
                summary = article.summary.strip()
                if len(summary) > 150:
                    # 150文字以内で文の終わり（句点、改行）を探す
                    truncated = summary[:150]
                    # 最後の句点、改行、または適切な区切り位置を探す
                    for delimiter in ['。', '\n', '.', '！', '？']:
                        last_pos = truncated.rfind(delimiter)
                        if last_pos > 100:  # 100文字以上は確保
                            truncated = truncated[:last_pos + 1]
                            break
                    summary = truncated + "..."
                lines.append(f"   {summary}")
            
            idx += 1
            if idx <= len(articles):  # 最後の記事以外は空行を追加
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


def run(dry_run: bool = False, storage_path: Path | None = None, max_items: int | None = None, manual: bool = False) -> int:
    storage_path = storage_path or config.SENT_URLS_PATH
    # 手動実行時は5件に制限、それ以外は指定されたmax_itemsまたはデフォルト値
    if manual:
        max_items = 5
    else:
        max_items = max_items or config.MAX_ARTICLES_PER_POST

    fetched: list[Article] = []
    
    # RSSフィードから取得（オプション）
    feed_urls = config.RSS_FEEDS
    if feed_urls:
        logger.info("Starting fetch for %d RSS feed(s)", len(feed_urls))
        rss_articles = fetch_all_feeds(feed_urls, timeout=config.FETCH_TIMEOUT)
        if not rss_articles:
            logger.warning("RSSフィードから記事を取得できませんでした。")
        else:
            med_count, it_count, both_count = _count_keyword_hits(rss_articles)
            logger.info("RSS keyword hits (before exclude): med=%d it=%d both=%d", med_count, it_count, both_count)
            fetched.extend(rss_articles)
    else:
        logger.info("RSS_FEEDS が空のため、RSS取得をスキップします。")

    # Webスクレイピングソース（優先）
    if config.EXTRA_SOURCES:
        logger.info("Fetching web scraping sources: %s", ", ".join(config.EXTRA_SOURCES))
    extra_articles: list[Article] = []
    for src in config.EXTRA_SOURCES:
        try:
            if src.lower() == "medicaltech":
                articles = fetch_medicaltech(timeout=config.FETCH_TIMEOUT)
                extra_articles.extend(articles)
                logger.info("Fetched %d articles from medicaltech-news", len(articles))
            elif src.lower() == "htwatch":
                articles = fetch_htwatch(timeout=config.FETCH_TIMEOUT)
                extra_articles.extend(articles)
                logger.info("Fetched %d articles from ht-watch", len(articles))
            elif src.lower() == "googlenews" or src.lower() == "google-news":
                articles = fetch_google_news(timeout=config.FETCH_TIMEOUT)
                extra_articles.extend(articles)
                logger.info("Fetched %d articles from Google News", len(articles))
            else:
                logger.warning("Unknown extra source: %s", src)
        except Exception as exc:
            logger.exception("Failed to fetch from %s: %s", src, exc)
    
    if extra_articles:
        med_c, it_c, both_c = _count_keyword_hits(extra_articles)
        logger.info("Web scraping keyword hits (before exclude): med=%d it=%d both=%d", med_c, it_c, both_c)
        fetched.extend(extra_articles)
    
    if not fetched:
        logger.warning("すべてのソースから記事を取得できませんでした。")
    else:
        logger.info("Total fetched articles: %d", len(fetched))

    filtered = filter_articles(
        fetched,
        medical_keywords=config.MEDICAL_KEYWORDS,
        it_keywords=config.IT_KEYWORDS,
        exclude_keywords=config.EXCLUDE_KEYWORDS,
        exclude_domains=config.EXCLUDE_DOMAINS,
    )
    logger.info("After keyword filtering: %d articles", len(filtered))
    
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
    message = build_message(new_articles, now)

    logger.info("New articles: %d (after dedupe and limit)", len(new_articles))

    if dry_run:
        logger.info("Dry-run mode: message not sent to Slack.")
        print(message)
        return 0

    success = post_message(config.SLACK_WEBHOOK_URL, message, timeout=config.FETCH_TIMEOUT)
    if not success:
        logger.error("Slack 送信に失敗しました。")
        return 1

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
    )
    raise SystemExit(exit_code)
