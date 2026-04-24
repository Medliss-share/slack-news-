# 医療×ITニュースを Slack に送るツール

このツールは、複数のソースから記事を取得して、キーワードで絞り込んだうえで、Slack の Incoming Webhook に投稿します。朝用と夜用の **2つの Webhook** に分けて送ることもできます。

## 配信の目安

| 時間帯の例 | Webhook の環境変数 | 想定している内容 |
|------------|-------------------|------------------|
| 朝（例: 9時） | `SLACK_WEBHOOK_URL_A` | 競合動向・ヘルステック技術・会議系（`--webhook a`） |
| 夜（例: 21時） | `SLACK_WEBHOOK_URL_B` | 一般IT・イベント（`--webhook b`）。一般ITの主な取得元は PR TIMES |

細かいキーワードや除外語、RSS の URL は **`config.py`** に書かれています。環境変数で上書きできる項目も、同じファイルのコメントと変数名を参照してください。

## 必要なもの

- Python 3.9 以上（標準ライブラリのみで動きます）
- Slack の Incoming Webhook の URL（チャンネルごとに 1 本ずつ用意する場合は、A 用と B 用の 2 本）

## セットアップ

リポジトリを取得したあと、ルートに `.env` を置いて、少なくとも次の変数を設定します。

```bash
SLACK_WEBHOOK_URL_A=https://hooks.slack.com/services/.../.../...
SLACK_WEBHOOK_URL_B=https://hooks.slack.com/services/.../.../...
# どちらか一方だけを使うときのための共通先（任意）
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/.../.../...
```

PR TIMES の RSS や追加ソースの指定など、その他の変数は **`config.py` の先頭付近**と **`.env.example`** にまとまっています。

## 実行例

```bash
# 送信せずに内容だけ確認する
python3 main.py --dry-run --verbose --category competitor,healthtech,conference --webhook a

python3 main.py --dry-run --verbose --category general_tech,conference --webhook b

# 実際に Slack へ送る（定時実行や cron で呼ぶ想定）
python3 main.py --verbose --category competitor,healthtech,conference --webhook a
```

`--category` には `healthtech`（ヘルステック技術動向）・`general_tech`（一般IT）・`competitor`（競合）・`conference`（イベント）などを、カンマ区切りで複数指定できます。`tech` は `healthtech` の別名として扱われます。

`--manual` を付けると、送信済み URL のチェックをせずに最大 5 件まで送るテスト向けの動きになります。

## 定時実行

**GitHub Actions** を使う場合は、`.github/workflows/scheduled-news.yml` が朝と夜のどちらのジョブかに応じて `main.py` の引数と `EXTRA_SOURCES` を切り替えます。リポジトリの **Settings → Secrets and variables → Actions** に、`SLACK_WEBHOOK_URL_A` と `SLACK_WEBHOOK_URL_B` を登録してください。

**Mac で launchd を使う場合**は、リポジトリ内の `com.suisan.slack-news-09.plist`（朝）と `com.suisan.slack-news-21.plist`（夜）の `ProgramArguments` を、自分のパスに合わせてから `launchctl load` してください。

## 主要なファイル

| ファイル | 役割 |
|----------|------|
| `main.py` | 全体の処理の入口 |
| `config.py` | キーワード・RSS・Webhook などの設定 |
| `fetcher.py` | RSS の取得 |
| `filter.py` | キーワードによるフィルタ |
| `categorizer.py` | カテゴリの付け替え |
| `extrasources.py` | PR TIMES 以外の追加取得（Google News、connpass など） |
| `notifier.py` | Slack への投稿 |
| `storage.py` | 送信済み URL の保存（既定では `data/sent_urls.json`） |
