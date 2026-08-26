"""APIs MT5 factices partagees par les tests, sans broker reel."""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional


def closed_bar(
    time_unix: int,
    open_: float = 2500.0,
    high: float = 2501.0,
    low: float = 2499.0,
    close: float = 2500.5,
    tick_volume: int = 100,
) -> tuple:
    return (time_unix, open_, high, low, close, tick_volume, 0, 0)


def make_bars(count: int, start: int = 1_700_000_000, step: int = 300) -> list[tuple]:
    return [closed_bar(start + i * step, close=2500.0 + (i % 5) * 0.1) for i in range(count)]


class FakeCheckResult:
    def __init__(self, retcode: int, comment: str = "ok"):
        self.retcode = retcode
        self.comment = comment


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_FOK = 2
    ORDER_FILLING_RETURN = 3
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_INVALID_FILL = 10030
    TRADE_RETCODE_MARKET_CLOSED = 10018
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    SYMBOL_TRADE_MODE_FULL = 4
    DEAL_ENTRY_OUT = 1

    def __init__(
        self,
        account_trade_mode: int = ACCOUNT_TRADE_MODE_DEMO,
        symbols: Optional[list[str]] = None,
        tick_time: Optional[int] = None,
        market_closed: bool = False,
        trade_allowed: bool = True,
        filling: int = ORDER_FILLING_IOC,
        check_retcode: int = TRADE_RETCODE_DONE,
        m5_count: int = 200,
        m15_count: int = 200,
    ):
        self.account_trade_mode = account_trade_mode
        self.symbols = symbols if symbols is not None else ["XAUUSD"]
        self.tick_time = tick_time if tick_time is not None else int(
            datetime.now(timezone.utc).timestamp()
        )
        self.market_closed = market_closed
        self.trade_allowed = trade_allowed
        self.filling = filling
        self.check_retcode = check_retcode
        self.m5_count = m5_count
        self.m15_count = m15_count
        self.order_requests: list[dict] = []
        self.check_requests: list[dict] = []
        self.selected: set[str] = set(self.symbols)
        self.positions: list = []
        self.deals: list = []
        self.timeout_send: bool = False
        self.fail_before_send: bool = False
        self.drop_position_after_send: bool = False
        self.truncate_comment: int | None = None
        self.partial_volume: float | None = None
        self.orders: list = []
        self.history_orders: list = []
        self._next_ticket: int = 987
        self.initialized = True

    def initialize(self) -> bool:
        self.initialized = True
        return True

    def shutdown(self) -> None:
        self.initialized = False

    def login(self, *args, **kwargs) -> bool:
        return True

    def last_error(self):
        return (0, "ok")

    def terminal_info(self):
        return SimpleNamespace(
            connected=True,
            trade_allowed=self.trade_allowed,
            name="MetaTrader 5",
        )

    def account_info(self):
        return SimpleNamespace(
            login=123456,
            name="Demo",
            server="Demo-Server",
            currency="USD",
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            margin_free=10_000.0,
            leverage=100,
            margin_level=0.0,
            trade_mode=self.account_trade_mode,
            trade_allowed=self.trade_allowed,
            margin_mode=getattr(self, "margin_mode", 2),
        )

    def symbols_get(self):
        return [SimpleNamespace(name=name) for name in self.symbols]

    def symbol_select(self, name: str, enable: bool = True) -> bool:
        if name not in self.symbols:
            return False
        if enable:
            self.selected.add(name)
        else:
            self.selected.discard(name)
        return True

    def symbol_info(self, name: str):
        if name not in self.symbols:
            return None
        return SimpleNamespace(
            name=name,
            visible=name in self.selected,
            select=name in self.selected,
            digits=2,
            spread=20,
            trade_mode=self.SYMBOL_TRADE_MODE_FULL,
            volume_min=0.01,
            volume_max=5.0,
            volume_step=0.01,
            volume_limit=10.0,
            point=0.01,
            trade_tick_size=0.01,
            trade_tick_value=1.0,
            trade_tick_value_profit=1.0,
            trade_tick_value_loss=1.0,
            trade_contract_size=100.0,
            trade_calc_mode=0,
            currency_profit="USD",
            currency_margin="USD",
            trade_stops_level=10,
            trade_freeze_level=0,
            filling_mode=self.filling,
            bid=2500.0,
            ask=2500.20,
            time=self.tick_time,
        )

    def symbol_info_tick(self, name: str):
        if name not in self.symbols:
            return None
        return SimpleNamespace(
            bid=2500.0,
            ask=2500.20,
            time=self.tick_time,
            time_msc=self.tick_time * 1000,
        )

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int):
        available = self.m5_count if timeframe == self.TIMEFRAME_M5 else self.m15_count
        if start_pos > 0:
            available = max(0, available - start_pos)
        return make_bars(min(count, available))

    def positions_get(self, **kwargs):
        symbol = kwargs.get("symbol")
        ticket = kwargs.get("ticket")
        items = self.positions
        if symbol:
            items = [p for p in items if p.symbol == symbol]
        if ticket is not None:
            items = [p for p in items if p.ticket == ticket]
        return tuple(items)

    def order_check(self, request: dict):
        self.check_requests.append(request)
        if self.market_closed:
            return FakeCheckResult(self.TRADE_RETCODE_MARKET_CLOSED, "market closed")
        if self.filling != self.ORDER_FILLING_IOC:
            return FakeCheckResult(self.TRADE_RETCODE_INVALID_FILL, "invalid fill")
        return FakeCheckResult(self.check_retcode, "ok")

    def order_send(self, request: dict):
        if self.fail_before_send:
            raise TimeoutError("timeout before send")
        self.order_requests.append(request)
        ticket = self._next_ticket
        self._next_ticket += 1
        filled = (
            self.partial_volume
            if self.partial_volume is not None
            else request.get("volume", 0.0)
        )
        comment = request.get("comment", "")
        if self.truncate_comment is not None:
            comment = comment[: self.truncate_comment]
        position = SimpleNamespace(
            ticket=ticket,
            symbol=request.get("symbol"),
            type=request.get("type", self.ORDER_TYPE_BUY),
            volume=filled,
            price_open=request.get("price", 0.0),
            price_current=request.get("price", 0.0),
            sl=request.get("sl", 0.0),
            tp=request.get("tp", 0.0),
            profit=0.0,
            swap=0.0,
            commission=0.0,
            comment=comment,
            time=self.tick_time,
            identifier=ticket,
            magic=request.get("magic", 0),
        )
        if not self.drop_position_after_send:
            self.positions.append(position)
        self.history_orders.append(
            SimpleNamespace(
                ticket=ticket,
                symbol=request.get("symbol"),
                magic=request.get("magic", 0),
                comment=comment,
                volume=request.get("volume", 0.0),
                volume_current=filled,
            )
        )
        self.deals.append(
            SimpleNamespace(
                ticket=ticket + 1000,
                order=ticket,
                position_id=ticket,
                symbol=request.get("symbol"),
                volume=filled,
                price=request.get("price", 0.0),
                profit=0.0,
                commission=0.0,
                swap=0.0,
                entry=0,
                magic=request.get("magic", 0),
                comment=comment,
            )
        )
        if self.timeout_send:
            raise TimeoutError("timeout after send")
        retcode = (
            self.TRADE_RETCODE_DONE_PARTIAL
            if self.partial_volume is not None
            else self.TRADE_RETCODE_DONE
        )
        return SimpleNamespace(
            retcode=retcode,
            order=ticket,
            deal=ticket + 1000,
            volume=filled,
            comment="done",
        )

    def history_deals_get(self, *args, **kwargs):
        symbol = kwargs.get("symbol") or kwargs.get("group")
        items = list(self.deals)
        if symbol:
            items = [item for item in items if getattr(item, "symbol", None) == symbol]
        return items

    def history_orders_get(self, *args, **kwargs):
        symbol = kwargs.get("symbol") or kwargs.get("group")
        items = list(self.history_orders)
        if symbol:
            items = [item for item in items if getattr(item, "symbol", None) == symbol]
        return items

    def orders_get(self, *args, **kwargs):
        symbol = kwargs.get("symbol")
        ticket = kwargs.get("ticket")
        items = list(self.orders)
        if symbol:
            items = [item for item in items if getattr(item, "symbol", None) == symbol]
        if ticket is not None:
            items = [item for item in items if getattr(item, "ticket", None) == ticket]
        return tuple(items)
