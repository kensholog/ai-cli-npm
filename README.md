# ai-cli-npm

公開データで「**npm のダウンロード数で、AI コーディング CLI（Claude Code / Codex CLI / Gemini CLI）の人気を比べてよいか**」を確かめるプロジェクト。どのツールが多く使われているかは主張しない。

状態: **フェーズ 0 通過、予測と撤退基準を凍結（2026-09-21）。ダウンロード数の値はまだ取得していない。**

| 文書 | 内容 |
|---|---|
| [docs/roadmap.md](docs/roadmap.md) | フェーズ一覧、全体方針、やらないこと |
| [docs/decisions/0001-question-and-criteria.md](docs/decisions/0001-question-and-criteria.md) | 問いの採用、予測 P1a・P1b・P2・P3、撤退基準 A・B・C の凍結、見たもの |
| [docs/sources.md](docs/sources.md) | 確認済みの事実と出典（API の仕様、3 ツールの配布のしかた、npm 上のパッケージ構造、利用条件、先行） |

## なぜ比べられないかもしれないのか（フェーズ 0 で分かったこと）

- Claude Code の推奨はネイティブインストーラーで、npm は代替手段。ネイティブ版の自動更新は npm を通らない
- Codex CLI は 2026-02-11（0.99.0）から、プラットフォーム別のバイナリを**同じパッケージ名の別バージョン**として配っている。1 回のインストールが 2 回のダウンロードとして数えられている可能性がある
- 安定版のリリース頻度が違う（Claude Code は月 20〜35 回、Codex CLI は月 7〜17 回、Gemini CLI は週 1 回が基本）。自動更新があれば、リリースのたびに既存の利用者ぶんが数えられる

## データの扱い

- npm の公式 API（ダウンロード数・レジストリ）と Homebrew の公式 analytics だけを使う。1 リクエスト/秒以下、全部で数十回
- 生データ（`data/`）はコミットしない。公開するのは集計と図だけ

## 作り方（AI の利用について）

分析の設計案・コード・データ取得・集計・図・記事の下書きには Claude Code（Anthropic）を使っています。**比較対象に Claude Code 自身が含まれます。** 問いと判定基準の決定、公開の判断、内容の最終確認は筆者（kensholog）が行い、予測と閾値はデータを見る前にコミットで固定しています（`docs/decisions/`）。数値と事実には出典 URL と確認日を付け、未確認のものは「未確認」と書いています。

- 検証の経緯・備忘は非公開の別リポジトリにある（`ideas/` は junction で、ここには置かない）
- 前の題材: [zenn-trend](https://github.com/kensholog/zenn-trend)、[carry-assets](https://github.com/kensholog/carry-assets)、[meccha-chameleon](https://github.com/kensholog/meccha-chameleon)
