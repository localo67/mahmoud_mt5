"""Detection de look-ahead : aucune donnee future n'est accessible."""


class LookAheadError(RuntimeError):
    pass


def assert_no_lookahead(bars: list[dict], now: int, accessor) -> None:
    visible = [bar for bar in bars if bar["time"] <= now]
    accessed_time = accessor(bars)
    if visible and accessed_time > now:
        raise LookAheadError(f"bar future {accessed_time} lue a {now}")
    if not visible and bars and accessor(bars) > now:
        raise LookAheadError(f"bar future {accessed_time} lue a {now}")
