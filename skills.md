# slack-news 設計スキル（Clean Architecture）

このリポジトリでは、**依存の向きを内側（ドメイン）に向ける** [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) を意識する。

## レイヤと責務

| レイヤ | ディレクトリ | 責務 |
|--------|----------------|------|
| **Domain** | `slack_news/domain/` | エンティティ（`Article`）、ソース表示名など純粋な知識。外部I/O・フレームワークに依存しない。 |
| **Application** | `slack_news/application/` | ユースケース（取得→加工→配信のオーケストレーション）、記事のドメインに近い加工（重複除去・時間窓・ソート）。 |
| **Presentation** | `slack_news/presentation/` | Slack 向けの表示整形（メッセージ組み立て）。 |
| **Interfaces（Ports）** | `slack_news/interfaces/` | `Protocol` で外向き依存を抽象化（通知・送信済みURL永続化など）。 |
| **Infrastructure** | `slack_news/infrastructure/` | Ports の具象実装（Webhook・ファイルJSON 等）。既存の `notifier` / `storage` を薄くラップしてよい。 |

**設定・外部ソースの取得**（`config.py`, `fetcher.py`, `extrasources.py` 等）は当面 **Infrastructure 相当**としてルートに置き、ユースケースから呼ぶ。段階的に `slack_news/infrastructure/` へ寄せてよい。

## 依存ルール

1. **Domain** は他レイヤを import しない。
2. **Application** は Domain と Ports（`Protocol`）に依存してよい。具象の `requests` / ファイルパス実装に直接依存しない（コンストラクタ注入またはファクトリで渡す）。
3. **Infrastructure** は Ports を実装し、必要なら既存モジュール（`notifier`, `storage`）に依存する。
4. **Presentation** は Domain（`Article`）と表示用の定数（カテゴリラベル等）に依存してよい。

## エントリポイント

- `main.py` は **CLI とロギング設定のみ**。ユースケースの組み立て（アダプタの注入）にとどめる。

## 記事フィルタの段階（`filter.py`）

方針は **拾い上げ（包含）を主**にし、拒否は **任意の安全弁**に限定する。

| 段階 | 内容 |
|------|------|
| Stage 0 | `exclude_domains` で URL ドメイン除外 |
| Stage 1 | **イベント以外**に、`EXCLUDE_KEYWORDS` を照合（デフォルトは空。運用では `EXCLUDE_EXTRA_KEYWORDS` のみ）。タイトル＋概要、URL 除去後 |
| Stage 2 | ソース別の**包含**: connpass イベント、優先 Google（Channel A 時は **医療 AND (IT OR 医療DX) OR 企業WL**、それ以外は **医療 OR 企業WL**）、企業WL、一般ITキーワード、通常の医療×IT（＋Channel A 時は医療DX ゲート） |

カテゴリタグ付け（競合・イベント等）は `filter_articles` の**後**の `categorizer` で行う。

## 変更時のチェックリスト

- 新しい外部サービスを足すときは **Port を先に**定義し、Infrastructure で実装する。
- ビジネスルール（何を「同じニュース」とみなすか等）は **Application / Domain 側**に置き、Slack の文面詳細は **Presentation** に置く。
- `config` の巨大辞書は「設定の読み込み」として許容し、**分岐ロジックを増やしすぎない**（ロジックはユースケースへ）。
