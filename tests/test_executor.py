from src.executor import Executor


class DummyClient:
    def __init__(self):
        self.calls = []

    def place_bracket_order(self, symbol, contracts, entry, stop, targets):
        self.calls.append((symbol, contracts, entry, stop, targets))
        return {"id": "123"}


def test_executor_calls_client_and_returns_order_id():
    client = DummyClient()
    executor = Executor(client)
    result = executor.place_bracket("SPY", 2, 5.0, 4.0, [6.0, 6.5])
    assert result.submitted is True
    assert result.order_id == "123"
    assert client.calls


def test_executor_handles_missing_client_gracefully():
    executor = Executor(None)
    result = executor.place_bracket("SPY", 1, 5.0, 4.0, [6.0])
    assert result.submitted is False
    assert result.reason == "no_client"
