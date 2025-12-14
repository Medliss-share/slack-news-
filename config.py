"""
設定値とキーワード定義。

必要に応じて環境変数で上書きできます:
- SLACK_WEBHOOK_URL: Slack Incoming Webhook のURL
- PRTIMES_RSS_URLS: カンマ区切りの RSS URL 一覧
"""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str = ".env") -> None:
    """外部ライブラリなしでシンプルな .env 読み込みを行う。"""
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


# .env があれば最初に読み込む
load_dotenv()

# Slack Webhook
SLACK_WEBHOOK_URL: str | None = os.environ.get("SLACK_WEBHOOK_URL")

# RSS URL（カンマ区切りの環境変数で上書き可能）
_rss_env = [
    url.strip()
    for url in os.environ.get("PRTIMES_RSS_URLS", "").split(",")
    if url.strip()
]

# デフォルトは全件取得用の index.rdf。不要なら .env で上書きしてください。
DEFAULT_RSS_FEEDS: list[str] = [
    "https://prtimes.jp/index.rdf",
]
RSS_FEEDS: list[str] = _rss_env or DEFAULT_RSS_FEEDS

# 追加スクレイピング対象（カンマ区切りで指定: medicaltech, htwatch, googlenews）
# デフォルトは Google News を除外し、medicaltech / htwatch のみ
DEFAULT_EXTRA_SOURCES: list[str] = ["medicaltech", "htwatch"]
_env_extra_sources = [
    src.strip()
    for src in os.environ.get("EXTRA_SOURCES", "").split(",")
    if src.strip()
]
EXTRA_SOURCES: list[str] = _env_extra_sources if _env_extra_sources else DEFAULT_EXTRA_SOURCES

# キーワード定義（編集しやすいようにここでまとめる）
MEDICAL_KEYWORDS: list[str] = [
    "医療",
    "ヘルスケア",
    "診療",
    "病院",
    "歯科",
    "看護",
    "クリニック",
    "製薬",
    "健康",
    "検査",
    "健診",
    "検診",
    "患者",
    "医薬",
    "医療機器",
    "介護",
    "介護施設",
    "薬局",
    "薬剤",
    "医師",
    "遠隔医療",
    "遠隔診療",
    "オンライン診療",
    "医療DX",
    "デジタルヘルス",
    "PHR",
    "メディカル",
    "ヘルス",
    "ウェルネス",
    "医療向け",
    "医師向け",
    "病院向け",
    "医療法人",
    "医薬品",
    "薬品",
    "薬剤師",
    "診断",
    "治療",
    "臨床",
    "入院",
    "外来",
    "処方",
    "調剤",
    "リハビリ",
    "訪問診療",
    "訪問看護",
    "在宅医療",
    "在宅看護",
]

IT_KEYWORDS: list[str] = [
    "AI",
    "IT",
    "DX",
    "デジタル",
    "電子カルテ",
    "システム",
    "SaaS",
    "SaaS型",
    "クラウド",
    "クラウド型",
    "アプリ",
    "アプリケーション",
    "IoT",
    "データ",
    "分析",
    "解析",
    "プラットフォーム",
    "アナリティクス",
    "ICT",
    "オンライン",
    "ソフトウェア",
    "API",
    "デジタル化",
    "IT化",
    "情報システム",
]

EXCLUDE_KEYWORDS: list[str] = [
    # 美容・健康関連（医療×ITとは無関係）
    "美容整形",
    "ダイエットサプリ",
    "エステ",
    "化粧品",
    "スキンケア",
    "メイクアップ",
    "フィットネス",
    "ジム",
    "トレーニング",
    
    # 食品・飲料関連
    "健康食品",
    "健康飲料",
    "サプリメント",
    "レストラン",
    "カフェ",
    "グルメ",
    "料理",
    "レシピ",

    # 動物医療・ペット関連（人医療向けではない）
    "動物病院",
    "獣医",
    "獣医師",
    "動物医療",
    "ペット",

    # 物流/サプライチェーン中心の話題（医療提供とは無関係）
    "サプライチェーン",
    "サプライチェーンDX",
    "物流",
    "ロジスティクス",
    
    # ITキーワードの誤マッチ防止
    "クラウドファンディング",  # ITの「クラウド」と混同しないように除外
    
    # 不動産・建設
    "不動産",
    "マンション",
    "住宅",
    "建設",
    "建築",
    
    # 金融・保険（生命保険・損害保険などは医療関連の可能性もあるが、一般的な保険は除外）
    "投資",
    "資産運用",
    
    # 教育（医療系の学校は含めたいが、一般的な教育は除外）
    "塾",
    "予備校",
    "学習塾",
    
    # エンタメ・旅行（医療IT関連のセミナー・イベント・展示会は含める）
    "旅行",
    "観光",
    "エンターテインメント",
    "マラソン",
    "ランニング",
    "スポーツ",
    
    # ITキーワードの誤マッチ防止（医療×ITとは無関係なIT活用）
    "EC",  # ECシステム、ECプラットフォームなど
    "eコマース",
    "ECサイト",
    "予約システム",  # レストラン予約など（医療予約システムは含めたいが、一般的な予約システムは除外）
    "会員システム",  # 会員管理システム（医療会員システムは含めたいが、一般的な会員システムは除外）
    "マーケティング",  # マーケティングデータ分析など
    "広告",
    "ゲーム",  # ゲームアプリなど
    "ショッピング",  # ショッピングアプリなど
    "スマートホーム",  # IoT家電関連
    "スマート家電",
    "家電",
]

# .envで追加の除外キーワードを渡せるようにする（カンマ区切り）
_env_exclude_keywords = [
    kw.strip()
    for kw in os.environ.get("EXCLUDE_EXTRA_KEYWORDS", "").split(",")
    if kw.strip()
]
if _env_exclude_keywords:
    EXCLUDE_KEYWORDS.extend(_env_exclude_keywords)

# リンクドメインで除外する場合に使用（カンマ区切り）
EXCLUDE_DOMAINS: list[str] = [
    dom.strip().lower()
    for dom in os.environ.get("EXCLUDE_DOMAINS", "").split(",")
    if dom.strip()
]

# 1回あたりの投稿件数上限（Slack 文字数制限を考慮）
MAX_ARTICLES_PER_POST: int = 5

# RSS 取得タイムアウト（秒）
FETCH_TIMEOUT: int = 10

# 取得対象とする時間範囲（時間単位）。デフォルトは直近24時間（前回実行以降の記事を取得）。
TIME_RANGE_HOURS: int = int(os.environ.get("TIME_RANGE_HOURS", "24"))

# 配信済みURLの保存先
DATA_DIR = Path("data")
SENT_URLS_PATH = DATA_DIR / "sent_urls.json"
# ログファイル（環境変数 LOG_FILE で指定。未指定なら標準出力のみ）
LOG_FILE = os.environ.get("LOG_FILE") or None
