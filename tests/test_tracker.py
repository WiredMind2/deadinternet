import pytest

from deadinternet.domain.experiment import Affiliate, OwnOffer
from deadinternet.track.redirect import hit
from tests.helpers import experiment, open_store


def test_click_increments_only_that_experiment(tmp_path):
    store = open_store(tmp_path)
    first = experiment(id="exp-a", money=Affiliate(tracking_code="code-a", merchant="acme"))
    second = experiment(id="exp-b", money=Affiliate(tracking_code="code-b", merchant="other"))
    store.insert_experiment(first)
    store.insert_experiment(second)

    count, url = hit(store, "code-a")
    assert count == 1
    assert url == "https://example.test/acme"
    assert store.get_experiment("exp-a").clicks == 1
    assert store.get_experiment("exp-b").clicks == 0

    count, url = hit(store, "code-a")
    assert count == 2
    assert url == "https://example.test/acme"
    assert store.get_experiment("exp-a").clicks == 2
    assert store.get_experiment("exp-b").clicks == 0

    count, url = hit(store, "code-b")
    assert count == 1
    assert url == "https://example.test/other"
    assert store.get_experiment("exp-a").clicks == 2
    assert store.get_experiment("exp-b").clicks == 1


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
