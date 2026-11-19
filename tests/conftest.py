import pytest

from tests.helpers import OPENED_STORES


@pytest.fixture(autouse=True)
def _close_stores():
    """Close every store a test opened so no sqlite handle outlives it.

    Unclosed handles surface as ResourceWarnings at unpredictable moments
    (usually during a later test) and can hold Windows file locks on the
    tmp directories."""
    yield
    for store in OPENED_STORES:
        try:
            store.close()
        except Exception:
            pass
    OPENED_STORES.clear()
