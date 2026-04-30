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
# デフォルト（--category=all や --webhook 未指定のフォールバック）
SLACK_WEBHOOK_URL: str | None = os.environ.get("SLACK_WEBHOOK_URL")
# Channel A: 競合動向（朝配信）
SLACK_WEBHOOK_URL_A: str | None = os.environ.get("SLACK_WEBHOOK_URL_A") or SLACK_WEBHOOK_URL
# Channel B: IT技術動向 + カンファレンス/イベント（夜配信）
SLACK_WEBHOOK_URL_B: str | None = os.environ.get("SLACK_WEBHOOK_URL_B") or SLACK_WEBHOOK_URL

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

# 追加スクレイピング対象（カンマ区切りで指定: medicaltech, htwatch, googlenews, connpass）
# デフォルトは Google News を除外し、medicaltech / htwatch / connpass
DEFAULT_EXTRA_SOURCES: list[str] = ["medicaltech", "htwatch", "connpass"]
_env_extra_sources = [
    src.strip()
    for src in os.environ.get("EXTRA_SOURCES", "").split(",")
    if src.strip()
]
EXTRA_SOURCES: list[str] = _env_extra_sources if _env_extra_sources else DEFAULT_EXTRA_SOURCES

# =============================================================================
# イベント (connpass) 用フィルタ設定
# =============================================================================
# イベント開催場所の一致判定キーワード。summary 内の開催場所にいずれかが含まれていれば通す
DEFAULT_EVENT_LOCATIONS: list[str] = ["オンライン", "広島"]
_env_event_locations = [
    loc.strip()
    for loc in os.environ.get("EVENT_LOCATIONS", "").split(",")
    if loc.strip()
]
EVENT_LOCATIONS: list[str] = _env_event_locations or DEFAULT_EVENT_LOCATIONS

# イベントを何日先まで拾うか（開催日が now 〜 now + N日 以内なら通す）
EVENT_LOOKAHEAD_DAYS: int = int(os.environ.get("EVENT_LOOKAHEAD_DAYS", "7"))

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
    # 国・自治体の医療政策（Google News 優先クエリ等でタイトルに省名のみの場合の医療側マッチ用）
    "厚生労働省",
    "厚労省",
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

# =============================================================================
# カテゴリ分類用キーワード辞書
# =============================================================================
# ヘルステック特化の IT 技術動向キーワード（Channel A 向け）
# 医療×IT フィルタを通過した記事の中で、さらに "ヘルステック文脈の技術動向" かを判定する
HEALTHTECH_TECH_KEYWORDS: list[str] = [
    # 医療情報標準
    "FHIR",
    "HL7",
    "DICOM",
    "SS-MIX",
    "HL7 FHIR",
    # データ基盤 / 相互運用性
    "医療データ基盤",
    "PHR",
    "EHR",
    "電子カルテ",
    "データ連携基盤",
    "全国医療情報プラットフォーム",
    "相互運用性",
    # 規制・品質系 IT
    "SaMD",
    "プログラム医療機器",
    "医療DX",
    "デジタル療法",
    "DTx",
    "薬事",
    "PMDA",
    "FDA承認",
    # 医療AI
    "医療AI",
    "診断支援AI",
    "画像診断AI",
    "医用画像",
    # 遠隔医療系
    "オンライン診療",
    "遠隔医療",
    "遠隔診療",
    # 医療分野のAI活用（医療×IT 通過記事前提なので弱めのキーワードも許容）
    "生成AI",
    "LLM",
    "ChatGPT",
    "Claude",
    "RAG",
]

# 一般IT 技術動向キーワード（Channel B 向け）
# PR TIMES 等の一般ソースから「AIエージェント / サイバーセキュリティ / システム開発」周辺に絞り込む
GENERAL_TECH_KEYWORDS: list[str] = [
    # --- 生成AI / LLM（PR TIMES で頻出。エージェント系と併せて拾う）---
    "生成AI",
    "LLM",
    "ChatGPT",
    "Claude",
    "Gemini",
    "AI活用",
    "AIソリューション",
    # --- AIエージェント（広い「生成AI」単体は避け、エージェント文脈を優先）---
    "AIエージェント",
    "エージェントAI",
    "自律型AI",
    "自律エージェント",
    "マルチエージェント",
    "Agentic",
    "AIエージェントプラットフォーム",
    "LLMエージェント",
    "対話型エージェント",
    "エージェント基盤",
    "Model Context Protocol",
    "MCP",
    "AIオーケストレーション",
    # --- サイバーセキュリティ ---
    "セキュリティ",
    "サイバーセキュリティ",
    "クラウドセキュリティ",
    "情報セキュリティ",
    "サイバー攻撃",
    "ランサムウェア",
    "ゼロトラスト",
    "脆弱性",
    "CVE",
    "ゼロデイ",
    "不正アクセス",
    "データ漏洩",
    "情報漏洩",
    "EDR",
    "XDR",
    "セキュリティ監査",
    "侵入検知",
    "マルウェア",
    "フィッシング対策",
    "WAF",
    "脆弱性診断",
    "ペネトレーションテスト",
    "ペネトレーション",
    "セキュリティ運用",
    "SBOM",
    "ソフトウェアサプライチェーン",
    "サプライチェーン攻撃",
    "セキュリティ対策",
    "セキュリティ強化",
    # --- システム開発・基盤 ---
    "システム開発",
    "システム導入",
    "ソフトウェア開発",
    "アプリケーション開発",
    "システム刷新",
    "システム統合",
    "システム構築",
    "システム更改",
    "モダナイゼーション",
    "レガシー刷新",
    "DevOps",
    "CI/CD",
    "SRE",
    "マイクロサービス",
    "アジャイル開発",
    "API開発",
    "バックエンド",
    "基盤構築",
    "クラウド移行",
    "クラウドネイティブ",
    "コンテナ",
    "Kubernetes",
    "インフラ自動化",
    "IaC",
    "アーキテクチャ刷新",
    # PR 文面でよく出る表現（index.rdf 全体からのヒット率を上げる）
    "生成AIエージェント",
    "セキュリティサービス",
    "セキュリティソリューション",
    "サイバー防御",
    "ランサム対策",
    "脅威インテリジェンス",
    "脆弱性対策",
    "情報システム",
    "基幹システム",
    "業務システム",
    "オープンソース",
    "MLOps",
    "LLMOps",
    "暗号化",
    "SSL証明書",
    "TLS1.3",
]

# 後方互換エイリアス（両方の union）。以前のコードが TECH_TREND_KEYWORDS を参照している場合のため残す
TECH_TREND_KEYWORDS: list[str] = HEALTHTECH_TECH_KEYWORDS + [
    kw for kw in GENERAL_TECH_KEYWORDS if kw not in HEALTHTECH_TECH_KEYWORDS
]

# 競合動向を示すキーワード（資金調達・IPO・提携・プロダクト動向など "動き" 系）
COMPETITOR_ACTION_KEYWORDS: list[str] = [
    # 資金調達
    "資金調達",
    "シリーズA",
    "シリーズB",
    "シリーズC",
    "シリーズD",
    "プレシリーズ",
    "調達",
    "出資",
    "増資",
    "第三者割当",
    # 上場・M&A
    "IPO",
    "上場",
    "東証",
    "グロース市場",
    "買収",
    "M&A",
    "TOB",
    "株式取得",
    "子会社化",
    "事業譲渡",
    "統合",
    "合併",
    # 提携
    "業務提携",
    "資本提携",
    "資本業務提携",
    "協業",
    "戦略的提携",
    "合弁",
    "ジョイントベンチャー",
    "パートナーシップ",
    # プロダクト動向
    "ローンチ",
    "リリース",
    "正式公開",
    "正式リリース",
    "ベータ版",
    "β版",
    "先行提供",
    "販売開始",
    "提供開始",
    "サービス開始",
    "新サービス",
    "新機能",
    # 実績系
    "導入事例",
    "採用事例",
    "導入実績",
    "実証実験",
    "PoC",
    "実装",
    "共同開発",
    # 認証・承認
    "薬事承認",
    "認証取得",
    "ISO取得",
    "FDA承認",
    "PMDA",
]

# カンファレンス・イベント系キーワード
CONFERENCE_KEYWORDS: list[str] = [
    # 一般的なイベント表現
    "カンファレンス",
    "コンファレンス",
    "サミット",
    "フォーラム",
    "シンポジウム",
    "学会",
    "セミナー",
    "ウェビナー",
    "ワークショップ",
    "ミートアップ",
    "勉強会",
    "講演",
    "登壇",
    "基調講演",
    "キーノート",
    # 形態
    "出展",
    "展示会",
    "開催",
    "参加募集",
    "参加者募集",
    "申し込み受付",
    # 具体的なヘルステック関連イベント名
    "Medical Japan",
    "HIMSS",
    "HLTH",
    "CES",
    "医療情報学会",
    "日本医療情報学会",
    "MEDISO",
    "Japan IT Week",
    "デジタルヘルスカンファレンス",
    "HealthTech Summit",
    "ヘルステックサミット",
    "メディカルジャパン",
    "医療DX展",
    "病院EXPO",
]


def _load_extra_keywords(env_key: str) -> list[str]:
    """.env で追加のキーワードを受け取る（カンマ区切り）。"""
    return [
        kw.strip()
        for kw in os.environ.get(env_key, "").split(",")
        if kw.strip()
    ]


# =============================================================================
# 医療DX 必須キーワード（Channel A 用の第3ゲート）
# =============================================================================
# Channel A (ヘルステック) は "医療×IT" 通過に加えて、以下のいずれかを含む記事のみ通す。
# これにより、矯正歯科/審美歯科/一般クリニックの日常ITネタ等、医療DXらしくない話題を排除する。
MEDICAL_DX_KEYWORDS: list[str] = [
    # 医療DX 直接表現
    "医療DX",
    "医療dx",
    "ヘルスケアDX",
    "ヘルステック",
    "医療デジタル",
    "クリニックDX",
    "薬局DX",
    "病院DX",
    # 医療情報システム / プラットフォーム
    "電子カルテ",
    "医事会計",
    "レセプト",
    "病院情報システム",
    "HIS",
    "PACS",
    "医療クラウド",
    "医療SaaS",
    "医療プラットフォーム",
    "医療データ基盤",
    "医療データ",
    "医療情報",
    # 標準規格・相互運用性
    "FHIR",
    "HL7",
    "DICOM",
    "SS-MIX",
    "相互運用性",
    "医療連携",
    "地域医療連携",
    "全国医療情報プラットフォーム",
    # 診療・患者向けデジタルサービス
    "オンライン診療",
    "遠隔医療",
    "遠隔診療",
    "AI問診",
    "問診票",
    "遠隔読影",
    "PHR",
    "EHR",
    # AI / 医療機器系
    "医療AI",
    "診断支援AI",
    "画像診断AI",
    "SaMD",
    "プログラム医療機器",
    "デジタル療法",
    "DTx",
    # 医療機関 BtoB 系
    "医療機関向け",
    "病院向け",
    "クリニック向け",
    "医師向け",
    "薬局向け",
]

HEALTHTECH_TECH_KEYWORDS.extend(_load_extra_keywords("HEALTHTECH_TECH_EXTRA_KEYWORDS"))
GENERAL_TECH_KEYWORDS.extend(_load_extra_keywords("GENERAL_TECH_EXTRA_KEYWORDS"))
MEDICAL_DX_KEYWORDS.extend(_load_extra_keywords("MEDICAL_DX_EXTRA_KEYWORDS"))

# 国・自治体の医療DX関連（通知・政策・周産期/産科とDXの交差など）。
# MEDICAL_DX 第3ゲートとヘルステック技術動向タグの双方に効かせる。
_GOVERNMENT_MEDICAL_DX_KEYWORDS: tuple[str, ...] = (
    "厚生労働省",
    "厚労省",
    "デジタル庁",
    "自治体",
    "都道府県",
    "市区町村",
    "地方自治体",
    "周産期医療",
    "産科医療",
)
for _kw in _GOVERNMENT_MEDICAL_DX_KEYWORDS:
    if _kw not in HEALTHTECH_TECH_KEYWORDS:
        HEALTHTECH_TECH_KEYWORDS.append(_kw)
    if _kw not in MEDICAL_DX_KEYWORDS:
        MEDICAL_DX_KEYWORDS.append(_kw)

# =============================================================================
# ヘルステック企業ホワイトリスト（Channel A 向け: 企業名含む記事は全ゲートをバイパス）
# =============================================================================
# これらの企業名がタイトル/本文に含まれる記事は、医療×IT / 医療DX ゲートをスキップして
# そのまま通す（EXCLUDE_KEYWORDS は引き続き適用）。
# 主要な医療DX/ヘルステック企業の資金調達・プロダクト動向を漏らさないため。
HEALTHTECH_COMPANY_ALLOWLIST: list[str] = [
    # プライマリケア / オンライン診療 / 問診
    "Ubie", "ユビー",
    "MICIN", "ミーシン",
    "メドレー",
    "カケハシ", "Kakehashi",
    "Linc'well", "リンクウェル",
    "ファストドクター", "Fast Doctor",
    "プラスメディ",
    "CLINICS", "メドレイ",
    # 電子カルテ / 病院/クリニック向けSaaS
    "ヘンリー",
    "エムスリー",
    "メドピア", "MedPeer",
    "DONUTS", "CLIUS",
    "NOBORI", "ノボリ",
    "カナミックネットワーク", "カナミック",
    "インテグリティ・ヘルスケア",
    # 医療AI / SaMD / 画像診断
    "CureApp", "キュア・アップ",
    "エルピクセル", "LPixel",
    "AIメディカルサービス",
    "プレシジョン",
    "Preferred Networks",
    "Holoeyes", "ホロアイズ",
    "Splink", "スプリンク",
    "アラヤ",
    "Aillis", "アイリス",
    # データ / 分析 / PHR
    "JMDC",
    "Welby", "ウェルビー",
    "カラダノート",
    "FRONTEO",
    # 薬局 DX
    "ファーマクラウド",
    "EPARKくすりの窓口",
    "メドピアファーマシー",
    # 介護DX
    "ソフィアメディ",
    "ウェルモ",
    # 総合ヘルステック
    "Dr.JOY", "ドクタージョイ",
    "アルム",
    "メドレジ",
    "3Hメディソリューション",
    # 病院/医療機関 DX プラットフォーマー
    "GaiXer",
    # 海外主要ヘルステック
    "Epic Systems",
    "Cerner",
    "Teladoc",
    "Doximity",
    "Headspace Health",
    "Flatiron Health",
    "Tempus AI",
]
HEALTHTECH_COMPANY_ALLOWLIST.extend(_load_extra_keywords("HEALTHTECH_COMPANY_EXTRA_ALLOWLIST"))

# Channel A 向けの優先 Google News クエリ（ヘルステック資金調達・動向を漏れなく拾う用）
# 取得記事は is_healthtech_priority=True が付与され、医療×IT / 医療DX ゲートをバイパスする。
DEFAULT_HEALTHTECH_PRIORITY_GOOGLE_NEWS_QUERIES: list[str] = [
    "医療DX 資金調達",
    "ヘルステック 資金調達",
    "ヘルスケア スタートアップ 資金調達",
    "医療AI 資金調達",
    "電子カルテ 資金調達",
    "オンライン診療 資金調達",
    "医療DX 提携",
    "医療DX 上場",
    "ヘルステック M&A",
    # 国・自治体の医療DXお知らせ・政策
    "厚生労働省 医療DX",
    "厚生労働省 電子カルテ",
    "自治体 医療DX",
    "デジタル庁 医療情報",
    "厚生労働省 オンライン資格確認",
]
_env_healthtech_priority_queries = [
    q.strip()
    for q in os.environ.get("HEALTHTECH_PRIORITY_GOOGLE_NEWS_QUERIES", "").split(",")
    if q.strip()
]
HEALTHTECH_PRIORITY_GOOGLE_NEWS_QUERIES: list[str] = (
    _env_healthtech_priority_queries
    or DEFAULT_HEALTHTECH_PRIORITY_GOOGLE_NEWS_QUERIES
)
TECH_TREND_KEYWORDS.extend(_load_extra_keywords("TECH_TREND_EXTRA_KEYWORDS"))
COMPETITOR_ACTION_KEYWORDS.extend(_load_extra_keywords("COMPETITOR_EXTRA_KEYWORDS"))
CONFERENCE_KEYWORDS.extend(_load_extra_keywords("CONFERENCE_EXTRA_KEYWORDS"))

# =============================================================================
# 一般IT（Channel B）用のソース設定
# =============================================================================
# デフォルトは PR TIMES の RSS のみ（品質・網羅のバランス）。Google News はオプション。
DEFAULT_GENERAL_TECH_PRTIMES_RSS_URLS: list[str] = [
    "https://prtimes.jp/index.rdf",
]
_env_general_tech_prtimes = [
    url.strip()
    for url in os.environ.get("GENERAL_TECH_PRTIMES_RSS_URLS", "").split(",")
    if url.strip()
]
GENERAL_TECH_PRTIMES_RSS_URLS: list[str] = (
    _env_general_tech_prtimes or DEFAULT_GENERAL_TECH_PRTIMES_RSS_URLS
)

# Google News（未設定時は空＝取得しない。必要なら .env でカンマ区切りクエリを指定）
DEFAULT_GENERAL_TECH_GOOGLE_NEWS_QUERIES: list[str] = []
_env_general_tech_queries = [
    q.strip()
    for q in os.environ.get("GENERAL_TECH_GOOGLE_NEWS_QUERIES", "").split(",")
    if q.strip()
]
# 環境変数が無いときだけデフォルト（空＝Google News は使わない）。
# キーがある場合は値が空でもそのまま採用し、Google を止めたいときに明示できる。
if "GENERAL_TECH_GOOGLE_NEWS_QUERIES" in os.environ:
    GENERAL_TECH_GOOGLE_NEWS_QUERIES = _env_general_tech_queries
else:
    GENERAL_TECH_GOOGLE_NEWS_QUERIES = list(DEFAULT_GENERAL_TECH_GOOGLE_NEWS_QUERIES)

# 追加の一般IT系 RSS（Publickey 等）。未指定時は空（PR TIMES のみ運用）
DEFAULT_GENERAL_TECH_RSS_URLS: list[str] = []
_env_general_tech_rss = [
    url.strip()
    for url in os.environ.get("GENERAL_TECH_RSS_URLS", "").split(",")
    if url.strip()
]
GENERAL_TECH_RSS_URLS: list[str] = (
    _env_general_tech_rss or DEFAULT_GENERAL_TECH_RSS_URLS
)


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

    # 審美・矯正歯科（医療DXとは無関係な一般/美容歯科治療）
    "矯正歯科",
    "歯科矯正",
    "歯列矯正",
    "インビザライン",
    "マウスピース矯正",
    "マウスピース型矯正",
    "マウスピース型カスタムメイド矯正",
    "審美歯科",
    "美容歯科",
    "ホワイトニング",
    "インプラント治療",
    "インプラント手術",
    "セラミック治療",

    # 動物医療・ペット関連（人医療向けではない）
    "動物病院",
    "獣医",
    "獣医師",
    "動物医療",
    "ペット",
    "ペット医療",
    "ペット病院",
    "動物クリニック",
    "獣医学",
    "動物診療",
    "動物治療",
    "ペット診療",
    "ペット治療",
    "ワンちゃん",
    "猫",
    "犬",
    "ペット向け",
    "動物向け",

    # 物流中心の話題（医療提供とは無関係）。「サプライチェーン」単体は除外しない
    # （ソフトウェアサプライチェーン / サプライチェーン攻撃 等のセキュリティ記事を誤落とさないため）
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
    
    # 暗号資産・Web3（一般ITチャンネルのノイズになりやすい）
    "DeFi",
    "NFT",
    "仮想通貨",
    "暗号資産",
    "Web3",
    "トークンセール",

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

# カテゴリ指定モード時の投稿件数上限（all モードは MAX_ARTICLES_PER_POST を使う）
MAX_ARTICLES_PER_CATEGORY: int = int(os.environ.get("MAX_ARTICLES_PER_CATEGORY", "8"))

# RSS 取得タイムアウト（秒）
FETCH_TIMEOUT: int = 10

# 取得対象とする時間範囲（時間単位）。デフォルトは直近24時間（前回実行以降の記事を取得）。
TIME_RANGE_HOURS: int = int(os.environ.get("TIME_RANGE_HOURS", "24"))

# 配信済みURLの保存先
DATA_DIR = Path("data")
SENT_URLS_PATH = DATA_DIR / "sent_urls.json"
# ログファイル（環境変数 LOG_FILE で指定。未指定なら標準出力のみ）
LOG_FILE = os.environ.get("LOG_FILE") or None
