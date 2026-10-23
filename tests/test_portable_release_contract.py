import numpy as np


def test_portable_weights_and_budget_contract(example_run):
    _, _, _, result = example_run
    utility = np.asarray(
        list(result.utility_result.utility_weights.values()), dtype=float
    )
    epsilon = np.asarray(list(result.allocation_result.epsilon.values()), dtype=float)

    assert np.all(np.isfinite(utility))
    assert np.all(utility >= 0.0)
    assert np.isclose(utility.sum(), 1.0, rtol=1e-10, atol=1e-12)
    assert np.all(np.isfinite(epsilon))
    assert np.all(epsilon > 0.0)
    assert np.isclose(
        epsilon.sum(),
        result.allocation_result.basic_composition_epsilon,
        rtol=1e-10,
        atol=1e-12,
    )


def test_portable_release_bounds_and_residual_contract(example_run):
    pipeline, _, _, result = example_run
    for name in pipeline.schema.numeric_columns:
        lower, upper = pipeline.schema.public_bounds[name]
        values = result.release_data[name].to_numpy(dtype=float)
        assert np.all(np.isfinite(values))
        assert np.all(values >= lower)
        assert np.all(values <= upper)

    states = result.physical_audit["states"]
    assert np.isfinite(states["noisy"]["nrms"])
    assert np.isfinite(states["full_projection"]["nrms"])
    assert states["full_projection"]["nrms"] <= states["noisy"]["nrms"] + 1e-12
