"""取得するリクエストの一覧と、生データの置き場所（data/raw/<取得日 UTC>/）の決まり。

fetch.py（実データ）と test_synthetic.py（合成データ）が同じ計画を使うので、
合成データは実データとまったく同じファイル構成になる。標準ライブラリのみ。
"""
from datetime import date, timedelta

PACKAGES = {
    "claude": "@anthropic-ai/claude-code",
    "codex": "@openai/codex",
    "gemini": "@google/gemini-cli",
}
TOOLS = tuple(PACKAGES)

# 3 パッケージの公開日（2025-02-24 / 04-16 / 06-25。sources.md）より前から取る
RANGE_START = date(2025, 1, 1)
# Claude Code のプラットフォーム別パッケージ（linux-x64 の作成日は 2026-04-13。sources.md）
CLAUDE_PLATFORM_PREFIX = "@anthropic-ai/claude-code-"
PLATFORM_RANGE_START = date(2026, 4, 1)

BREW_PERIODS = ("30d", "90d", "365d")
BREW_ANALYTICS = (
    # (category, リポジトリ, items のキー名)
    ("install", "homebrew-core", "formula"),
    ("install-on-request", "homebrew-core", "formula"),  # 事後の参考表用（判定には使わない）
    ("cask-install", "homebrew-cask", "cask"),
)
BREW_META = (
    ("formula", "codex"),
    ("formula", "gemini-cli"),
    ("cask", "codex"),
    ("cask", "claude-code"),
    ("cask", "claude-code@latest"),
)


def slug(pkg: str) -> str:
    return pkg.lstrip("@").replace("/", "__")


def last_day(fetch_date: date) -> date:
    """0001: 取得日の 2 日前までを使う。"""
    return fetch_date - timedelta(days=2)


def window(end: date, n_days: int) -> tuple[date, date]:
    """end を含む直近 n_days 日。"""
    return end - timedelta(days=n_days - 1), end


def range_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """暦年で区切る（npm の range は 1 回 18 か月まで）。"""
    out = []
    s = start
    while s <= end:
        e = min(date(s.year, 12, 31), end)
        out.append((s, e))
        s = e + timedelta(days=1)
    return out


def plan_stage1() -> list[dict]:
    """レジストリ（版の公開時刻と optionalDependencies）。プラットフォーム別パッケージ名はここから決める。"""
    return [
        {
            "kind": "registry",
            "package": pkg,
            "url": f"https://registry.npmjs.org/{pkg.replace('/', '%2F')}",
            "file": f"registry/{slug(pkg)}.json",
        }
        for pkg in PACKAGES.values()
    ]


def claude_platform_packages(claude_registry: dict) -> list[str]:
    """dist-tags.latest の optionalDependencies のうち、@anthropic-ai/claude-code-* のもの。"""
    latest = claude_registry["dist-tags"]["latest"]
    deps = claude_registry["versions"][latest].get("optionalDependencies", {})
    return sorted(k for k in deps if k.startswith(CLAUDE_PLATFORM_PREFIX))


def plan_stage2(fetch_date: date, platform_pkgs: list[str]) -> list[dict]:
    plan = []
    range_end = fetch_date - timedelta(days=1)  # 集計で使うのは last_day（2 日前）まで
    w30 = window(last_day(fetch_date), 30)
    for pkg in PACKAGES.values():
        for s, e in range_chunks(RANGE_START, range_end):
            plan.append({
                "kind": "npm_range", "package": pkg, "start": s.isoformat(), "end": e.isoformat(),
                "url": f"https://api.npmjs.org/downloads/range/{s}:{e}/{pkg}",
                "file": f"npm_range/{slug(pkg)}__{s}_{e}.json",
            })
    for pkg in PACKAGES.values():  # 撤退基準 B: 明示した 30 日間の point
        s, e = w30
        plan.append({
            "kind": "npm_point", "package": pkg, "start": s.isoformat(), "end": e.isoformat(),
            "url": f"https://api.npmjs.org/downloads/point/{s}:{e}/{pkg}",
            "file": f"npm_point/{slug(pkg)}__{s}_{e}.json",
        })
    for pkg in PACKAGES.values():  # P1a（Codex）。他 2 つは参考
        plan.append({
            "kind": "npm_versions", "package": pkg,
            "url": f"https://api.npmjs.org/versions/{pkg.replace('/', '%2F')}/last-week",
            "file": f"npm_versions/{slug(pkg)}.json",
        })
    for pkg in PACKAGES.values():  # 版別の合計と突き合わせるための参考（判定には使わない）
        plan.append({
            "kind": "npm_point_lastweek", "package": pkg,
            "url": f"https://api.npmjs.org/downloads/point/last-week/{pkg}",
            "file": f"npm_point_lastweek/{slug(pkg)}.json",
        })
    for pkg in platform_pkgs:
        s, e = PLATFORM_RANGE_START, range_end
        plan.append({
            "kind": "npm_range_platform", "package": pkg, "start": s.isoformat(), "end": e.isoformat(),
            "url": f"https://api.npmjs.org/downloads/range/{s}:{e}/{pkg}",
            "file": f"npm_range_platform/{slug(pkg)}__{s}_{e}.json",
        })
    for category, repo, _ in BREW_ANALYTICS:
        for period in BREW_PERIODS:
            plan.append({
                "kind": "brew_analytics", "category": category, "period": period,
                "url": f"https://formulae.brew.sh/api/analytics/{category}/{repo}/{period}.json",
                "file": f"brew/analytics__{category}__{period}.json",
            })
    for typ, name in BREW_META:
        plan.append({
            "kind": "brew_meta", "type": typ, "name": name,
            "url": f"https://formulae.brew.sh/api/{typ}/{name}.json",
            "file": f"brew/{typ}__{name.replace('@', '_at_')}.json",
        })
    return plan
