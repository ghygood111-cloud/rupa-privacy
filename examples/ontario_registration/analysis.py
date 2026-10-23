"""Public-only downstream GRR frequency analysis; not a RUPA mechanism."""
import math

import numpy as np
import pandas as pd

FIELDS = ("handles_liquid", "handles_solid")


def binary_parameters(epsilon):
    epsilon = float(epsilon)
    if not math.isfinite(epsilon) or epsilon <= 0:
        raise ValueError("Field epsilon must be finite and positive")
    q = math.exp(-epsilon) / (1.0 + math.exp(-epsilon))
    p = 1.0 - q
    if p <= q:
        raise ValueError("Field epsilon is too small for stable floating-point decoding")
    return p, q, p - q


def analyze_public_release(public, epsilon, family_alpha=0.05):
    """Read only released rows and public mechanism parameters, never raw truth."""
    if len(public) == 0:
        raise ValueError("Public release must be non-empty")
    if not math.isfinite(family_alpha) or not 0 < family_alpha < 1:
        raise ValueError("family_alpha must be finite and in (0, 1)")
    half_width = math.sqrt(math.log(2 * len(FIELDS) / family_alpha) / (2 * len(public)))
    marginals, inverse_weights = {}, {}
    for name in FIELDS:
        if name not in public or not set(public[name].unique()).issubset({"no", "yes"}):
            raise ValueError("Expected public binary domain for " + name)
        p, q, gap = binary_parameters(epsilon[name])
        yes = public[name].eq("yes").to_numpy(dtype=float)
        observed = float(yes.mean())
        estimate = (observed - q) / gap
        inverse_weights[name] = (yes - q) / gap
        marginals[name] = {
            "observed_proportion": observed,
            "decoded_proportion_unclipped": estimate,
            "decoded_proportion_clipped_for_display": float(np.clip(estimate, 0, 1)),
            "simultaneous_95_lower": float(np.clip((observed - half_width - q) / gap, 0, 1)),
            "simultaneous_95_upper": float(np.clip((observed + half_width - q) / gap, 0, 1)),
            "epsilon": float(epsilon[name]), "p": p, "q": q,
        }
    both = float(np.mean(inverse_weights[FIELDS[0]] * inverse_weights[FIELDS[1]]))
    return {
        "rows": int(len(public)), "marginals": marginals,
        "both_states_observed": float(public[list(FIELDS)].eq("yes").all(axis=1).mean()),
        "both_states_decoded_unclipped": both,
        "analysis_scope": "Public-only inverse of the fixed independent binary GRR channels; no extra source-data query.",
        "interval_scope": "95% simultaneous Hoeffding intervals for the two marginals, not the joint estimate.",
    }


def analyze_run(run_directory):
    """Use exactly the files exposed by the existing public writer."""
    from pathlib import Path
    path = Path(run_directory)
    public = pd.read_csv(path / "release_data.csv")
    allocation = pd.read_csv(path / "epsilon_allocation.csv")
    epsilon = allocation.set_index("feature")["epsilon"].to_dict()
    result = analyze_public_release(public, epsilon)
    result["run_id"] = path.name
    return result


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Analyze one approved public GRR run; no original data required.")
    parser.add_argument("run_directory")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(analyze_run(args.run_directory), indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
