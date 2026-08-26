from core.filling import filling_name, select_filling
from fakes import FakeMT5


def test_select_filling_prefers_ioc_then_fok_then_return() -> None:
    api = FakeMT5()
    assert select_filling(2, api) == api.ORDER_FILLING_IOC
    assert select_filling(1, api) == api.ORDER_FILLING_FOK
    assert select_filling(0, api) == api.ORDER_FILLING_RETURN
    assert filling_name(api.ORDER_FILLING_IOC, api) == "IOC"
