import uvicorn

from deadinternet.api.app import create_app
from deadinternet.propose.agent import RepairProposer
from deadinternet.runtime import LivePublisher, LiveRenderer
from deadinternet.store import Store


def main() -> None:
    store = Store("data/deadinternet.sqlite")
    app = create_app(
        store,
        renderer=LiveRenderer(),
        publisher=LivePublisher(),
        proposer=RepairProposer.from_env(),
    )
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
