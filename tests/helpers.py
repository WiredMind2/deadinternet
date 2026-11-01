from deadinternet.domain.experiment import Affiliate, Experiment, FacelessStyle, Look, Status
from deadinternet.store import Store


def open_store(tmp_path):
    return Store(str(tmp_path / "lab.sqlite"))


def experiment(**overrides) -> Experiment:
    base = dict(
        id="exp-1",
        niche_id="niche-1",
        hypothesis="A question hook travels",
        hook_id="question",
        script="Here is the spoken script.",
        caption="Watch this.",
        style=FacelessStyle(look=Look.stills, voice_id="voice-1", caption_style="bold"),
        money=Affiliate(tracking_code="abc", merchant="acme"),
        status=Status.draft,
        length_sec=45,
    )
    base.update(overrides)
    return Experiment(**base)


def experiment_body(**overrides) -> dict:
    body = {
        "id": "exp-1",
        "niche_id": "niche-1",
        "hypothesis": "A question hook travels",
        "hook_id": "question",
        "script": "Here is the spoken script.",
        "caption": "Watch this.",
        "style": {
            "kind": "faceless",
            "look": "stills",
            "voice_id": "voice-1",
            "caption_style": "bold",
        },
        "money": {"kind": "affiliate", "tracking_code": "abc", "merchant": "acme"},
        "length_sec": 45,
    }
    body.update(overrides)
    return body
