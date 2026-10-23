# Ontario hazardous-waste registration coverage example

This is an additional, public-data application of the unchanged RUPA API.
It evaluates registration coverage, not waste tonnage, generation rates,
transport flows, compliance, or enterprise-level confidentiality.

Source: Ontario Ministry of the Environment, Conservation and Parks,
**Hazardous Waste Public Information**, resource **2002-2022 Generator
Registration and Waste Classes**.

- Catalogue: https://data.ontario.ca/en/dataset/hazardous-waste-public-information
- Licence: https://www.ontario.ca/page/open-government-licence-ontario
- Attribution: Contains information licensed under the Open Government Licence - Ontario.
- No endorsement by Ontario is claimed. This data notice does not license RUPA's code.

The preparation script groups all source records by the literal registration
number, preserves leading zeros, and creates exactly one row per registration.
`handles_liquid` and `handles_solid` indicate whether any registered class has
that physical state. Both public domains are declared as `['no', 'yes']`.
The calibration-only target is the number of distinct registered waste classes;
it is a public complexity proxy, not a measured confidential cost or production
target. Original names, addresses, and registration numbers are not included in
the prepared tables. The benchmark roster uses reproducible public row keys;
these keys are not an anonymization guarantee.

A deterministic SHA-256 partition of registration numbers separates public
calibration units from public evaluation units before fitting. This is a
reproducibility demonstration on already public data, not a new confidential
release. Repeated seeded outputs are research replicates; they must not be
published together for confidential data without cumulative accounting.

Only categorical GRR is exercised. Numerical allocation, Laplace perturbation,
and physical repair are not evaluated by this example. Existing mixed-field
examples remain separate and their unfavorable results are not replaced.

## Prepare and reproduce

From the repository root, in the supported, installed Python environment:

```powershell
python examples/ontario_registration/prepare.py
rupa-privacy validate --calibration examples/ontario_registration/calibration.csv --release examples/ontario_registration/release.csv --config examples/ontario_registration/config_reproducibility.yaml
rupa-privacy run --calibration examples/ontario_registration/calibration.csv --release examples/ontario_registration/release.csv --config examples/ontario_registration/config_reproducibility.yaml --output examples/ontario_registration/runs --run-id ontario_example
rupa-privacy inspect-run examples/ontario_registration/runs/ontario_example --sensitive-target registered_class_count
python examples/ontario_registration/analysis.py examples/ontario_registration/runs/ontario_example
python -m pytest --junitxml=experiments/softwarex_application_case_20261020/pytest_rerun.xml
python experiments/softwarex_application_case_20261020/run_case.py --output experiments/softwarex_application_case_20261020/results_rerun --pytest-xml experiments/softwarex_application_case_20261020/pytest_rerun.xml
```

The raw 76 MB source file is cached locally under `_source_cache/`, not
redistributed in the manuscript. Preparation requires internet access once;
the experiment uses the prepared local tables without network access.
Inspect `provenance.json` for the actual source digest, row counts, exclusions,
split method, public domains, and prepared-table hashes.
Both the CLI run ID and matrix output directory must be unused; use a new
suffix for later executions. The protocol is not selected from release errors.

The downstream `analysis.py` reads approved public CSVs and declared field
epsilons. It reports both raw randomized-response frequencies and the standard
GRR frequency decoder `(observed_frequency - q) / (p - q)`. The latter is
ordinary downstream analysis, not a change to RUPA's perturbation or allocation.
Unclipped decoded estimates and simultaneous Hoeffding intervals are retained;
plot clipping is labeled separately. Ground-truth comparisons are only possible
here because the source is already public.

"No" means no matching state label was recorded in this historical resource,
not proof that a facility never handles that state. Missing state labels are
retained and counted in provenance. The resource has no usable annual date
field: no annual trend or current-registration interpretation is made.
