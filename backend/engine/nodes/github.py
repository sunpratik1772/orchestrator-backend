"""GitHub REST API actions. Authenticates via GITHUB_TOKEN env var."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunContext
from ..node_spec import _spec_from_yaml

_HERE = Path(__file__).parent
  
import base64
import json as _json
import logging
import os

import httpx

logger = logging.getLogger(__name__)
_BASE = "https://api.github.com"


def _upstream_rows(incoming):
    for out in incoming.values():
        if isinstance(out, dict) and isinstance(out.get("rows"), list):
            return list(out["rows"])
    return []


async def _gh(method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, _BASE + path, headers=headers, json=body)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, resp.text


def _lean(action: str, r: dict) -> dict:
    if action in ("list-repos", "get-repo"):
        return {
            "id": r.get("id"), "name": r.get("full_name") or r.get("name"),
            "description": r.get("description") or "",
            "stars": r.get("stargazers_count"), "forks": r.get("forks_count"),
            "open_issues": r.get("open_issues_count"),
            "language": r.get("language"), "updated_at": r.get("updated_at"),
            "url": r.get("html_url"),
        }
    if action in ("list-issues", "create-issue"):
        return {
            "id": r.get("id"), "number": r.get("number"),
            "title": r.get("title"), "state": r.get("state"),
            "author": (r.get("user") or {}).get("login"),
            "labels": ", ".join(l.get("name", "") for l in (r.get("labels") or [])),
            "created_at": r.get("created_at"), "updated_at": r.get("updated_at"),
            "url": r.get("html_url"),
        }
    if action == "list-prs":
        return {
            "id": r.get("id"), "number": r.get("number"),
            "title": r.get("title"), "state": r.get("state"),
            "author": (r.get("user") or {}).get("login"),
            "base": (r.get("base") or {}).get("ref"),
            "head": (r.get("head") or {}).get("ref"),
            "created_at": r.get("created_at"), "url": r.get("html_url"),
        }
    if action == "list-commits":
        sha = r.get("sha") or ""
        commit = r.get("commit") or {}
        return {
            "sha": sha[:8], "author": (commit.get("author") or {}).get("name"),
            "message": (commit.get("message") or "").split("\n")[0],
            "date": (commit.get("author") or {}).get("date"),
            "url": r.get("html_url"),
        }
    return r


async def run(node: dict, ctx: RunContext, incoming: dict[str, Any]) -> dict[str, Any]:
    cfg = node.get("config") or {}
    action = cfg.get("action") or "list-repos"
    repo = cfg.get("repo") or ""
    method, body = "GET", None

    if action == "list-repos":
        path = "/user/repos?per_page=50&sort=updated"
    elif action == "list-issues":
        if not repo: raise ValueError("repo required for list-issues")
        path = f"/repos/{repo}/issues?state={cfg.get('state', 'open')}&per_page=50"
    elif action == "list-prs":
        if not repo: raise ValueError("repo required for list-prs")
        path = f"/repos/{repo}/pulls?state={cfg.get('state', 'open')}&per_page=50"
    elif action == "list-commits":
        if not repo: raise ValueError("repo required for list-commits")
        path = f"/repos/{repo}/commits?per_page=30"
    elif action == "get-repo":
        if not repo: raise ValueError("repo required for get-repo")
        path = f"/repos/{repo}"
    elif action == "create-issue":
        if not repo: raise ValueError("repo required for create-issue")
        path = f"/repos/{repo}/issues"
        method = "POST"
        upstream_rows = _upstream_rows(incoming)
        labels_raw = cfg.get("labels") or ""
        body = {
            "title": cfg.get("title") or (
                f"Workflow result: {_json.dumps(upstream_rows[0])[:80]}" if upstream_rows else "New issue from dbStudio"
            ),
            "body": cfg.get("body") or (
                f"```json\n{_json.dumps(upstream_rows[:5], indent=2, default=str)}\n```" if upstream_rows else ""
            ),
            "labels": [l.strip() for l in labels_raw.split(",") if l.strip()],
        }
    elif action == "push-file":
        if not repo: raise ValueError("repo required for push-file")
        file_path = (cfg.get("filePath") or "").strip()
        if not file_path: raise ValueError("filePath required for push-file")
        fmt = cfg.get("fileFormat") or "json"
        rows = _upstream_rows(incoming)
        if cfg.get("fileContent"):
            raw = cfg["fileContent"]
        elif rows:
            if fmt == "csv":
                cols = list(rows[0].keys())
                lines = [",".join(cols)]
                for r in rows:
                    lines.append(",".join(_csv_escape(r.get(c)) for c in cols))
                raw = "\n".join(lines)
            else:
                raw = _json.dumps(rows, indent=2, default=str)
        else:
            raw = cfg.get("fileContent") or "{}"
        # Look up SHA if file already exists.
        existing_sha = None
        sc, data = await _gh("GET", f"/repos/{repo}/contents/{file_path}")
        if sc == 200 and isinstance(data, dict):
            existing_sha = data.get("sha")
        path = f"/repos/{repo}/contents/{file_path}"
        method = "PUT"
        body = {
            "message": cfg.get("commitMessage") or f"dbStudio: update {file_path}",
            "content": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
            "branch": cfg.get("branch") or "main",
        }
        if existing_sha:
            body["sha"] = existing_sha
    else:
        raise ValueError(f"Unknown GitHub action: {action}")

    sc, data = await _gh(method, path, body)
    if sc >= 400:
        raise RuntimeError(f"GitHub API {sc}: {str(data)[:200]}")

    if action == "push-file" and isinstance(data, dict):
        commit = data.get("commit") or {}
        return {
            "action": action, "repo": repo, "filePath": cfg.get("filePath"),
            "branch": cfg.get("branch") or "main",
            "commitSha": (commit.get("sha") or "")[:8],
            "commitUrl": commit.get("html_url"),
            "message": commit.get("message"),
            "pushed": True,
            "rows": [{"repo": repo, "file": cfg.get("filePath"),
                      "sha": (commit.get("sha") or "")[:8], "url": commit.get("html_url")}],
            "rowCount": 1, "connected": True,
        }

    items = data if isinstance(data, list) else [data]
    lean = [_lean(action, r) for r in items if isinstance(r, dict)]
    return {"action": action, "repo": repo, "rows": lean, "rowCount": len(lean), "connected": True}


def _csv_escape(v) -> str:
    s = str(v if v is not None else "")
    if "," in s or '"' in s:
        return '"' + s.replace('"', '""') + '"'
    return s
  
NODE_SPEC = _spec_from_yaml(_HERE / "github.yaml", run)
  