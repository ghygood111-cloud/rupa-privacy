# Field contract for the synthetic hazardous-waste example

**Provenance:** Every row is produced by `generate_data.py`. The enterprise
metadata names below were visible in one author-provided API screenshot. The
business quantities, labels, public bounds, category domains, and equations
are **illustrative design choices**, not verified fields or values supplied by
the information centre.

## Released numerical estimates

| Field | Meaning | Unit | Declared public bound | Origin |
|---|---|---|---|---|
| `generated_total_t` | Generated mass, four modeled streams only | t/year | 0-1600 | synthetic assumption |
| `waste_acid_t` | Modeled waste-acid mass | t/year | 0-1600 | synthetic assumption |
| `distillation_residue_t` | Modeled distillation-residue mass | t/year | 0-1600 | synthetic assumption |
| `incineration_fly_ash_t` | Modeled incineration-fly-ash mass | t/year | 0-1600 | synthetic assumption |
| `surface_treatment_waste_t` | Modeled surface-treatment-waste mass | t/year | 0-1600 | synthetic assumption |
| `transferred_total_t` | Mass transferred in the period | t/year | 0-1600 | synthetic assumption |
| `cross_region_transferred_t` | Transferred mass crossing the model region | t/year | 0-1600 | synthetic assumption |
| `within_region_transferred_t` | Transferred mass staying in the model region | t/year | 0-1600 | synthetic assumption |
| `on_site_treated_t` | Generated mass treated on site | t/year | 0-1600 | synthetic assumption |
| `retained_for_next_period_t` | Generated mass retained in the model | t/year | 0-1600 | synthetic assumption |
| `manifest_total_count` | Number of modeled transfer manifests | count/year | 0-180 | synthetic assumption |
| `cross_region_manifest_count` | Modeled cross-region manifests | count/year | 0-180 | synthetic assumption |
| `within_region_manifest_count` | Modeled within-region manifests | count/year | 0-180 | synthetic assumption |
| `emergency_response_count` | Modeled response events | count/year | 0-10 | synthetic assumption |

Counts are treated as numerical statistical estimates by the current core;
their published values need not be integers. They must not be used as formal
transaction or compliance records.

## Released finite categories

| Field | Meaning | Public demonstration domain | Origin |
|---|---|---|---|
| `industry_group` | Broad industry label | `steel_rolling`, `coking`, `metal_surface_treatment`, `waste_incineration` | project brief, synthetic labels |
| `dominant_waste_type` | Largest modeled waste stream | `waste_acid`, `distillation_residue`, `incineration_fly_ash`, `surface_treatment_waste` | project brief, synthetic labels |
| `primary_handling_route` | Largest modeled transfer/on-site/retention fraction | `transfer`, `on_site`, `retained` | synthetic assumption |
| `emergency_plan_status` | Example plan-status label | `current`, `review_due` | synthetic assumption |

These are labels, not official GB industry or waste codes. The finite domains
are declared in `config_reproducibility.yaml` before release; RUPA does not
learn them from the private release table. GRR may change a label, and the
final label need not remain logically consistent with noisy numerical fields.

## Roster, excluded metadata, and target

| Field | Meaning in the screenshot or example | Release treatment |
|---|---|---|
| `public_enterprise_period_id` | Synthetic public roster surrogate for one enterprise-year | Included unchanged as the public unit ID; not a protected field |
| `qyid` | Enterprise ID shown in the screenshot; the real ID may encode district | Synthetic placeholder only, excluded |
| `zzjgdm` | Unified social credit code in the screenshot | Synthetic placeholder only, excluded |
| `dwmc` | Unit name in the screenshot | Synthetic placeholder only, excluded |
| `dwszqxz` | Administrative district code in the screenshot | Synthetic placeholder only, excluded |
| `dwdz` | Detailed address in the screenshot | Non-address placeholder only, excluded |
| `hylbdm` | Industry code in the screenshot | Synthetic nonstandard placeholder only, excluded |
| `lxr` | Contact person in the screenshot | `not_collected` placeholder only, excluded |
| `lxrsj` | Contact phone in the screenshot | `not_collected` placeholder only, excluded |
| `gljhid` | Management-plan query ID visible in the screenshot | Synthetic placeholder only, excluded |
| `year` | Management-plan query year visible in the screenshot | Fixed demonstration context, excluded |
| `confidential_cost_index` | Calibration-only synthetic sensitive target | Not in release input or public output |

The screenshot's `qyid`, `zzjgdm`, `dwmc`, `dwszqxz`, `dwdz`, `hylbdm`, `lxr`,
and `lxrsj` are enterprise-information response fields. `gljhid` and `year`
appear in a management-plan query request. The screenshot does **not** prove
these fields occur in a transfer-manifest response. No real identifier,
contact detail, address, or API credential is distributed with this example.

## Public synthetic equalities

```text
generated_total_t = waste_acid_t + distillation_residue_t
                  + incineration_fly_ash_t + surface_treatment_waste_t
transferred_total_t = cross_region_transferred_t + within_region_transferred_t
generated_total_t = transferred_total_t + on_site_treated_t
                  + retained_for_next_period_t
manifest_total_count = cross_region_manifest_count + within_region_manifest_count
```

These equalities hold by construction before perturbation. They omit imports,
exports, beginning inventory, carry-over, and many other operational details.
Do not apply them to real data without independent domain validation. Current
RUPA supports only public linear equalities and may still leave final residuals.
