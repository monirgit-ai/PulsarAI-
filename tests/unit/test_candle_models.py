from datetime import datetime, timezone

from data.ingestion.models import Candle


def test_from_rest_kline() -> None:
    row = [
        1710000000000,
        "50000.0",
        "51000.0",
        "49000.0",
        "50500.0",
        "100.5",
        1710003599999,
        "5000000.0",
        1200,
        "50.0",
        "2500000.0",
        "0",
    ]
    c = Candle.from_rest_kline("btcusdt", "1h", row)
    assert c.symbol == "BTCUSDT"
    assert c.timeframe == "1h"
    assert c.close == 50500.0
    assert c.num_trades == 1200


def test_from_ws_kline() -> None:
    k = {
        "t": 1710000000000,
        "s": "ETHUSDT",
        "i": "1m",
        "o": "3000",
        "h": "3010",
        "l": "2990",
        "c": "3005",
        "v": "10",
        "n": 50,
        "x": True,
    }
    c = Candle.from_ws_kline(k)
    assert c.symbol == "ETHUSDT"
    assert c.timeframe == "1m"
    assert c.volume == 10.0
