# ロードマップ

## 全体方針

- 「検証できるか」が先。問い・予測・閾値・撤退基準は、値を見る前に [decisions/0001](decisions/0001-question-and-criteria.md) で凍結する
- 数値と事実には出典 URL と確認日。事実と推測を分ける。未確認は「未確認」と書く
- どのツールが勝っているかは主張しない。3 ツールに同じ指標を当てる
- 生データ（`data/`）はコミットしない。公開するのは `docs/` の集計と図だけ

## フェーズ一覧

| フェーズ | 内容 | 状態 | 成果物 |
|---|---|---|---|
| 0 | データの到達・利用条件・先行の確認（値は見ない） | **通過（2026-09-21）** | [sources.md](sources.md) |
| 0.5 | 予測 P1a・P1b・P2・P3 と撤退基準 A・B・C の凍結 | **2026-09-21** | [decisions/0001](decisions/0001-question-and-criteria.md) |
| 1 | 取得（npm range・point・版別・レジストリ・Homebrew、40 リクエスト） | **2026-09-21** | `data/`（非公開） |
| 2 | A・B の判定 → P1a・P1b・P2・P3 と記述 | **2026-09-21**（A・B 通過、C を満たす） | [results.md](results.md)、`docs/data/`、[decisions/0002](decisions/0002-verdicts.md)、[posthoc.md](posthoc.md) |
| 2.5 | 問いの追加「npm の急増は何だったのか」: 予測 Q1・Q2、記述 Q3・Q4 の凍結 → issue・Releases・Hacker News の取得 → 判定 | **2026-09-21**（凍結 [0003](decisions/0003-why-question-and-criteria.md) → 取得 1,521 リクエスト → 判定 [0004](decisions/0004-why-verdicts.md)。Q1 は「人の流入とは整合しない」、Q2 は支持） | [results_why.md](results_why.md)、`docs/data/why_*` |
| 2.7 | 問いの追加「なぜ人が動いたのか」＋公開データで比べられる項目の表: 凍結 → 題名の集計と追加取得（issue の状態、約 500 リクエスト）→ 判定 | **2026-09-22**（凍結 [0005](decisions/0005-why-people-moved.md) → 題名の集計と追加取得 479 リクエスト → 判定 [0006](decisions/0006-moved-verdicts.md)。R1a・R1m・R1b は保留、R3 は判定不能） | [results_moved.md](results_moved.md)、`docs/data/moved_*` |
| 3 | 記事（zenn-content で執筆。平日、2026-10-05 以降に公開） | 図 3 枚と下書きまで（2026-09-21）。公開前に、値が 0 の日を 3 リクエストで再確認する | `scripts/figures.py` |

## やらないこと

- 利用者数の推定（npm 以外の経路の数は公開データに無い）
- ツールの機能・性能・料金の比較
- 比較チャートのサイトの画面を引用すること（一次データから自分で描く）
- 取得後に窓・閾値・対象を変えること
