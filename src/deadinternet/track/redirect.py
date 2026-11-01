"""Resolve a tracking code to a destination and record one click."""

from deadinternet.domain.experiment import Affiliate, OwnOffer


def destination_for(store, code: str) -> str:
    """Offer URL for this code, scanning stored experiments."""
    for experiment in store.list_experiments():
        money = experiment.money
        if isinstance(money, OwnOffer) and money.tracking_code == code:
            return money.offer_url
        if isinstance(money, Affiliate) and money.tracking_code == code:
            return f"https://example.test/{money.merchant}"
    raise KeyError(code)


def hit(store, code: str) -> tuple[int, str]:
    """Return the new click count and the destination URL for `code`."""
    destination = destination_for(store, code)
    count = int(store.add_click(code))
    return count, destination
