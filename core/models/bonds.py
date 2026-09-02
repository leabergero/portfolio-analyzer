"""
bonds.py — Renta fija argentina: soberanos y obligaciones negociables.

Fase 1 expone solo lo que hace falta para identificar y rutear instrumentos.
El resto —flujos de fondos, interés corrido, TIR y curva— entra en la fase 3,
junto con las medidas de riesgo de tasa (duración, DV01, convexidad) anotadas
en `docs/PENDIENTES.md`.

El mapeo del ticker en dólares vive en `core.data.symbols` porque es
conocimiento del espacio de nombres, no de la matemática del bono: lo necesitan
también el ruteo de precios y el importador de CSV, que no deberían depender de
este módulo.
"""

from core.data.symbols import (  # noqa: F401  — API pública de renta fija
    COCOS_ONLY,
    LETRAS,
    ON_D_TICKER,
    SOBERANOS,
    d_ticker,
    is_bond,
)

__all__ = ["d_ticker", "is_bond", "SOBERANOS", "ON_D_TICKER", "LETRAS", "COCOS_ONLY"]
