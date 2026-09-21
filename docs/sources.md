# 確認済みの事実と出典

凡例: ✅ 一次情報を自分で確認 / 🔶 WebFetch・検索の要約で確認 / ❌ 未確認。確認日はすべて 2026-09-21。

## データの仕様

| 項目 | 内容 | 出典 |
|---|---|---|
| npm の日次ダウンロード数 | `GET https://api.npmjs.org/downloads/range/{開始}:{終了}/{package}`。日は UTC。1 回の問い合わせは最大 18 か月、最古は 2015-01-10。スコープつきパッケージは point / range で使えるが、一括（bulk）では使えない。3 パッケージとも 2025-01-01〜2026-06-30 の 546 日分が返ることを確認（✅ 日数と日付だけ） | 🔶 https://github.com/npm/registry/blob/main/docs/download-counts.md |
| 版別のダウンロード数 | `GET https://api.npmjs.org/versions/{package}/last-week`。「only available for the previous 7 days」。`@openai%2Fcodex` で 4,324 版のキーが返り、うち 3,631 がプラットフォーム接尾辞つき（✅ キー名と件数だけ） | 🔶 同上 |
| 「1 ダウンロード」の定義 | 同文書は npm のブログ記事「how npm download counts work」を参照している | ❌ ブログ記事は未読。記事を書く前に読む |
| 版の公開時刻 | `GET https://registry.npmjs.org/{package}` の `time`（版 → ISO 時刻）と `versions[版].optionalDependencies` | ✅ |
| Homebrew の install 数 | `https://formulae.brew.sh/api/analytics/{install,cask-install}/{homebrew-core,homebrew-cask}/{30d,90d,365d}.json`。`install` は依存としての導入を含み、`install-on-request` は明示的な導入だけ | 🔶 https://formulae.brew.sh/docs/api/ |

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

## 利用条件

- npm Open Source Terms: 「You may replicate data from the Public Registry using the Public APIs per this Agreement.」、過大な負荷の禁止（月 500 万リクエストは論外という記述）。ダウンロード統計の再掲を禁じる記述は見当たらない（🔶 https://docs.npmjs.com/policies/open-source-terms ）
- Homebrew の JSON API: 利用条件・レート制限の記載なし（🔶）
- 本プロジェクトのリクエストは数十回、1 リクエスト/秒以下

## 先行（検索 4 回の範囲。網羅的ではない）

- Qiita「Codex CLIは躍進しているのか？ ～データで見る2025年8月のAI Codingの動向まとめ～」（2025-09-01）: GitHub の公開リポジトリ 9,000 個の設定ファイルの有無で 16 ツールの採用を数える。npm のダウンロード数・リリース頻度・配布経路は扱っていない（🔶 本文の要約）https://qiita.com/kotauchisunsun/items/a1e06dd590f945ae09ef
- TanStack の npm stats など、3 パッケージの比較チャートを見せるツールがある（❌ チャートは開いていない）。生のチャートを並べるだけでは新規性が無い
- Zenn・note・DEV の比較記事は機能・料金の比較（🔶 題名と要約）
