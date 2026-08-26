"""Retrait d'une strategie dont l'avantage n'est plus valide."""

from __future__ import annotations


class DecommissionPolicy:
    def run(self, reason: str) -> dict:
        return {
            "service_disabled": True,
            "artifacts_archived": True,
            "access_revoked": True,
            "reason": reason,
            "auto_optimization": False,
        }
