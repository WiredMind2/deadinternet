"""Resolve a tracking code to a destination and record one click."""

from deadinternet.domain.experiment import Affiliate, OwnOffer


class UnconfiguredDestination(KeyError):
    """The code is known, but its merchant has no saved offer URL."""


def destination_for(store, code: str) -> str:
    """Operator-configured offer URL for this code, scanning stored experiments."""
    for experiment in store.list_experiments():
        money = experiment.money
        if isinstance(money, OwnOffer) and money.tracking_code == code:
            return money.offer_url
        if isinstance(money, Affiliate) and money.tracking_code == code:
            offer = store.get_offer(money.merchant)
            url = (offer or {}).get("url") or ""
            if not url:
                raise UnconfiguredDestination(
                    f"merchant {money.merchant} has no offer url; save one with POST /offers"
                )
            return url
    raise KeyError(code)


def hit(store, code: str) -> tuple[int, str]:
    """Return the new click count and the destination URL for `code`."""
    destination = destination_for(store, code)
    count = int(store.add_click(code))
    return count, destination
