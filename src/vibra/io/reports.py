"""Serialize typed results without hidden arrays, NaNs, or proprietary formats."""

import dataclasses
import json
from typing import Any

import numpy as np
from pydantic import BaseModel

from vibra import __version__


def _encode(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Unsupported report object: {type(value).__name__}")


def engineering_report(analysis: str, inputs: Any, result: Any) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "vibra_version": __version__,
            "analysis": analysis,
            "units": "SI: m, kg, s, N, Pa, rad; frequencies explicitly in Hz",
            "verification_scope": (
                "Solver benchmark suite only; this user model has not been independently validated"
            ),
            "validation_status": "Analytical numerical verification; not experimental",
            "inputs": inputs,
            "results": result,
        },
        default=_encode,
        indent=2,
        allow_nan=False,
    )
