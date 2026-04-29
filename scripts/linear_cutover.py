#!/usr/bin/env python3
"""One-time bd -> Linear cutover helper for Symphony.

The script is intentionally small and stdlib-only. It turns tracked bead JSONL
into Linear issue payloads and can create those issues through Linear GraphQL
when the required environment variables are present.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def _graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    api_key = _env("LINEAR_API_KEY")
    if api_key is None:
        raise SystemExit("LINEAR_API_KEY is required for Linear API calls.")
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    request = urllib.request.Request(
        LINEAR_GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Linear API HTTP {exc.code}: {body}") from exc
    data = json.loads(body)
    if data.get("errors"):
        raise SystemExit(json.dumps(data["errors"], indent=2))
    return data["data"]


def status(_: argparse.Namespace) -> int:
    data = _graphql(
        """
        query CutoverStatus {
          viewer { id name email }
          teams(first: 50) { nodes { id key name } }
          workflowStates(first: 100) { nodes { id name type team { key name } } }
          projects(first: 100) { nodes { id name state teams { nodes { key name } } } }
        }
        """
    )
    print(json.dumps(data, indent=2))
    return 0


def _load_beads(path: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            issue = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        if isinstance(issue, dict):
            issues.append(issue)
    return issues


def _priority(value: Any) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return 0
    if priority <= 0:
        return 1
    if priority == 1:
        return 2
    if priority == 2:
        return 3
    return 4


def _description(issue: dict[str, Any]) -> str:
    parts = [
        f"Legacy bead: `{issue.get('id', '')}`",
        "",
        issue.get("description") or "_No description in bead._",
    ]
    if issue.get("design"):
        parts.extend(["", "## Design", str(issue["design"])])
    if issue.get("acceptance_criteria"):
        parts.extend(["", "## Acceptance Criteria", str(issue["acceptance_criteria"])])
    if issue.get("notes"):
        parts.extend(["", "## Notes", str(issue["notes"])])
    labels = issue.get("labels") or []
    if labels:
        parts.extend(["", "## Legacy Labels", ", ".join(f"`{label}`" for label in labels)])
    return "\n".join(parts).strip()


def _payload(issue: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    team_id = args.team_id or _env("LINEAR_TEAM_ID")
    if team_id is None:
        raise SystemExit("LINEAR_TEAM_ID is required to build Linear issue payloads.")
    bead_id = issue.get("id") or "unknown"
    title = issue.get("title") or "Untitled bead"
    payload: dict[str, Any] = {
        "teamId": team_id,
        "title": f"[{bead_id}] {title}",
        "description": _description(issue),
        "priority": _priority(issue.get("priority")),
    }
    project_id = args.project_id or _env("LINEAR_PROJECT_ID")
    state_id = args.state_id or _env("LINEAR_READY_STATE_ID")
    if project_id:
        payload["projectId"] = project_id
    if state_id:
        payload["stateId"] = state_id
    return payload


def _selected(issues: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    wanted_ids = set(args.id or [])
    selected: list[dict[str, Any]] = []
    for issue in issues:
        if wanted_ids and issue.get("id") not in wanted_ids:
            continue
        if args.status and issue.get("status") != args.status:
            continue
        selected.append(issue)
    if args.limit is not None:
        selected = selected[: args.limit]
    return selected


def plan(args: argparse.Namespace) -> int:
    issues = _selected(_load_beads(args.input), args)
    payloads = [_payload(issue, args) for issue in issues]
    print(json.dumps(payloads, indent=2))
    print(f"\nPrepared {len(payloads)} Linear issue payload(s).", file=sys.stderr)
    return 0


def push(args: argparse.Namespace) -> int:
    issues = _selected(_load_beads(args.input), args)
    payloads = [_payload(issue, args) for issue in issues]
    if not args.execute:
        print(json.dumps(payloads, indent=2))
        print(
            f"\nDry run: prepared {len(payloads)} issue(s). "
            "Re-run with --execute to create them in Linear.",
            file=sys.stderr,
        )
        return 0
    mutation = """
    mutation IssueCreate($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue { id identifier title url }
      }
    }
    """
    created: list[dict[str, Any]] = []
    for payload in payloads:
        data = _graphql(mutation, {"input": payload})
        result = data["issueCreate"]
        if not result.get("success"):
            raise SystemExit(f"Linear rejected issue: {payload['title']}")
        created.append(result["issue"])
    print(json.dumps(created, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)

    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Print Linear teams, workflow states, and projects.")

    def add_cutover_args(cutover_parser: argparse.ArgumentParser) -> None:
        cutover_parser.add_argument(
            "--input",
            type=Path,
            default=Path(".beads/issues.jsonl"),
            help="Path to bead JSONL export.",
        )
        cutover_parser.add_argument("--team-id", help="Linear team id. Defaults to LINEAR_TEAM_ID.")
        cutover_parser.add_argument(
            "--project-id", help="Linear project id. Defaults to LINEAR_PROJECT_ID."
        )
        cutover_parser.add_argument(
            "--state-id", help="Linear target state id. Defaults to LINEAR_READY_STATE_ID."
        )
        cutover_parser.add_argument(
            "--status", default="open", help="Bead status filter. Defaults to open."
        )
        cutover_parser.add_argument(
            "--id", action="append", help="Specific bead id to migrate. Repeatable."
        )
        cutover_parser.add_argument("--limit", type=int, help="Limit number of selected beads.")

    plan_parser = sub.add_parser("plan", help="Print Linear issue payloads without API writes.")
    add_cutover_args(plan_parser)
    push_parser = sub.add_parser(
        "push", help="Create Linear issues. Dry-run unless --execute is set."
    )
    add_cutover_args(push_parser)
    push_parser.add_argument("--execute", action="store_true", help="Actually create issues.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "status":
        return status(args)
    if args.cmd == "plan":
        return plan(args)
    if args.cmd == "push":
        return push(args)
    parser.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
