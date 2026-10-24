"""Read an unpacked snapshot directory into objects ``ingest`` accepts.

The scorer normally builds ``Snapshot`` values itself. This loader exists so
the smoke run can feed the same on-disk layout (``manifest.json`` plus
``pages/*.md``) without calling the live website.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def load_snapshot_dir(root: Path | str) -> list[SimpleNamespace]:
    folder = Path(root)
    snapshots: list[SimpleNamespace] = []
    children = [
        path for path in folder.iterdir() if path.is_dir() and (path / "manifest.json").is_file()
    ]
    for snap_dir in sorted(children):
        manifest = json.loads((snap_dir / "manifest.json").read_text(encoding="utf-8"))
        pages = []
        for entry in manifest.get("pages") or []:
            rel = entry["file"]
            file_path = (snap_dir / rel).resolve()
            if not file_path.is_relative_to(snap_dir.resolve()):
                raise ValueError(f"unsafe page path in {snap_dir.name}: {rel}")
            pages.append(
                SimpleNamespace(
                    url=entry["url"],
                    title=entry.get("title") or "",
                    markdown=file_path.read_text(encoding="utf-8"),
                    fetched_at=entry.get("fetched_at") or manifest["taken_on"],
                )
            )
        snapshots.append(
            SimpleNamespace(
                snapshot_id=manifest["snapshot_id"],
                taken_on=manifest["taken_on"],
                pages=pages,
            )
        )
    snapshots.sort(key=lambda snap: snap.taken_on)
    return snapshots
