from src.executor import Executor


class DummyClient:
    def __init__(self):
        self.submitted = []
        self.closed = []
        self.cancelled = []

    def submit_order(self, **kwargs):
        self.submitted.append(kwargs)
        return {"id": "123"}

    def close_position(self, **kwargs):
        self.closed.append(kwargs)

    def cancel_child_orders(self, order_id):
        self.cancelled.append(order_id)


def test_executor_submits_bracket_and_tracks_idempotency():
    client = DummyClient()
    executor = Executor(client)

    result = executor.enter_with_bracket(
        option_symbol="SPY240621C001", 
        qty=2,
        hard_stop_opt_price=1.0,
        take_profit_opt_price=2.0,
        trade_date="2024-06-21",
        symbol="SPY",
        direction="long",
        orb_len=30,
    )

    assert result.submitted is True
    assert result.order_id == "123"
    assert client.submitted[0]["order_class"] == "bracket"
    assert client.submitted[0]["take_profit"] == {"limit_price": 2.0}

    duplicate = executor.enter_with_bracket(
        option_symbol="SPY240621C001",
        qty=1,
        hard_stop_opt_price=0.5,
        take_profit_opt_price=None,
        trade_date="2024-06-21",
        symbol="SPY",
        direction="long",
        orb_len=30,
    )
    assert duplicate.submitted is False
    assert duplicate.reason == "duplicate"


def test_executor_handles_missing_client_gracefully():
    executor = Executor(None)
    result = executor.enter_with_bracket(
        option_symbol="SPY", 
        qty=1, 
        hard_stop_opt_price=1.0, 
        take_profit_opt_price=None,
        trade_date="2024-06-21",
        symbol="SPY",
        direction="long",
        orb_len=30,
    )
    assert result.submitted is False
    assert result.reason == "no_client"


def test_close_and_cancel_helpers_call_client():
    client = DummyClient()
    executor = Executor(client)

    executor.close_option_market("SPY240621C001")
    executor.cancel_children("order-1")

    assert client.closed == [{"symbol": "SPY240621C001", "type": "market"}]
    assert client.cancelled == ["order-1"]
