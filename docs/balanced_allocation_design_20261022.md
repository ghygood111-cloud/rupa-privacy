# Optional balanced numerical allocation

## Status and compatibility

The author explicitly authorized algorithm improvement after observing the legacy
allocation failure. The default remains `legacy_rupa`; its formulas and reference
release arrays are unchanged. `balanced_rupa` and `uniform` are opt-in numerical
strategies. Laplace, GRR, physical projection, adjacency, accounting, ledger,
production randomness and public-output filtering are unchanged.

The finding motivating this change was a calibration-only allocation: in the
hazardous-waste configuration, 3.396 of the 4.3 numerical budget went to one
low-association count field. NMI is an estimated association score; a near-zero
estimate is not proof that an attribute has no disclosure risk or that it should
receive almost all the budget.

## Defined surrogate problem

Let the numerical budget be E across d fields, with e0=E/d, z_j=epsilon_j/e0.
Normalize positive fitted utility weights into w_j. Define
q_j=(R_j+c)/sum(R+c), with fixed c>0. Solve:

```text
minimize  sum_j w_j / z_j^2 + (lambda/d) sum_j (z_j - 1)^2
subject to
          mean(z) = 1
          lower <= z_j <= upper
          sum_j q_j z_j^2 <= 1
```

The defaults c=0.05, lambda=0.1, lower=0.5 and upper=2 are explicit engineering
policy settings, fixed before evaluating the new strategy. They are not claimed
to be universally optimal. Fitting uses only independent calibration and public
configuration, never release rows or release truth errors.

The positive-weight objective is strictly convex. Its diagonal Hessian is
6*w_j/z_j^4 + 2*lambda/d > 0. The feasible set is convex and contains uniform
allocation. Thus the defined surrogate has a unique global minimizer. The solver
uses scaled shares and analytic gradients, and checks its result. Solver failure
or a failed budget/range/exposure check raises BudgetOptimizationError; there is
no silent fallback after a solver failure. Analytically uniform-only cases are
handled explicitly before numerical optimization.

The budget bounds imply epsilon_j/E lies between lower/d and upper/d. At d=14,
the default maximum is 14.29%, rather than the observed legacy 79% concentration.
Furthermore, sum(z)=d implies sum(z^2)>=d. Hence the smoothed-risk constraint gives
sum(R*z^2)<=sum(R), so the original risk-exposure surrogate cannot exceed uniform.
This is a property of a proxy, not an actual attack-success or stronger-DP theorem.

## Use

In an existing valid configuration add:

```yaml
privacy:
  numeric_budget_strategy: balanced_rupa
  numeric_risk_smoothing: 0.05
  numeric_stability_weight: 0.1
  numeric_min_uniform_fraction: 0.5
  numeric_max_uniform_multiple: 2.0
```

Keep all the other required configuration sections. The GUI exposes the strategy
under Configuration / Numerical budget allocation; changing it invalidates prior
validation/results and requires Validate before Run. Advanced settings remain in
the YAML editor. The old fixed-seed examples still select the legacy default.

## Evaluation boundary

`experiments/allocation_revision_20261022/protocol.json` fixes three synthetic
cases, budgets 1/5/20, both alpha 0 and 0.98, and 30 paired seeds. One case uses
new held-out rows from the unchanged hazardous-waste generator with a fixed seed;
its calibration stays unchanged. This is exploratory software research, not an
independent human deployment. All gains and regressions are retained, including
failure to improve over uniform or continued large task errors. Better allocation
cannot remove the information cost of releasing many bounded row-level attributes.
