# Third-party notices

RUPA source code is licensed under BSD-3-Clause. Dependency packages and public
benchmark data retain their own licenses; the RUPA license does not relicense
them. This source release does not vendor scientific libraries, Python, browser
software, fonts, external paper PDFs, or a compiled Windows environment.

## Software dependencies

| Component | Role | License |
| --- | --- | --- |
| NumPy, SciPy, scikit-learn, pandas | Numerical/data processing | BSD-3-Clause; binary wheels may include additional notices |
| openpyxl, PyYAML | Input/configuration | MIT |
| diffprivlib 0.6.5 | Optional research total-query mechanism | MIT, as recorded in the installed distribution |
| Streamlit | Optional local interface | Apache-2.0 |
| Matplotlib | Optional paper figures | Matplotlib/PSF-based license; bundled resources retain their notices |
| pytest, pytest-cov | Test tools | MIT |
| certifi | Transitive HTTPS trust store | MPL-2.0; remains a separately licensed dependency |

Exact package versions, dependency closure and license-file hashes are recorded
by the release verification process. Dependencies installed by pip are separate
distributions: retain their license/NOTICE files when redistributing their source
or binaries. In particular, a future frozen Windows bundle requires a separate
component-license collection; this source/wheel release is not that bundle.
The dependency inventory includes license-file hashes. Legacy metadata marked
UNKNOWN for importlib-metadata, zipp and setuptools was checked against the
installed license texts (Apache-2.0, MIT and MIT respectively). Streamlit's
Apache-2.0 declaration was also checked against its official versioned source
license; its installed wheel did not list a separate license file in RECORD.

## Public data

### Ontario hazardous-waste registration coverage

Contains information licensed under the **Open Government Licence - Ontario**.

- Publisher: Ontario Ministry of the Environment, Conservation and Parks.
- Catalogue: https://data.ontario.ca/en/dataset/hazardous-waste-public-information
- Resource: 2002-2022 Generator Registration and Waste Classes.
- License: https://www.ontario.ca/page/open-government-licence-ontario
- Included derivatives: public row keys, two binary physical-state indicators,
  and a calibration-only count. Preparation drops original registration numbers,
  names and addresses; the keys are not an anonymity guarantee.
- Attribution, source digest, partition and derivative hashes:
  `examples/ontario_registration/provenance.json`.
- No Ontario endorsement or current-registration/compliance interpretation is
  claimed. The raw source download and catalogue cache are not distributed.

### UCI Concrete Compressive Strength

Yeh, I. (1998). *Concrete Compressive Strength* [Dataset]. UCI Machine Learning
Repository. https://doi.org/10.24432/C5PK67

- License: **Creative Commons Attribution 4.0 International (CC BY 4.0)**,
  https://creativecommons.org/licenses/by/4.0/.
- Source: https://archive.ics.uci.edu/dataset/165/concrete+compressive+strength
- The research fixture partitions the public measurements by recipe groups and
  creates disjoint calibration/release blocks. Preparation and hashes are in
  `experiments/task_statistics_20261022/external/provenance.json`.
- These derivatives remain CC BY 4.0, not BSD-3-Clause. They are public benchmark
  observations, not confidential enterprise data or five independent domains.

### Generated examples and requirements metadata

Official, hazardous-waste, water-treatment and third-party-reuse examples are
generated demonstration data, not real confidential industrial observations.
Their generation assumptions and source scripts are retained. The water example
is inspired by the UCI Water Treatment Plant domain but does not copy its rows.
The hazardous-waste field catalogue is requirements metadata supplied by the
copyright holder, not a real operational dataset or a working external API.

No third-party scientific paper PDF, downloaded executable, OS font, confidential
record, development transcript or browser cache is part of the source release.
