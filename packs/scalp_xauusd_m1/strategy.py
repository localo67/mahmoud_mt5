"""Scalping XAUUSD M1 : meme idee que EURUSD, seuils or."""

from packs.impulse_ema import ImpulseEmaScalp


def build(pack):
    return ImpulseEmaScalp(pack)


Strategy = ImpulseEmaScalp
