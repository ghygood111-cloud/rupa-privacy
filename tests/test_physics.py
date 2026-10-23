import numpy as np


def test_all_physical_states_are_reported(example_run):
    _, _, _, result = example_run
    states = result.physical_audit["states"]
    assert set(states) == {
        "original_clipped_internal",
        "noisy",
        "full_projection",
        "interpolated",
        "final_clipped",
    }
    assert states["full_projection"]["rms"] < 1e-6
    assert states["interpolated"]["rms"] < states["noisy"]["rms"]
    assert result.physical_audit["repair_alpha"] == 0.98


def test_final_release_respects_all_public_bounds(example_run):
    pipeline, _, _, result = example_run
    for name in pipeline.schema.numeric_columns:
        lower, upper = pipeline.schema.public_bounds[name]
        assert np.all(result.release_data[name].to_numpy() >= lower)
        assert np.all(result.release_data[name].to_numpy() <= upper)


def test_interpolation_and_clipping_states_remain_distinct(example_run):
    _, _, _, result = example_run
    assert not result.projected_data.equals(result.repaired_data)
    assert not result.repaired_data.equals(result.release_data)
    assert "can reintroduce residual" in result.physical_audit["interpretation_note"]
