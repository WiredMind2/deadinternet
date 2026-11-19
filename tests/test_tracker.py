import pytest

from deadinternet.domain.experiment import Affiliate, OwnOffer
from deadinternet.track.redirect import UnconfiguredDestination, hit
from tests.helpers import experiment, open_store


def test_click_increments_only_that_experiment(tmp_path):
    store = open_store(tmp_path)
    store.upsert_offer("acme", "Acme", "https://acme.test/deal", merchant="acme")
    store.upsert_offer("other", "Other", "https://other.test/deal", merchant="other")
    first = experiment(id="exp-a", money=Affiliate(tracking_code="code-a", merchant="acme"))
    second = experiment(id="exp-b", money=Affiliate(tracking_code="code-b", merchant="other"))
    store.insert_experiment(first)
    store.insert_experiment(second)

    count, url = hit(store, "code-a")
    assert count == 1
    assert url == "https://acme.test/deal"
    assert store.get_experiment("exp-a").clicks == 1
    assert store.get_experiment("exp-b").clicks == 0

    count, url = hit(store, "code-a")
    assert count == 2
    assert url == "https://acme.test/deal"
    assert store.get_experiment("exp-a").clicks == 2
    assert store.get_experiment("exp-b").clicks == 0

    count, url = hit(store, "code-b")
    assert count == 1
    assert url == "https://other.test/deal"
    assert store.get_experiment("exp-a").clicks == 2
    assert store.get_experiment("exp-b").clicks == 1


def test_affiliate_click_without_a_saved_offer_url_does_not_click(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(
        experiment(id="exp-a", money=Affiliate(tracking_code="code-a", merchant="acme"))
    )
    with pytest.raises(UnconfiguredDestination):
        hit(store, "code-a")
    assert store.get_experiment("exp-a").clicks == 0


def test_own_offer_click_uses_the_offer_url(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(
        experiment(
            id="exp-own",
            money=OwnOffer(tracking_code="own-1", offer_url="https://shop.test/deal"),
        )
    )
    count, url = hit(store, "own-1")
    assert count == 1
    assert url == "https://shop.test/deal"
    assert store.get_experiment("exp-own").clicks == 1


def test_unknown_code_does_not_click(tmp_path):
    store = open_store(tmp_path)
    store.insert_experiment(experiment(id="exp-a"))
    with pytest.raises(KeyError):
        hit(store, "missing")
    assert store.get_experiment("exp-a").clicks == 0
