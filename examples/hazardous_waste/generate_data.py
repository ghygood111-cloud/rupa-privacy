"""Generate a synthetic enterprise-year hazardous-waste demonstration pair.

The equations are teaching assumptions, not regulatory mass-balance rules or
records obtained from an information centre.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


INDUSTRIES = (
    "steel_rolling",
    "coking",
    "metal_surface_treatment",
    "waste_incineration",
)
WASTE_TYPES = (
    "waste_acid",
    "distillation_residue",
    "incineration_fly_ash",
    "surface_treatment_waste",
)
WASTE_COLUMNS = tuple(name + "_t" for name in WASTE_TYPES)
WASTE_PROFILES = np.array(
    [
        [0.60, 0.14, 0.08, 0.18],
        [0.10, 0.68, 0.14, 0.08],
        [0.12, 0.08, 0.12, 0.68],
        [0.08, 0.12, 0.72, 0.08],
    ]
)


def generate_enterprise_year(n_rows, seed, prefix):
    rng = np.random.default_rng(seed)
    industry_index = rng.choice(len(INDUSTRIES), size=n_rows, p=[0.26, 0.24, 0.28, 0.22])
    industry = np.asarray(INDUSTRIES)[industry_index]
    generated = np.clip(rng.lognormal(np.log(520.0), 0.39, n_rows), 110.0, 1500.0)
    fractions = np.vstack(
        [rng.dirichlet(35.0 * WASTE_PROFILES[index]) for index in industry_index]
    )
    waste_masses = generated[:, None] * fractions

    handling_fractions = rng.dirichlet([3.5, 3.0, 1.5], size=n_rows)
    transferred = generated * handling_fractions[:, 0]
    on_site = generated * handling_fractions[:, 1]
    retained = generated - transferred - on_site
    cross_share = rng.beta(2.2, 3.0, size=n_rows)
    cross_region = transferred * cross_share
    within_region = transferred - cross_region

    manifest_count = rng.poisson(2.0 + generated / 22.0)
    cross_manifests = rng.binomial(manifest_count, cross_share)
    within_manifests = manifest_count - cross_manifests
    emergency_count = rng.poisson(
        0.12 + 0.24 * (industry == "waste_incineration") + 0.10 * (cross_share > 0.7)
    )
    handling_route = np.asarray(["transfer", "on_site", "retained"])[
        np.argmax(handling_fractions, axis=1)
    ]
    dominant_type = np.asarray(WASTE_TYPES)[np.argmax(waste_masses, axis=1)]
    plan_status = rng.choice(["current", "review_due"], n_rows, p=[0.72, 0.28])
    confidential_cost_index = (
        0.14 * generated
        + 0.08 * cross_region
        + 0.55 * manifest_count
        + 18.0 * emergency_count
        + 24.0 * (plan_status == "review_due")
        + rng.normal(0.0, 22.0, n_rows)
    )

    names = ["{0}{1:06d}".format(prefix, index) for index in range(n_rows)]
    data = {
        "public_enterprise_period_id": names,
        "qyid": ["SYN-QY-" + name for name in names],
        "zzjgdm": ["SYN-USCC-" + name for name in names],
        "dwmc": ["Synthetic enterprise " + name for name in names],
        "dwszqxz": ["DEMO01"] * n_rows,
        "dwdz": ["Not a real address"] * n_rows,
        "hylbdm": ["SYN{0:02d}".format(index + 1) for index in industry_index],
        "lxr": ["not_collected"] * n_rows,
        "lxrsj": ["not_collected"] * n_rows,
        "gljhid": ["SYN-PLAN-" + name for name in names],
        "year": [2026] * n_rows,
        "generated_total_t": generated,
    }
    data.update({name: waste_masses[:, index] for index, name in enumerate(WASTE_COLUMNS)})
    data.update(
        {
            "transferred_total_t": transferred,
            "cross_region_transferred_t": cross_region,
            "within_region_transferred_t": within_region,
            "on_site_treated_t": on_site,
            "retained_for_next_period_t": retained,
            "manifest_total_count": manifest_count,
            "cross_region_manifest_count": cross_manifests,
            "within_region_manifest_count": within_manifests,
            "emergency_response_count": emergency_count,
            "industry_group": industry,
            "dominant_waste_type": dominant_type,
            "primary_handling_route": handling_route,
            "emergency_plan_status": plan_status,
            "confidential_cost_index": confidential_cost_index,
        }
    )
    return pd.DataFrame(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--calibration-rows", type=int, default=240)
    parser.add_argument("--release-rows", type=int, default=320)
    args = parser.parse_args()
    if args.calibration_rows < 2 or args.release_rows < 2:
        parser.error("Both datasets require at least two rows")
    args.output.mkdir(parents=True, exist_ok=True)
    calibration = generate_enterprise_year(args.calibration_rows, 20261016, "CAL-")
    release = generate_enterprise_year(args.release_rows, 20261017, "REL-")
    calibration.to_csv(args.output / "calibration.csv", index=False)
    release.drop(columns=["confidential_cost_index"]).to_csv(
        args.output / "release.csv", index=False
    )
    print(
        "Wrote synthetic calibration.csv ({0} rows) and release.csv ({1} rows)".format(
            len(calibration), len(release)
        )
    )


if __name__ == "__main__":
    main()
