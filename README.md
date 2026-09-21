# ai-cli-npm

公開データで「**npm のダウンロード数で、AI コーディング CLI（Claude Code / Codex CLI / Gemini CLI）の人気を比べてよいか**」を確かめるプロジェクト。どのツールが多く使われているかは主張しない。

状態: **取得と判定まで完了（2026-09-21）。** 撤退基準 A・B は通過、C（記事化）を満たす。記事は未公開。

| 文書 | 内容 |
|---|---|
| [docs/roadmap.md](docs/roadmap.md) | フェーズ一覧、全体方針、やらないこと |
| [docs/decisions/0001-question-and-criteria.md](docs/decisions/0001-question-and-criteria.md) | 問いの採用、予測 P1a・P1b・P2・P3、撤退基準 A・B・C の凍結、見たもの |
| [docs/results.md](docs/results.md) | 結果（A・B、P1a・P1b・P2・P3、記述）。数値は `docs/data/` |
| [docs/decisions/0002-verdicts.md](docs/decisions/0002-verdicts.md) | 判定、時刻の記録、事前登録からの逸脱 |
| [docs/posthoc.md](docs/posthoc.md) | 事後の参考表（事前登録に無い集計。判定には使わない） |
| [docs/sources.md](docs/sources.md) | 確認済みの事実と出典（API の仕様、3 ツールの配布のしかた、npm 上のパッケージ構造、利用条件、先行） |

## 結果の要点（2026-09-21 取得。詳細は docs/results.md）

- **P1a 支持**: `@openai/codex` の直近 7 日のダウンロード数の **51.5%** は、プラットフォーム別バイナリの版（`0.155.1-linux-x64` など）に付いている。同じ集計で Claude Code と Gemini CLI は 0%
- **P1b 支持**: 0.99.0（2026-02-11）の前後で Codex CLI の日次の中央値は 4.7 倍（他 2 つは 1.1〜1.4 倍）。ただし二重計上だけなら最大 2 倍で、需要増との切り分けはできない
- **P2**: 事前登録の指標では Codex CLI 1.22・Gemini CLI 1.40 で「跳ねる」、Claude Code は判定不能。指標がトレンドを除いておらず、判定は弱い（事後の確認では 1.09 と 1.20）
- **P3**: npm と Homebrew の順位は、30 日・90 日では一致（予測は外れ）、365 日では不一致
- ダウンロード数は利用者数ではない。どのツールが多く使われているかは、この結果からは言えない

## 再現のしかた

```
python scripts/test_synthetic.py   # 答えの分かっている合成データで集計を検証（75 項目）
python scripts/fetch.py            # 40 リクエスト、1 リクエスト/秒以下。data/raw/<取得日>/ に保存
python scripts/analyze.py          # 判定を表示し、docs/data/ に集計を書く
python scripts/posthoc.py          # 事後の参考表
```

標準ライブラリだけで動く（Python 3.14.3 で確認）。

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
