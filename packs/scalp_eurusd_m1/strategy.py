"""Scalping EURUSD M1 : impulse + EMA, spread conscient."""

from packs.impulse_ema import ImpulseEmaScalp


def build(pack):
    return ImpulseEmaScalp(pack)


Strategy = ImpulseEmaScalp
