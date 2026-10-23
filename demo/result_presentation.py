"""Presentation-only tables derived from already exported public diagnostics."""

from typing import Mapping

import pandas as pd


PHYSICAL_STAGES = (
    ("noisy", "DP perturbation"),
    ("full_projection", "Full projection"),
    ("interpolated", "Interpolation"),
    ("final_clipped", "Final clipping"),
)


def physical_stage_table(physical: Mapping) -> pd.DataFrame:
    """Keep the actual stage order and distinguish missing measurements from zero."""
    states = physical.get("states", {})
    rows = []
    for order, (key, label) in enumerate(PHYSICAL_STAGES, start=1):
        values = states.get(key)
        if not isinstance(values, Mapping) or not values:
            continue
        rows.append(
            {
                "Order": order,
                "State": key,
                "Stage": label,
                "RMS": values.get("rms"),
                "NRMS": values.get("nrms"),
                "Max absolute residual": values.get("max_absolute_residual"),
                "Violation rate": values.get("violation_rate"),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "Order", "State", "Stage", "RMS", "NRMS",
            "Max absolute residual", "Violation rate",
        ],
    )
