# 確認済みの事実と出典

凡例: ✅ 一次情報を自分で確認 / 🔶 WebFetch・検索の要約で確認 / ❌ 未確認。確認日はすべて 2026-09-21（「取得後」と書いた行は、値を取得した後に確認したもの）。

## データの仕様

| 項目 | 内容 | 出典 |
|---|---|---|
| npm の日次ダウンロード数 | `GET https://api.npmjs.org/downloads/range/{開始}:{終了}/{package}`。日は UTC。1 回の問い合わせは最大 18 か月、最古は 2015-01-10。スコープつきパッケージは point / range で使えるが、一括（bulk）では使えない。3 パッケージとも 2025-01-01〜2026-06-30 の 546 日分が返ることを確認（✅ 日数と日付だけ） | 🔶 https://github.com/npm/registry/blob/main/docs/download-counts.md |
| 版別のダウンロード数 | `GET https://api.npmjs.org/versions/{package}/last-week`。「only available for the previous 7 days」。`@openai%2Fcodex` で 4,324 版のキーが返り、うち 3,631 がプラットフォーム接尾辞つき（✅ キー名と件数だけ） | 🔶 同上 |
| 「1 ダウンロード」の定義 | npm 公式ブログ「numeric precision matters: how npm download counts work」（2014-07-22、@seldo）: ダウンロード数は「the number of HTTP 200 responses we served that were tarball files」（tarball を 1 つ返すごとに 1 回）。自動ビルドサーバー、ミラー、全パッケージを取得するロボットを含み、パッケージの利用者数とは別物だと明言している。1 日 50 回を超えないとノイズと区別できない、という目安も示す。新しい版を公開するとミラーが取りに来るので一時的に増える、とも書いている（取得後） | ✅ https://blog.npmjs.org/post/92574016600/numeric-precision-matters-how-npm-download-counts-work.html （WebFetch の要約のあと、curl で取得した本文で引用の文言を確認） |
| 集計のタイミング | 1 日 1 回、UTC の 0 時を過ぎたころに前日ぶんのログを集計してデータベースに入れる、と説明している（取得後） | 🔶 https://github.com/npm/registry/blob/main/docs/download-counts.md |
| 版の公開時刻 | `GET https://registry.npmjs.org/{package}` の `time`（版 → ISO 時刻）と `versions[版].optionalDependencies` | ✅ |
| Homebrew の install 数 | `https://formulae.brew.sh/api/analytics/{install,cask-install}/{homebrew-core,homebrew-cask}/{30d,90d,365d}.json`。`install` は依存としての導入を含み、`install-on-request` は明示的な導入だけ。JSON の形は `{"start_date", "end_date", "formulae": {名前: [{"formula" か "cask": "名前 [オプション]", "count": "1,234"}, …]}}` で、`gemini-cli --HEAD` のようなオプション違いが別の行になる（✅ 取得後、実データで確認） | 🔶 https://formulae.brew.sh/docs/api/ |

## 配布のしかた

| ツール | 内容 | 出典 |
|---|---|---|
| Claude Code | 推奨は Native Install（`curl -fsSL https://claude.ai/install.sh \| bash`）。Homebrew cask（`claude-code` は stable、`claude-code@latest` は latest）、WinGet、apt・dnf・apk。npm は「Advanced installation options」の節。「Native installations automatically update in the background」「Homebrew installations do not auto-update」。npm について「The npm package installs the same native binary as the standalone installer. npm pulls the binary in through a per-platform optional dependency such as `@anthropic-ai/claude-code-darwin-arm64`」、「If an npm global install can't auto-update because the npm global directory isn't writable, Claude Code shows a one-time notice」 | ✅ https://code.claude.com/docs/en/setup （全文） |
| Codex CLI | README の先頭はシェルスクリプト（`curl -fsSL https://chatgpt.com/codex/install.sh \| sh`）。ほかに `npm install -g @openai/codex`、`brew install --cask codex`、GitHub Releases のバイナリ。自動更新の記載なし | 🔶 https://github.com/openai/codex |
| Gemini CLI | `npx @google/gemini-cli`、`npm install -g @google/gemini-cli`、`brew install gemini-cli`、MacPorts。安定版は毎週火曜 20:00 UTC、preview は毎週火曜 23:59 UTC、nightly は毎日 00:00 UTC。自動更新の記載なし | 🔶 https://github.com/google-gemini/gemini-cli |

## npm 上のパッケージの構造（✅ レジストリのメタデータ）

| パッケージ | 版 | プラットフォーム別バイナリ |
|---|---|---|
| `@anthropic-ai/claude-code` | 525 版（2025-02-24〜2026-09-19、すべて安定版）。dist-tags: latest / next / stable。安定版は月 20〜35 回 | optionalDependencies に別名のパッケージ 8 個（`@anthropic-ai/claude-code-{darwin,linux,win32}-…`、linux は musl 版あり）。`@anthropic-ai/claude-code-linux-x64` の作成日は 2026-04-13。それ以前の optionalDependencies は `@img/sharp-*` |
| `@openai/codex` | 4,672 版（安定版 188、2025-04-16〜2026-09-21）。dist-tags にプラットフォーム別のタグがある。安定版は月 7〜17 回 | 0.99.0（2026-02-11 公開）から、optionalDependencies が `@openai/codex-linux-x64` → `npm:@openai/codex@0.99.0-linux-x64` の形（**同じパッケージ名の別バージョンへの別名**）。`@openai/codex-linux-x64` という独立パッケージは存在しない（404） |
| `@google/gemini-cli` | 755 版（安定版 197、2025-06-25〜2026-09-21）。dist-tags: latest / preview / nightly ほか | プラットフォーム別バイナリなし（optionalDependencies は node-pty と keytar） |

## Homebrew 上の 3 ツール（✅ 取得後。`formulae.brew.sh/api/{cask,formula}/….json` と homebrew-core の履歴）

| 名前 | 内容 |
|---|---|
| cask `codex` | desc「OpenAI's coding agent that runs in your terminal」、homepage `https://github.com/openai/codex`、配布物は GitHub Releases の `codex-package-aarch64-apple-darwin.tar.gz`（0.155.1） |
| formula `codex` | API は 404（今は存在しない）。homebrew-core の `Formula/c/codex.rb` は 2025-10-17 のコミット「codex: remove formula to prepare for cask migration」（2de6c8ff61）で削除。削除直前（3b4ae5064e）の desc・homepage は cask と同じで、`tap_migrations.json` に `"codex": "homebrew/cask"`。→ **同じツール**。analytics には過去の install が残る |
| cask `claude-code` / `claude-code@latest` | desc「Terminal-based AI coding assistant」、homepage `https://claude.com/product/claude-code`、配布物は `downloads.claude.ai/claude-code-releases/…`（2.1.267 / 2.1.278） |
| formula `gemini-cli` | desc「Interact with Google Gemini AI models from the command-line」、homepage `https://geminicli.com`、ソースは `registry.npmjs.org/@google/gemini-cli/-/gemini-cli-0.46.0.tgz`（npm の tarball。bottle での導入が npm のダウンロード数に入るかは ❌ 未確認） |

## 利用条件

- npm Open Source Terms: 「You may replicate data from the Public Registry using the Public APIs per this Agreement.」、過大な負荷の禁止（月 500 万リクエストは論外という記述）。ダウンロード統計の再掲を禁じる記述は見当たらない（🔶 https://docs.npmjs.com/policies/open-source-terms ）
- Homebrew の JSON API: 利用条件・レート制限の記載なし（🔶）
- 本プロジェクトのリクエストは数十回、1 リクエスト/秒以下

## 先行（検索 4 回の範囲。網羅的ではない）

- Qiita「Codex CLIは躍進しているのか？ ～データで見る2025年8月のAI Codingの動向まとめ～」（2025-09-01）: GitHub の公開リポジトリ 9,000 個の設定ファイルの有無で 16 ツールの採用を数える。npm のダウンロード数・リリース頻度・配布経路は扱っていない（🔶 本文の要約）https://qiita.com/kotauchisunsun/items/a1e06dd590f945ae09ef
- TanStack の npm stats など、3 パッケージの比較チャートを見せるツールがある（❌ チャートは開いていない）。生のチャートを並べるだけでは新規性が無い
- Zenn・note・DEV の比較記事は機能・料金の比較（🔶 題名と要約）

## 「なぜ増えたのか」のフェーズ 0（2026-09-21、判定の後。代理指標の値は見ていない）

### 先行・報道（npm の突出の週を「逆転」として報じたもの）

| 出典 | 日付 | 内容 | 確認 |
|---|---|---|---|
| Espressio AI「Codex Passed Claude Code on npm: What the Spike Really Means」 https://espressio.ai/blog/codex-passed-claude-code-npm/ | 2026-05-06 | npm 公式 API（同日取得）で、直近 1 週間は `@openai/codex` 約 1 億 9,550 万・`@anthropic-ai/claude-code` 約 540 万、直近 1 か月は約 2 億 1,050 万と約 4,650 万。説明は「配布経路の違い（Claude Code は npm を非推奨にした）」と一般的な歪み（自動更新・CI・キャッシュ）。**同じパッケージ名のプラットフォーム版、突出が 05-07 に元へ戻ったこと（執筆時点では未来）には触れていない** | 🔶 WebFetch の要約 |
| BigGo Finance「Claude Code Faces Crisis of Trust: Users Flee as Codex Downloads Surge 12x」 https://finance.biggo.com/news/YIqNCp4BYH_ypPqO39KP | 2026-05-09 | TickerTrends の数字として、05-03 までの週に Codex 8,610 万・Claude Code 720 万（12 倍）、増加は「04-30 から 05-03 にほぼ集中」。原因を Claude 側のモデル更新後の品質低下と利用枠への不満による「利用者の流出」と説明。**npm の数え方への注意書きは無い** | 🔶 WebFetch の要約 |
| 同じ「12 倍」「週次 +1,397%」を伝える記事が中国語圏に複数（Yahoo 香港、cmoney、知乎、DoNews。2026-05-09〜10 ごろ） | ── | 題名と検索結果の要約のみ | 🔶 |
| 日本語での同種の報道・記事 | ── | 検索 2 回では見つからず（検索ツールが米国向けなので、無いとは言えない） | ❌ |

手元の日次（2026-09-21 取得）との対応: 04-26〜05-02 の 7 日間の合計は Codex 約 8,668 万・Claude Code 約 786 万で、報じられた 8,610 万・720 万と同じ桁。突出は 05-06 まで続き、05-07 に 85 万へ戻った（[posthoc.md](posthoc.md) 7 節）。

### 配布経路の追加の事実

- Claude Code の GitHub の README は「Installation via npm is deprecated.」と明記し、npm を「NPM (Deprecated)」として最後に置いている（✅ `gh api repos/anthropics/claude-code/readme`、2026-09-21）。README のインストール手順の直近の更新コミットは 2026-01-12・2025-11-09・2025-11-03（✅。非推奨の記述がどのコミットで入ったかは ❌ 未確認）

### 経路に依らない代理指標の到達（✅ 構造だけ確認。値は表示していない）

| 指標 | 取り方 | 確認したこと |
|---|---|---|
| issue の作成数（月・週） | GitHub Search API `search/issues?q=repo:…+is:issue+created:開始..終了` の `total_count`。認証つきで 30 回/分 | 3 リポジトリ（openai/codex、anthropics/claude-code、google-gemini/gemini-cli）とも存在し issue が有効。`incomplete_results: false` |
| issue の作成者（初めて立てた人の数） | REST `repos/…/issues?state=all`（100 件/ページ、`user.login` と `created_at`） | 項目の存在 |
| GitHub Releases のダウンロード数（版ごとの累計） | REST `repos/…/releases` の `assets[].download_count` | 3 リポジトリとも項目あり。openai/codex は 1 リリース 176 アセット（cask とインストールスクリプトの取得元）、claude-code は 10、gemini-cli は 3 |
| Hacker News の投稿数・ポイント | Algolia の公開 API `hn.algolia.com/api/v1/search_by_date`（`created_at_i`、`points`、`num_comments`） | 到達と項目 |
| GitHub のスター履歴 | REST は 404、GraphQL は edges が空 | **取れない**（使わない） |
| 公式の変更履歴 | https://learn.chatgpt.com/docs/changelog （developers.openai.com/codex/changelog から 308 で転送）。月ごとの見出し、2025-05〜2026-09-18、月 3〜8 件、ラベルは「Codex CLI」「General」など | 🔶 構造だけ。2026-04〜05 の項目の中身は未読 |
| Zenn の記事数（日本語の関心） | zenn-trend の 2026-09-04 取得ぶん（トピック `codex`・`codexcli`・`geminicli` は全期間。`claudecode` は一覧の上限で 2026-04 以降だけ） | 月別の本数は 2026-03〜07 を見た（codex: 134・125・278・257・236） |

## 「なぜ人が動いたのか」のフェーズ 0（2026-09-22。issue の題名の中身は、下に書いたもの以外は見ていない）

### 当事者の公表文

| 出典 | 日付 | 内容（要約） | 確認 |
|---|---|---|---|
| Anthropic「An update on recent Claude Code quality reports」 https://www.anthropic.com/engineering/april-23-postmortem | 2026-04-23 | Claude Code の品質についての利用者の報告を、3 つの変更にさかのぼって説明している。(1) 既定の推論の強さを high から medium に下げた（03-04 開始、04-07 に戻した。Sonnet 4.6・Opus 4.6）、(2) 1 時間以上止まっていたセッションで古い思考を消す変更に不具合があり、毎ターン消えていた（03-26 開始、04-10 の v2.1.101 で修正）、(3) 出力を短くするシステムプロンプトの指示が、コーディングの質を下げた（04-16 に Opus 4.7 と同時に開始、04-20 に戻した）。利用者の報告は 3 月上旬から。API は影響なし。**04-23 に全契約者の利用枠をリセット**。今後の対策（評価の拡充、段階的な展開など）を挙げている | 🔶 WebFetch の要約（当事者の公式ブログ） |
| OpenAI の変更履歴「GPT-5.5 and Codex app updates」 https://learn.chatgpt.com/docs/changelog | 2026-04-23 | 同じ日に GPT-5.5 の項目がある | ✅ 取得した HTML から項目の日付と題名を確認（中身は未読） |

→ 2026-04-23 には、Anthropic の説明と利用枠のリセット、OpenAI の新モデルが重なっている。Anthropic 自身の説明では、品質に影響のあった期間は 03-04〜04-20。

### issue の受け付け方の変更（✅ GitHub API、2026-03-01〜06-15 のコミット）

- anthropics/claude-code: `.github/ISSUE_TEMPLATE` の変更なし。`.github/workflows` は 03-31・04-27・05-06・05-22 に変更（題名からは issue の受け付けを絞る変更は読み取れない。中身は未確認）
- openai/codex: `.github/ISSUE_TEMPLATE` は 05-08（3 件）と 05-13 に変更。06-12 に「Translate non-English issues」のワークフロー

### リポジトリの公開範囲（✅ GitHub API）

- openai/codex: Apache-2.0。Rust のソース（言語統計で約 67 MB）とプルリクエストが公開されている
- anthropics/claude-code: GitHub の判定ではライセンスなし（LICENSE.md はある）。中身は README・CHANGELOG・plugins・examples・scripts などで、製品本体のソースは無い。issue の受け付けと変更履歴の場所

### すでに見た issue の題名

- openai/codex の 2026-04-28〜05-10 の issue のうち、題名が npm・install・update・download を含む 70 件（0003 の突出の追加確認）。それ以外の題名は、3 リポジトリとも読んでいない。Hacker News と Zenn の題名も、件数と区分の集計だけを見て、題名そのものは表示していない

### Gemini CLI の提供の変更（✅ 2026-09-22、リポジトリの公式アナウンス）

- google-gemini/gemini-cli の Discussions（Announcements）#28017「Important Update: Gemini CLI Has Stopped Serving Requests for Individual Accounts」（2026-06-18 20:02 UTC）: 2026-06-18 から、Gemini CLI は Google AI Pro・Ultra と無料枠の個人アカウントへの提供を止め、後継の Antigravity CLI への移行を案内している。Gemini Code Assist のライセンスを持つ企業利用と API キーでの利用は影響なし https://github.com/google-gemini/gemini-cli/discussions/28017
- 最初の告知は 2026-05-19（Google I/O）とする記事が複数ある（🔶 検索結果の要約。公式の告知文は未確認）
- これは 0004 の「Gemini CLI の issue が 6 月から激減した理由は未確認」への答えの候補。npm の日次の中央値は 2026-08 でも 01 月の 0.90 倍（0004）
