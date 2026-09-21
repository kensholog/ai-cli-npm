"""記事用の図。docs/data/ の公開 CSV・JSON だけから描く（生データ不要）。matplotlib が要る（.venv）。

  .venv/Scripts/python scripts/figures.py [out_dir]     既定の out_dir: ../zenn-content/images/ai-cli-npm

  fig1_codex_platform_share.png  版別ダウンロード数（直近 7 日）のうち、プラットフォーム版が占める割合。3 パッケージに同じ集計（P1a）
  fig2_daily_downloads.png       3 パッケージの日次ダウンロード数（7 日移動中央値、対数目盛）（記述 e）
  fig3_step_around_e.png         2026-02-11 の前後 28 日の中央値（P1b）。3 パッケージを同じ窓で

色は 3 系列（青・橙・青緑）。色覚多様性での見分けやすさは dataviz の validate_palette.js で確認済み（全ペア、light）。
青緑は背景とのコントラストが 3:1 未満なので、線の端に名前を直接書く。
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "zenn-content" / "images" / "ai-cli-npm"
OUT.mkdir(parents=True, exist_ok=True)

SURFACE, INK, INK2, GRID, NEUTRAL = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0", "#c9c8c0"
COLOR = {"claude": "#2a78d6", "codex": "#eb6834", "gemini": "#1baf7a"}
NAME = {"claude": "Claude Code", "codex": "Codex CLI", "gemini": "Gemini CLI"}
PKG = {"claude": "@anthropic-ai/claude-code", "codex": "@openai/codex", "gemini": "@google/gemini-cli"}
TOOLS = ("claude", "codex", "gemini")

plt.rcParams.update({
    "font.family": ["Meiryo", "BIZ UDPGothic", "Yu Gothic", "MS Gothic", "sans-serif"],  # Noto Sans JP（可変フォント）は極細になる
    "axes.unicode_minus": False, "figure.dpi": 160, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "axes.spines.top": False, "axes.spines.right": False, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left", "font.size": 9.5,
})

S = json.loads((DATA / "summary.json").read_text(encoding="utf-8"))
with open(DATA / "daily_downloads.csv", encoding="utf-8") as f:
    ROWS = list(csv.DictReader(f))
DAILY = {t: {date.fromisoformat(r["day"]): int(r[t]) for r in ROWS if r[t] != ""} for t in TOOLS}


def man(x, _=None):
    return f"{x / 1e4:,.10g} 万" if x >= 1e4 else f"{x:,.0f}"


# ---- fig 1: プラットフォーム版の割合（P1a）
totals = {"codex": (S["P1a"]["total"], S["P1a"]["platform_total"])}
for t, x in S["P1a_reference_other_tools"].items():
    totals[t] = (x["total"], x["platform_total"])
fig, ax = plt.subplots(figsize=(9, 3.3))
order = ["gemini", "claude", "codex"]  # 下から。Codex を一番上に
for y, t in enumerate(order):
    total, plat = totals[t]
    share = plat / total
    ax.barh(y, 1 - share, height=0.5, color=NEUTRAL, edgecolor=SURFACE, linewidth=2)
    ax.barh(y, share, left=1 - share, height=0.5, color=COLOR["codex"], edgecolor=SURFACE, linewidth=2)
    ax.text((1 - share) / 2, y, f"本体の版 {(1 - share) * 100:.1f}%", ha="center", va="center", fontsize=9.5, color=INK)
    if share > 0:
        ax.text(1 - share / 2, y, f"プラットフォーム版 {share * 100:.1f}%", ha="center", va="center", fontsize=9.5, color=INK, fontweight="bold")
    ax.text(-0.012, y + 0.14, NAME[t], ha="right", va="center", fontsize=10, fontweight="bold")
    ax.text(-0.012, y - 0.17, f"{PKG[t]}\n7 日で {total:,}", ha="right", va="center", fontsize=7.5, color=INK2)
ax.set_xlim(0, 1)
ax.set_ylim(-0.5, 2.55)
ax.set_yticks([])
ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
ax.spines["left"].set_visible(False)
fig.suptitle("同じパッケージ名のダウンロード数のうち、プラットフォーム別バイナリの版が占める割合（直近 7 日）",
             x=0.015, ha="left", fontsize=10.5, fontweight="bold")
fig.text(0.015, 0.03, "npm の版別ダウンロード数（2026-09-21 取得）。プラットフォーム版 = 版の文字列が -darwin-arm64・-darwin-x64・-linux-arm64・-linux-x64・\n"
         "-win32-arm64・-win32-x64 で終わる版（例: 0.155.1-linux-x64）。Claude Code はバイナリを別名の 8 パッケージに置き、Gemini CLI はバイナリを持たない",
         fontsize=7.5, color=INK2, va="bottom")
fig.subplots_adjust(left=0.23, right=0.97, top=0.88, bottom=0.26)
fig.savefig(OUT / "fig1_codex_platform_share.png")
plt.close(fig)


# ---- fig 2: 日次の推移（7 日移動中央値、0 の日を除く、対数目盛）
def rolling(daily: dict) -> tuple[list, list]:
    xs, ys = [], []
    for d in sorted(daily):
        vals = [daily[x] for x in (d + timedelta(days=k) for k in range(-3, 4)) if daily.get(x, 0) > 0]
        if len(vals) >= 4:
            xs.append(d)
            ys.append(median(vals))
    return xs, ys


fig, ax = plt.subplots(figsize=(9, 4.8))
for t in TOOLS:
    xs, ys = rolling(DAILY[t])
    ax.plot(xs, ys, color=COLOR[t], lw=2, label=NAME[t], solid_capstyle="round")
    ax.annotate(NAME[t], (xs[-1], ys[-1]), textcoords="offset points", xytext=(6, -3 if t != "claude" else -9), fontsize=9, color=INK)
ax.set_yscale("log")
ax.yaxis.set_major_formatter(FuncFormatter(man))
ax.set_ylim(800, 9e7)
ax.grid(axis="y")
ax.set_axisbelow(True)
for d, txt, ha, dx in ((date(2026, 2, 11), "2026-02-11  Codex CLI 0.99.0\nバイナリを同じパッケージ名の\n別バージョンとして配りはじめる", "right", -4),
                       (date(2026, 4, 17), "2026-04-17  Claude Code 2.1.113\nバイナリを別名の 8 パッケージに", "left", 4)):
    ax.axvline(d, color=INK2, lw=0.8)
    ax.text(d + timedelta(days=dx), 1100, txt, fontsize=7.8, color=INK2, va="bottom", ha=ha)
ax.annotate("Codex CLI  2026-04-30〜05-06\n1 日 1,300 万〜4,600 万（前後は 90 万前後）\n原因は未確認", (date(2026, 5, 3), 3.4e7),
            textcoords="offset points", xytext=(14, -2), fontsize=7.8, color=INK2, va="center")
ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax.set_xlim(date(2025, 2, 24), date(2026, 11, 20))
ax.set_ylabel("1 日のダウンロード数（対数目盛）")
ax.legend(loc="upper left", frameon=False, ncol=3, fontsize=9)
ax.set_title("3 パッケージの npm 日次ダウンロード数（7 日移動中央値、2025-02-24〜2026-09-19、UTC）")
ax.text(0, -0.12, "npm の公式 API（2026-09-21 取得）。値が 0 の日（npm 側の集計の欠けとみられる 9〜10 日）は除いて中央値を取った。ダウンロード数は利用者数ではない",
        transform=ax.transAxes, fontsize=7.5, color=INK2, va="top")
fig.subplots_adjust(left=0.09, right=0.98, top=0.92, bottom=0.14)
fig.savefig(OUT / "fig2_daily_downloads.png")
plt.close(fig)


# ---- fig 3: E の前後（P1b）。3 パッケージを同じ窓で、縦軸はそれぞれ 0 から
P = S["P1b"]["per_tool"]
fig, axes = plt.subplots(1, 3, figsize=(9, 3.6))
x0, x1 = date(2026, 1, 5), date(2026, 4, 2)
for ax, t in zip(axes, TOOLS):
    before = [date.fromisoformat(x) for x in P[t]["before"]]
    after = [date.fromisoformat(x) for x in P[t]["after"]]
    xs = [d for d in sorted(DAILY[t]) if x0 <= d <= x1]
    ax.axvspan(before[0], before[1] + timedelta(days=1), color=NEUTRAL, alpha=0.35, lw=0)
    ax.axvspan(after[0], after[1] + timedelta(days=1), color=NEUTRAL, alpha=0.35, lw=0)
    ax.plot(xs, [DAILY[t][d] for d in xs], color=COLOR[t], lw=1.4)
    for win, key in ((before, "median_before"), (after, "median_after")):
        ax.plot([win[0], win[1]], [P[t][key]] * 2, color=INK, lw=2, solid_capstyle="round")
        ax.text(win[0] + (win[1] - win[0]) / 2, 0.97, f"中央値 {P[t][key] / 1e4:,.1f} 万", ha="center", va="top", fontsize=8.5, color=INK,
                transform=ax.get_xaxis_transform())
    ax.axvline(date(2026, 2, 11), color=INK2, lw=0.8)
    ax.set_ylim(0, max(DAILY[t][d] for d in xs) * 1.25)
    ax.yaxis.set_major_formatter(FuncFormatter(man))
    ax.grid(axis="y")
    ax.set_axisbelow(True)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m 月"))
    ax.set_xlim(x0, x1)
    ax.tick_params(labelsize=8)
    ax.set_title(f"{NAME[t]}   中央値の比 {P[t]['ratio']:.2f} 倍", fontsize=10)
fig.suptitle("2026-02-11（Codex CLI 0.99.0、縦線）の前 28 日と、14 日あけた後 28 日（灰色の帯）の日次ダウンロード数",
             x=0.01, ha="left", fontsize=10.5, fontweight="bold")
fig.text(0.01, 0.02, f"黒い横線は帯の中の中央値。縦軸はパッケージごとに違う（0 から）。Codex CLI の比 ÷ 他 2 つの比の平均 = {S['P1b']['did']:.2f}。"
         "二重計上だけで説明できるのは最大 2 倍まで", fontsize=7.5, color=INK2)
fig.subplots_adjust(left=0.07, right=0.985, top=0.8, bottom=0.17, wspace=0.28)
fig.savefig(OUT / "fig3_step_around_e.png")
plt.close(fig)
print("saved:", *[p.name for p in sorted(OUT.glob("fig*.png"))], "→", OUT)
