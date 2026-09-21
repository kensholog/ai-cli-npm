"""比較表（decisions/0005）の「issue への対応」用に、issue の状態を取得して data/issue_states/<取得日 UTC>/ に保存する。

- GitHub の GraphQL を、認証済みの `gh` コマンド経由で呼ぶ。作成日時の新しい順に、2026-06-01 より前の issue が出るまでさかのぼる
- 取る項目: number・createdAt・closedAt・state・stateReason・コメントの件数・作成者の種別（題名も本文も取らない）
- 1 リクエスト/秒以下、再開可。値は表示しない

  python scripts/fetch_issue_states.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_proxies as F  # noqa: E402
import proxy_metrics as PM  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STOP_BEFORE = "2026-06-01T00:00:00Z"
QUERY = """
query($owner:String!, $name:String!, $after:String) {
  repository(owner:$owner, name:$name) {
    issues(first:100, after:$after, orderBy:{field:CREATED_AT, direction:DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { number createdAt closedAt state stateReason comments { totalCount } author { __typename } }
    }
  }
}
"""


def main() -> None:
    out = ROOT / "data" / "issue_states" / datetime.now(timezone.utc).date().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    log = F.Log(out)
    for tool, repo in PM.REPOS.items():
        owner, name = repo.split("/")
        path, state_path = out / f"{F.slug(repo)}.jsonl", out / f"{F.slug(repo)}.state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"after": None, "done": False, "pages": 0, "started_at": F.now()}
        while not state["done"]:
            args = ["graphql", "-f", f"query={QUERY}", "-f", f"owner={owner}", "-f", f"name={name}"]
            if state["after"]:
                args += ["-f", f"after={state['after']}"]
            conn = json.loads(F.gh(args, log, "issue_states", f"{repo} page {state['pages'] + 1}"))["data"]["repository"]["issues"]
            with open(path, "a", encoding="utf-8") as f:
                for node in conn["nodes"]:
                    f.write(json.dumps(node, ensure_ascii=False) + "\n")
            reached = bool(conn["nodes"]) and conn["nodes"][-1]["createdAt"] < STOP_BEFORE
            state.update({"after": conn["pageInfo"]["endCursor"], "pages": state["pages"] + 1,
                          "done": reached or not conn["pageInfo"]["hasNextPage"]})
            state_path.write_text(json.dumps(state), encoding="utf-8")
        print(f"issue_states {repo}: 完了（{state['pages']} ページ）")
    log.add(kind="done", what="issue_states")


if __name__ == "__main__":
    main()
