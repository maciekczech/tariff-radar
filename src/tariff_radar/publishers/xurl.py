from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def publish_thread_with_xurl(
    posts: list[str],
    *,
    executable: str = "xurl",
    state_path: Path | None = None,
    timeout: int = 30,
) -> list[str]:
    """Publish through xurl, resuming safely when a prior attempt stopped mid-thread."""
    if not posts:
        return []
    discovered = shutil.which(executable)
    if discovered is None:
        raise RuntimeError(
            "xurl is not installed; install and authenticate it before enabling X publishing"
        )
    resolved = str(Path(discovered).resolve())

    fingerprint = hashlib.sha256("\0".join(posts).encode()).hexdigest()
    ids = _load_state(state_path, fingerprint, len(posts))
    parent_id = ids[-1] if ids else None
    for text in posts[len(ids) :]:
        command = (
            [resolved, "post", text] if parent_id is None else [resolved, "reply", parent_id, text]
        )
        completed = subprocess.run(  # noqa: S603 - absolute executable, no shell
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        payload = json.loads(completed.stdout)
        post_id = str(payload["data"]["id"])
        ids.append(post_id)
        parent_id = post_id
        _save_state(state_path, fingerprint, ids)
    return ids


def _load_state(state_path: Path | None, fingerprint: str, post_count: int) -> list[str]:
    if state_path is None or not state_path.exists():
        return []
    payload = json.loads(state_path.read_text())
    if payload.get("fingerprint") != fingerprint:
        raise RuntimeError("X publication state belongs to a different thread")
    raw_ids = payload.get("ids", [])
    if not isinstance(raw_ids, list) or len(raw_ids) > post_count:
        raise RuntimeError("X publication state has an invalid post ID list")
    ids = [str(post_id) for post_id in raw_ids]
    if any(not post_id.strip() for post_id in ids):
        raise RuntimeError("X publication state contains an empty post ID")
    return ids


def _save_state(state_path: Path | None, fingerprint: str, ids: list[str]) -> None:
    if state_path is None:
        return
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    temporary.write_text(json.dumps({"fingerprint": fingerprint, "ids": ids}))
    temporary.replace(state_path)
