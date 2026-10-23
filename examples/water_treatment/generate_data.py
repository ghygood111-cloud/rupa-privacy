"""Generate an independent semi-synthetic water-treatment demonstration pair."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


TREATMENT_TRAINS = ("conventional", "membrane", "hybrid")
SOURCE_CLASSES = ("river", "reservoir", "groundwater", "industrial_blend")
SHIFT_PATTERNS = ("day", "rotating", "continuous")


def generate_water_treatment(n_rows, seed, id_prefix):
    rng = np.random.default_rng(seed)
    train = rng.choice(TREATMENT_TRAINS, n_rows, p=[0.48, 0.22, 0.30])
    source = rng.choice(SOURCE_CLASSES, n_rows, p=[0.35, 0.25, 0.25, 0.15])
    shift = rng.choice(SHIFT_PATTERNS, n_rows, p=[0.18, 0.34, 0.48])

    source_factor = pd.Series(source).map(
        {"river": 1.05, "reservoir": 0.95, "groundwater": 0.82, "industrial_blend": 1.20}
    ).to_numpy()
    train_loss = pd.Series(train).map(
        {"conventional": 0.030, "membrane": 0.055, "hybrid": 0.040}
    ).to_numpy()
    raw_inflow = np.clip(
        rng.lognormal(mean=np.log(56000.0), sigma=0.30, size=n_rows) * source_factor,
        12000.0,
        150000.0,
    )
    sludge_fraction = np.clip(
        0.018 + 0.010 * (source == "industrial_blend") + rng.normal(0.0, 0.0025, n_rows),
        0.010,
        0.045,
    )
    backwash_fraction = np.clip(
        train_loss + rng.normal(0.0, 0.004, n_rows), 0.015, 0.075
    )
    sludge_water = raw_inflow * sludge_fraction
    backwash_loss = raw_inflow * backwash_fraction
    treated_outflow = raw_inflow - sludge_water - backwash_loss

    recycle_fraction = np.clip(
        0.09 + 0.05 * (train == "membrane") + rng.normal(0.0, 0.012, n_rows),
        0.05,
        0.20,
    )
    recycle_water = treated_outflow * recycle_fraction
    process_feed = treated_outflow + recycle_water

    aeration_intensity = (
        0.24
        + 0.10 * (train == "membrane")
        + 0.06 * (source == "industrial_blend")
        + rng.normal(0.0, 0.018, n_rows)
    )
    pumping_intensity = (
        0.075
        + 0.025 * (shift == "continuous")
        + 0.012 * (source == "groundwater")
        + rng.normal(0.0, 0.008, n_rows)
    )
    aeration_energy = np.clip(aeration_intensity, 0.15, 0.48) * process_feed
    pumping_energy = np.clip(pumping_intensity, 0.045, 0.14) * raw_inflow
    total_energy = aeration_energy + pumping_energy

    operating_cost_index = (
        0.085 * total_energy
        + 0.018 * sludge_water
        + 120.0 * (train == "membrane")
        + 90.0 * (source == "industrial_blend")
        + rng.normal(0.0, 75.0, n_rows)
    )

    return pd.DataFrame(
        {
            "plant_day_id": ["{0}{1:06d}".format(id_prefix, i) for i in range(n_rows)],
            "raw_inflow_m3d": raw_inflow,
            "treated_outflow_m3d": treated_outflow,
            "backwash_loss_m3d": backwash_loss,
            "sludge_water_m3d": sludge_water,
            "process_feed_m3d": process_feed,
            "recycle_water_m3d": recycle_water,
            "aeration_energy_kwh": aeration_energy,
            "pumping_energy_kwh": pumping_energy,
            "total_energy_kwh": total_energy,
            "treatment_train": train,
            "source_water_class": source,
            "shift_pattern": shift,
            "operating_cost_index": operating_cost_index,
        }
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=Path(__file__).resolve().parent, type=Path)
    parser.add_argument("--calibration-rows", type=int, default=1500)
    parser.add_argument("--release-rows", type=int, default=2000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    calibration = generate_water_treatment(args.calibration_rows, 271828, "CAL-")
    release = generate_water_treatment(args.release_rows, 314159, "REL-")
    calibration.to_csv(args.output / "calibration.csv", index=False)
    release.drop(columns=["operating_cost_index"]).to_csv(
        args.output / "release.csv", index=False
    )
    print("Wrote calibration.csv ({0} rows) and release.csv ({1} rows)".format(
        len(calibration), len(release)
    ))


if __name__ == "__main__":
    main()

