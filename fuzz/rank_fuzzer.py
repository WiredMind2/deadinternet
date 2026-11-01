"""Atheris harness scaffolded by ClusterFuzz (AST fallback)."""
import sys
from pathlib import Path

import atheris

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / 'src'))

from deadinternet.domain.rank import cell_size, below_sample_floor, suggest, assert_no_render_side_effect  # noqa: E402


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    try:
        cell_size(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)), fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass
    try:
        below_sample_floor(fdp.ConsumeIntInRange(-10**6, 10**6), fdp.ConsumeIntInRange(-10**6, 10**6))
    except Exception:
        pass
    try:
        suggest(fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)), fdp.ConsumeUnicodeNoSurrogates(min(fdp.RemainingBytes(), 4096)))
    except Exception:
        pass
    try:
        assert_no_render_side_effect()
    except Exception:
        pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
