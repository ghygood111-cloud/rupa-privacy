# Public schema and task boundary

| Field | Role | Unit/domain | Source or definition |
|---|---|---|---|
| public_registration_id | Public fixed roster | ONT- plus 8-digit row ordinal | Literal registration identifiers sorted lexically; one row per identifier |
| handles_liquid | Protected category | no, yes | Any source row for that registration has PHYSICAL_STATE=Liquid (case-insensitive, trimmed) |
| handles_solid | Protected category | no, yes | Any source row for that registration has PHYSICAL_STATE=Solid (case-insensitive, trimmed) |
| registered_class_count | Calibration target only | Distinct recorded waste class count | WASTE_CLASS_CODE distinct count within the registration; public complexity proxy |

The binary domains are set by the query definition, not sample categories.
There are no numerical released fields, numerical public bounds, or physical
equalities in this focused categorical application. Empty constraints are
intentional and their zero residuals are not a physical-accuracy result.

The fixed-roster privacy unit is a registration record after aggregation.
This is not add/remove privacy, and not a claim about a company's full history
or every registration belonging to the same legal enterprise.

The source inventory combines historical registrations. Repeated waste classes
and state labels are reduced by set membership; no mass, flow, capacity,
production, or annual activity information is inferred.

Public calibration partitions already public records. The target's numerical
encoding satisfies the current API and measures recorded class complexity; it
does not turn these records into secret cost data or certify target protection.
