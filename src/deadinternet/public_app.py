"""The internet-facing click app: GET /r/{code} and nothing else (US-034).

The admin API (api/app.py) keeps its own /r/{code} route for local dev
convenience and the vite dev proxy; THIS app is the one an operator
exposes to the open internet, because it mounts no write surface at all.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from deadinternet.api.app import _ThreadSafeStore
from deadinternet.track.redirect import hit


def create_public_app(store) -> FastAPI:
    """Serve the tracking redirect on the lab's store, with no admin route.

    The store gets the same treatment the admin app applies:
    _ThreadSafeStore reopens the file connection for FastAPI's worker
    threads and serializes every call, so concurrent clicks cannot
    interleave transactions on one connection. The helper is imported
    from api.app (which this story does not modify) so the two apps
    share the connection identically instead of drifting copies.
    """
    store = _ThreadSafeStore(store)
    # No docs or schema routes: the public surface advertises nothing
    # beyond the redirect itself.
    app = FastAPI(title="Dead Internet clicks", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/r/{code}")
    def redirect_click(code: str):
        # Identical to the admin route's happy path: hit() owns the
        # counter+log transaction on the same store, so a click here is
        # recorded exactly as the admin app records one. hit() raises
        # KeyError for an unknown code, and UnconfiguredDestination (a
        # KeyError subclass) when the code's merchant has no saved offer
        # url. The admin app echoes str(exc) — naming the merchant and
        # the POST /offers fix — which is right for a local dev surface;
        # the public app deliberately answers one generic 404 for both,
        # so the open internet learns nothing about the store.
        try:
            _count, destination = hit(store, code)
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown tracking code") from None
        return RedirectResponse(url=destination, status_code=302)

    return app
