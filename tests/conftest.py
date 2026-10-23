import pytest

from rupa_privacy import RUPAPipeline
from rupa_privacy.data import (
    example_adjacency_config,
    example_constraints,
    example_privacy_accounting_config,
    example_privacy_config,
    example_regulatory_prior,
    example_schema,
    generate_example_pair,
)


@pytest.fixture(scope="session")
def example_run():
    calibration, release = generate_example_pair()
    schema = example_schema()
    privacy = example_privacy_config()
    pipeline = RUPAPipeline(
        schema,
        privacy,
        example_constraints(),
        example_regulatory_prior(),
        example_adjacency_config(),
        example_privacy_accounting_config(),
    )
    result = pipeline.fit_transform(calibration, release)
    return pipeline, calibration, release, result
