# 医療×ITニュース自動配信システム

医療×IT領域のニュースを複数ソースから取得し、Slack の **2チャンネル** に1日2回投稿するためのツールです。
朝と夜でチャンネル（Webhook）を切り替え、役割を分担させます。

## 配信チャンネルと時間帯

| 時刻 | チャンネル | カテゴリ | 目的 |
|------|-----------|----------|------|
| 09:00 | **Channel A** (`SLACK_WEBHOOK_URL_A`) | `competitor` — 競合動向 | 資金調達・IPO・M&A・業務提携・プロダクトリリースなど |
| 21:00 | **Channel B** (`SLACK_WEBHOOK_URL_B`) | `tech` + `conference` | ヘルステックIT技術動向とカンファレンス/ITイベントをまとめて |

### 記事分類とフィルタの二系統

- **ニュース記事**（PR TIMES / 医療テックニュース / ヘルステックウォッチ / Google News）
  - 一次フィルタ: 「医療キーワード × ITキーワードの両方を含む記事」
  - カテゴリ分類: `TECH_TREND_KEYWORDS` / `COMPETITOR_ACTION_KEYWORDS` / `CONFERENCE_KEYWORDS` でタグ付け
- **イベント情報**（connpass Atom）
  - 一次フィルタはバイパス（医療限定しない）
  - 代わりに「**開催日時が今から7日以内** かつ **開催場所がオンラインまたは広島**」で絞り込み
  - 自動的に `conference` カテゴリとして扱う（Channel B 夜配信対象）
  - `EVENT_LOCATIONS` / `EVENT_LOOKAHEAD_DAYS` で挙動を調整可能

## 機能概要

- **複数ソースからの記事取得**
  - PR TIMES（RSSフィード）
  - 医療テックニュース（Webスクレイピング）
  - ヘルステックウォッチ（Webスクレイピング）
  - Google News（RSSフィード）
  - connpass（Atomフィード／イベント情報、医療限定しない）

- **記事のフィルタリング（ニュース側）**
  - タイトル/概要に「医療系キーワード」かつ「IT系キーワード」を含む記事のみ抽出
  - 除外キーワードに該当する記事は除外（美容整形、食品関連、EC関連など）

- **イベントフィルタ（connpass側）**
  - 開催日時が「今から N 日以内」(`EVENT_LOOKAHEAD_DAYS`、デフォルト 7日)
  - 開催場所が `EVENT_LOCATIONS`（デフォルト: `オンライン, 広島`）のいずれかを含む
  - 自動的に `conference` カテゴリ扱い、医療×IT フィルタをバイパス

- **カテゴリ分類**
  - ニュースは通過後に `TECH_TREND_KEYWORDS` / `COMPETITOR_ACTION_KEYWORDS` / `CONFERENCE_KEYWORDS` で分類（複数該当可）
  - イベントは `conference` 固定

- **記事の概要（description）取得**
  - 各ソースから記事ページにアクセスして適切なdescriptionを取得
  - meta description、og:description、または記事本文から抽出

- **重複除去**
  - URLとタイトルベースで重複を除去
  - PR TIMESを最優先として、優先度の高いソースの記事を残す

- **過去送信済みURL管理**
  - JSONで送信済みURLを保持し、重複送信を防止
  - 同じ日の別時間帯でも重複を防ぐ

- **Slack投稿**
  - 抽出記事をソース別にグループ化して1つのメッセージにまとめて投稿
  - 件数が多い場合は上限（デフォルト20件）までに制限
  - 記事がない場合は「新着なし」を送信

## セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/Suisan-neki/slack-news-.git
cd slack-news-
```

### 2. 環境変数の設定

`.env` ファイルを作成し、以下の環境変数を設定します：

```bash
# デフォルト（--category=all や --webhook 未指定のフォールバック）
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Channel A（競合動向・朝配信）
SLACK_WEBHOOK_URL_A=https://hooks.slack.com/services/YOUR/WEBHOOK/FOR_COMPETITOR

# Channel B（IT技術動向 + カンファレンス/イベント・夜配信）
SLACK_WEBHOOK_URL_B=https://hooks.slack.com/services/YOUR/WEBHOOK/FOR_TECH_AND_CONF

PRTIMES_RSS_URLS=https://prtimes.jp/index.rdf
LOG_FILE=/path/to/cron.log
```

**環境変数の説明：**
- `SLACK_WEBHOOK_URL`: デフォルト Webhook（`--category=all` や `--webhook default` 時）
- `SLACK_WEBHOOK_URL_A`: Channel A（`--webhook a`、競合動向）。未指定時は `SLACK_WEBHOOK_URL` にフォールバック
- `SLACK_WEBHOOK_URL_B`: Channel B（`--webhook b`、IT技術動向+カンファレンス）。未指定時は `SLACK_WEBHOOK_URL` にフォールバック
- `PRTIMES_RSS_URLS`: PR TIMESのRSS URLをカンマ区切りで指定（デフォルト: `https://prtimes.jp/index.rdf`）
- `EXTRA_SOURCES`: 追加サイトをスクレイピングする場合に指定（カンマ区切り）
  - `medicaltech`: 医療テックニュース
  - `htwatch`: ヘルステックウォッチ
  - `googlenews` または `google-news`: Google News（デフォルトでは除外）
  - `connpass`: connpass 新着イベント Atom フィード（医療限定しない）
  - **デフォルト**: `medicaltech,htwatch,connpass`
- `EVENT_LOCATIONS`: connpass イベントを拾う開催場所キーワード（カンマ区切り、デフォルト: `オンライン,広島`）
- `EVENT_LOOKAHEAD_DAYS`: connpass イベントを何日先まで拾うか（デフォルト: `7`）
- `LOG_FILE`: ログをファイルに出力したい場合のパス（オプション）
- `EXCLUDE_EXTRA_KEYWORDS`: 除外キーワードをカンマ区切りで追加する（例: `求人,採用,転職`）
- `EXCLUDE_DOMAINS`: 除外したいドメインをカンマ区切りで指定する（例: `example.com,foo.jp`）
- `TIME_RANGE_HOURS`: 取得対象とする時間範囲（時間）。デフォルトは直近24時間を集計して送信します。
- `TECH_TREND_EXTRA_KEYWORDS`: IT技術動向カテゴリの追加キーワード（カンマ区切り）
- `COMPETITOR_EXTRA_KEYWORDS`: 競合動向カテゴリの追加キーワード（カンマ区切り）
- `CONFERENCE_EXTRA_KEYWORDS`: カンファレンス・イベントカテゴリの追加キーワード（カンマ区切り）
- `MAX_ARTICLES_PER_CATEGORY`: カテゴリ指定モード時の上限件数（デフォルト: 8）
- `SSL_UNVERIFIED_DOMAINS`: SSL 検証を緩めるドメインをカンマ区切りで指定（デフォルト: `ht-watch.com`）。サーバ側の証明書設定不備で hostname mismatch になるサイトにだけ適用される安全弁

### 3. Python環境

- Python 3.9+ が必要（標準ライブラリのみ使用、外部依存なし）

## 使い方

### 手動実行（テスト用）

```bash
# Slack送信なしの確認（dry-run）
python3 main.py --dry-run --verbose

# 手動実行モード（送信済みURLチェックをスキップ、5件に制限、Google News除外）
python3 main.py --manual --verbose

# 通常実行（実際にSlackに送信）
python3 main.py
```

**コマンドラインオプション：**
- `--dry-run`: Slack送信せず標準出力にメッセージを表示
- `--manual`: 手動実行モード（送信済みURLチェックをスキップ、5件に制限、Google News除外）
- `--verbose`: 詳細ログを出力
- `--storage-path PATH`: 配信済みURLを保存するJSONのパス（デフォルト: `data/sent_urls.json`）
- `--max-items N`: 1回の投稿に含める最大件数
- `--category` : 配信カテゴリ（カンマ区切りで複数指定可、デフォルト: `all`）
  - `tech`: IT技術動向のみ
  - `competitor`: 競合動向のみ
  - `conference`: カンファレンス・イベントのみ
  - `tech,conference` のように複数指定可。複数指定時はカテゴリ別にセクション化される
  - `all`: 従来通りソース別まとめで全件表示
- `--webhook {default,a,b}`: 配信先 Slack Webhook を選択（デフォルト: `default`）
  - `a`: `SLACK_WEBHOOK_URL_A`（競合動向/朝）
  - `b`: `SLACK_WEBHOOK_URL_B`（IT技術動向+カンファレンス/夜）
  - `default`: `SLACK_WEBHOOK_URL`

### カテゴリ別テスト（dry-run）

```bash
# Channel A（競合動向・朝配信）の出力確認
python3 main.py --dry-run --category competitor --webhook a

# Channel B（IT技術動向+カンファレンス・夜配信）の出力確認
python3 main.py --dry-run --category tech,conference --webhook b

# 個別カテゴリで出力確認
python3 main.py --dry-run --category tech --manual
python3 main.py --dry-run --category conference --manual
```

## 定時実行と重複防止

### 定時実行方法

#### 方法1: GitHub Actions（推奨・パソコンが起動していなくても動作）

1. **GitHubリポジトリのSecretsに環境変数を設定**
   - リポジトリの Settings → Secrets and variables → Actions に移動
   - 以下のSecretsを追加：
     - `SLACK_WEBHOOK_URL_A`: Channel A（朝・ヘルステック系）用 Webhook（必須）
     - `SLACK_WEBHOOK_URL_B`: Channel B（夜・一般IT+イベント）用 Webhook（必須）
     - `SLACK_WEBHOOK_URL`: 未設定時のフォールバック用（任意。`main.py` の `--webhook default` 用）
     - `PRTIMES_RSS_URLS`: PR TIMES の RSS URL（任意。未指定時は `config.py` のデフォルト）
     - `EXCLUDE_EXTRA_KEYWORDS`: 除外キーワード（任意、カンマ区切り）
     - `EXCLUDE_DOMAINS`: 除外ドメイン（任意、カンマ区切り）
     - `TIME_RANGE_HOURS`: 取得する過去時間（任意）
     - その他 `config.py` で参照する任意の Secret（`HEALTHTECH_PRIORITY_GOOGLE_NEWS_QUERIES` 等）は必要に応じて

   **注意:** ワークフロー内で朝用・夜用に `EXTRA_SOURCES` を切り替えているため、リポジトリの `EXTRA_SOURCES` Secret は使いません（設定してもこのジョブでは参照しません）。

2. **ワークフローファイルの確認**
   - `.github/workflows/scheduled-news.yml` が正しくコミットされているか確認
   - スケジュール: **JST 9:05 頃**（Channel A）、**JST 21:05 頃**（Channel B）。UTC の `cron` で指定（GitHub は UTC 基準）

3. **動作確認**
   - GitHubリポジトリの Actions タブで実行状況を確認
   - 手動実行: Actions → 本ワークフロー → Run workflow → `channel` で `a` / `b` / `both` を選択

**メリット:**
- パソコンが起動していなくても動作
- 無料で利用可能
- 実行ログがGitHub上で確認できる

#### 方法2: macOS LaunchAgent（ローカル実行）

コードを更新した後は、LaunchAgentを再ロードして最新コードを使うようにします：

```bash
# 15時の plist は廃止。旧 15時plistがロード済みの場合は先に unload しておく
launchctl unload ~/Library/LaunchAgents/com.suisan.slack-news-15.plist 2>/dev/null || true

launchctl unload ~/Library/LaunchAgents/com.suisan.slack-news-09.plist
launchctl unload ~/Library/LaunchAgents/com.suisan.slack-news-21.plist
launchctl load ~/Library/LaunchAgents/com.suisan.slack-news-09.plist
launchctl load ~/Library/LaunchAgents/com.suisan.slack-news-21.plist
```

- `com.suisan.slack-news-09.plist`: 09:00 に `--category competitor,healthtech,conference --webhook a`
- `com.suisan.slack-news-21.plist`: 21:00 に `--category general_tech,conference --webhook b`

**注意:** パソコンが起動していてログインしている場合のみ動作します。スリープ中や電源オフ時は実行されません。

### 手動送信と定時送信の違い

#### 手動送信（本番と分けて実行）

```bash
python3 main.py --manual --verbose
```

- Google Newsを除外
- 5件に制限
- 送信済みチェックをスキップ
- 送信したURLは `data/sent_urls.json` に記録される
- その後の定時実行では同じ記事を再送しない

#### 定時送信

```bash
python3 main.py
```

- 直近24時間分から未送信のものだけ送信
- 手動で送ったものも含め、`data/sent_urls.json` にあるURLは再送されない
- 同じ日の別時間帯でも重複を防ぐ

### 確認ポイント

1. **`data/sent_urls.json` が消えないように確認**
   - パスと権限が正しく設定されているか確認
   - ファイルが存在し、書き込み可能であることを確認

2. **環境変数の確認**
   - `SLACK_WEBHOOK_URL` 環境変数が設定されているか確認

3. **ログの確認**
   - `cron.log` または `LOG_FILE` で以下のログを確認：
     - `Loaded X sent URLs` - 送信済みURLの読み込み数
     - `New articles: Y` - 新規記事数
   - これらのログで重複抑止の動作が確認できます

この状態で、手動配信済みの記事は次の定時配信から除外され、定時配信内でも同じ時間帯で重複は出ません。

## ディレクトリ構成

```
slack-news-/
├── main.py              # 実行エントリーポイント
├── config.py            # 設定（RSS/キーワード/Slack）
├── fetcher.py           # RSSフィード取得と記事ページからのdescription取得
├── filter.py            # キーワードフィルタリング
├── notifier.py          # Slack投稿
├── storage.py           # 配信済みURL管理
├── extrasources.py      # 追加ソース（医療テックニュース、ヘルステックウォッチ、Google News、connpass）
├── categorizer.py       # 3カテゴリ分類（IT技術/競合/カンファレンス）
├── httpclient.py        # HTTP取得共通ユーティリティ（特定ドメインのSSL検証緩和）
├── data/
│   └── sent_urls.json   # 配信済みURLの保存先（自動生成）
└── README.md            # このファイル
```

## キーワード設定

### 医療系キーワード

`config.py` の `MEDICAL_KEYWORDS` で定義されています。例：
- 医療、ヘルスケア、診療、病院、クリニック
- 介護、介護施設、薬局、医師
- 医療DX、デジタルヘルス、遠隔医療、オンライン診療
- など

### IT系キーワード

`config.py` の `IT_KEYWORDS` で定義されています。例：
- AI、IT、DX、デジタル、システム
- クラウド、SaaS、アプリ、IoT
- データ、分析、解析、プラットフォーム
- など

### 除外キーワード

`config.py` の `EXCLUDE_KEYWORDS` で定義されています。以下のような記事は除外されます：
- 美容整形、エステ、化粧品、フィットネス
- 健康食品、レストラン、グルメ
- 不動産、マンション、投資
- EC、クラウドファンディング、ゲーム
- など

## 動作の流れ

1. **記事取得**
   - RSSフィードから記事を取得（PR TIMES、Google News）
   - Webスクレイピングで記事を取得（医療テックニュース、ヘルステックウォッチ）

2. **description取得**
   - 各記事のページにアクセスしてdescriptionを取得
   - meta description、og:description、または記事本文から抽出

3. **フィルタリング**
   - 医療系キーワードとIT系キーワードの両方を含む記事のみ抽出
   - 除外キーワードに該当する記事を除外

4. **重複除去**
   - URLとタイトルベースで重複を除去
   - 優先度の高いソースの記事を残す

5. **送信済みチェック**
   - 過去に送信したURLをチェック
   - 未送信の記事のみを抽出

6. **Slack投稿**
   - ソース別にグループ化してメッセージを作成
   - Slack Incoming Webhook に投稿

## トラブルシューティング

### ログの確認

```bash
# ログファイルを確認
tail -f cron.log

# エラーのみ確認
grep ERROR cron.log
```

### 手動実行でテスト

```bash
# dry-runモードで動作確認
python3 main.py --dry-run --verbose

# 手動実行モードで実際にSlackに送信（5件に制限）
python3 main.py --manual --verbose
```


## ライセンス

このプロジェクトのライセンス情報はリポジトリを確認してください。

## 更新履歴

- 2025-11-28: 全媒体でdescription取得機能を実装、除外キーワードを大幅に追加
- 複数ソース対応（医療テックニュース、ヘルステックウォッチ、Google News）
- RSS 1.0 (RDF)形式に対応
- 重複除去機能の改善
