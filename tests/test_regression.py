import numpy as np
import pytest


pytestmark = pytest.mark.locked_regression


EXPECTED_RISK = np.array(
    [
        0.7731983608216372,
        0.7561969916196246,
        0.6728127501775261,
        0.7078070368170307,
        0.6884388424549162,
        0.20335499632031473,
        0.08324374155181266,
        0.5245161644336732,
        0.006545996968449315,
        0.0065752297994195455,
    ]
)
EXPECTED_UTILITY = np.array(
    [
        0.09590876283643993,
        0.08350606239461035,
        0.19892322574214322,
        0.1330513519128109,
        0.059170843810086436,
        0.1381765884458476,
        0.17233781340105253,
        0.05449104674209121,
        0.00767556112317894,
        0.05675874359173908,
    ]
)
EXPECTED_EPSILON = np.array(
    [
        0.37473259113932933,
        0.36692627888008406,
        0.46040208882943834,
        0.4148043925361961,
        0.35438497828773063,
        0.7437453917032074,
        1.4939199932806462,
        0.3910842853433671,
        0.047670608536381526,
        0.3523293914636185,
    ]
)


def test_default_risk_utility_and_allocation_match_legacy(example_run):
    _, _, _, result = example_run
    risk = np.array(list(result.risk_result.single_scores.values()))
    utility = np.array(list(result.utility_result.utility_weights.values()))
    epsilon = np.array(list(result.allocation_result.epsilon.values()))
    np.testing.assert_allclose(risk, EXPECTED_RISK, rtol=0.0, atol=1e-12)
    np.testing.assert_allclose(utility, EXPECTED_UTILITY, rtol=0.0, atol=1e-12)
    np.testing.assert_allclose(epsilon, EXPECTED_EPSILON, rtol=0.0, atol=1e-10)
    assert result.risk_result.joint_penalty["runtime"] == result.risk_result.joint_penalty["dust"]
    assert np.isclose(result.risk_result.joint_penalty["runtime"], 0.0006786573050211742)


def test_default_noise_and_final_repair_match_legacy(example_run):
    _, _, _, result = example_run
    expected_noisy = np.array(
        [
            [7000.0, 39.98168746167653, 5000.0],
            [1000.0, 20.0, 35000.0],
            [1000.0, 180.0, 35000.0],
        ]
    )
    actual_noisy = result.noisy_data.loc[
        :2, ["wastewater", "cod", "electricity"]
    ].to_numpy()
    np.testing.assert_allclose(actual_noisy, expected_noisy, rtol=0.0, atol=1e-12)

    expected_repaired = np.array(
        [
            [3760.617006053986, 91.31505890058321, 18053.472757292497],
            [4697.635438157624, 117.34088595394046, 23894.88647020309],
            [5711.276355297309, 145.8819088824327, 28921.205067589963],
        ]
    )
    actual_repaired = result.release_data.loc[
        :2, ["wastewater", "cod", "electricity"]
    ].to_numpy()
    np.testing.assert_allclose(actual_repaired, expected_repaired, rtol=0.0, atol=1e-9)


def test_fixed_seed_is_reproducible(example_run):
    pipeline, _, release, first = example_run
    second = pipeline.transform(release)
    for name in first.release_data.columns:
        np.testing.assert_array_equal(first.release_data[name], second.release_data[name])
