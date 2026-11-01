"""Storyboard files inside a niche folder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from deadinternet.domain.experiment import Beat, InvalidBoard


class UnsafeId(ValueError):
    pass


def check_segment(value: str) -> str:
    if (
        not isinstance(value, str)
        or value == ""
        or value.strip() == ""
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
    ):
        raise UnsafeId(f"unsafe id {value!r}")
    return value


def storyboard_path(media_dir: Path | str, theme_id: str, niche_id: str, experiment_id: str) -> Path:
    return (
        Path(media_dir)
        / check_segment(theme_id)
        / check_segment(niche_id)
        / f"{check_segment(experiment_id)}.storyboard.json"
    )


def video_path(media_dir: Path | str, theme_id: str, niche_id: str, experiment_id: str) -> Path:
    board = storyboard_path(media_dir, theme_id, niche_id, experiment_id)
    return board.with_name(f"{check_segment(experiment_id)}.mp4")


def canonical_bytes(beats: tuple[Beat, ...] | list[Beat]) -> bytes:
    payload = {
        "beats": [
            {
                "spoken": beat.spoken,
                "on_screen": beat.on_screen,
                "visual_note": beat.visual_note,
            }
            for beat in beats
        ]
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_storyboard(path: Path, beats: tuple[Beat, ...] | list[Beat]) -> str:
    payload = canonical_bytes(beats)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hash_bytes(payload)


def read_storyboard(path: Path) -> tuple[tuple[Beat, ...], str]:
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise InvalidBoard("storyboard file is unreadable") from exc
    try:
        raw = json.loads(payload.decode("utf-8"))
        beats = tuple(
            Beat(
                spoken=str(item["spoken"]),
                on_screen=str(item.get("on_screen") or ""),
                visual_note=str(item.get("visual_note") or ""),
            )
            for item in raw["beats"]
        )
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise InvalidBoard("storyboard file is unreadable") from exc
    return beats, hash_bytes(payload)
