# Public linear constraints

The example uses only public linear equalities supported by the current RUPA
projection. These are semi-synthetic accounting identities used to test software
portability; they are not asserted to be exact laws for every real treatment plant.

1. Hydraulic outflow balance:
   `raw_inflow = treated_outflow + backwash_loss + sludge_water`.
2. Process-feed balance:
   `process_feed = treated_outflow + recycle_water`.
3. Electrical-energy balance:
   `total_energy = aeration_energy + pumping_energy`.

The constraint matrix, right-hand side, and tolerance are declared in each YAML
configuration. No coefficient is estimated from the release records. The software
does not support nonlinear products, inequalities, uncertain constraints, or a claim
that projection reconstructs an unobserved true plant state.

