# Synthetic hazardous-waste enterprise-year example

This is an illustrative third RUPA example for the four industries and four waste
types discussed in the research project. It is **not** a download from an
information-centre API, a transfer-manifest extract, or an empirical study of
Jing-Jin-Ji facilities. A single screenshot of an enterprise/management-plan
API informed the *names* of excluded metadata fields; it did not establish a
complete manifest schema, a public numerical range, a category codebook, or
permission to publish records.

The fixed public roster is `public_enterprise_period_id`. Each row represents
one synthetic enterprise in one fixed reporting year. The private-to-public ID
mapping is outside RUPA. Real `qyid` can encode location and must not be called
protected merely because other columns receive noise. One enterprise's many
manifests are aggregated into one row here; raw manifest-event publication is
not supported by the current fixed-roster, one-row-per-unit model.

## Reproduce

```powershell
python examples/hazardous_waste/generate_data.py
rupa-privacy validate --calibration examples/hazardous_waste/calibration.csv --release examples/hazardous_waste/release.csv --config examples/hazardous_waste/config_reproducibility.yaml
rupa-privacy run --calibration examples/hazardous_waste/calibration.csv --release examples/hazardous_waste/release.csv --config examples/hazardous_waste/config_reproducibility.yaml --output demo/runs
```

Separate seeds and non-overlapping `CAL-`/`REL-` rosters create 240 calibration
rows and 320 release rows by default. `confidential_cost_index` is present in
calibration only. The 18 released fields are 14 numerical columns perturbed by
the existing Laplace mechanism and four finite-domain categorical columns
perturbed by the existing GRR mechanism. Ten API-like metadata fields, including
`qyid`, `zzjgdm`, `dwmc`, `dwdz`, `lxr`, `lxrsj`, `gljhid`, and `year`, are not
released; `public_enterprise_period_id` alone is the public roster key.

## Generation assumptions

- Industry group is drawn from four demonstration labels. A Dirichlet draw
  splits each generated mass among four illustrative waste streams; the total
  is their sum.
- A second Dirichlet draw splits generation among transfer, on-site treatment,
  and retention for the next period. Transfer is split into cross-region and
  within-region quantities.
- Manifest counts are synthetic Poisson draws and are split using a binomial
  draw. Emergency counts are synthetic Poisson draws.
- The calibration-only cost index is a noisy combination of total mass,
  cross-region transfer, manifest count, emergency count, and plan status.
- Public bounds and category domains in the YAML are **declared teaching
  assumptions**, not inferred from release records or validated regulatory
  limits. The four linear equalities describe this generator, not real-world
  hazardous-waste law or a complete stock-flow accounting system.

The fixed total epsilon of 5 is split across many fields. More fields do not
improve privacy or utility automatically: per-field noise and category
distortion can be substantial. Noisy manifest counts can be fractional after
Laplace noise and projection; they are statistical estimates, not valid
operational manifest counts. RUPA reduces public equality residuals but does
not guarantee exact final physical consistency or operational correctness.

See `SCHEMA.md` for per-field meanings and the distinction between screenshot
fields, scenario assumptions, and actual public output. Production use requires
the complete authorized field dictionary, privacy-unit decision, public
bounds/domains, lawful source data, and a separate governance review.
