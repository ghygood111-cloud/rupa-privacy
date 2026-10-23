# NMI preprocessing reproducibility

RUPA 0.1.x computes numerical NMI labels with scikit-learn quantile binning using
explicit parameters:

```text
encode="ordinal"
strategy="quantile"
subsample=None
random_state=0
```

`subsample=None` intentionally uses all calibration rows. This avoids the
scikit-learn default randomized subsample for tables above 200,000 rows. The
fixed `random_state` documents the intended deterministic policy even though it
is not used when subsampling is disabled.

RUPA disables stochastic subsampling for NMI calibration in the supported
release to preserve deterministic reproducibility. Large calibration tables
therefore require additional memory and computation time.

The 0.1.x dependency contract is `scikit-learn>=1.2,<1.7`. These versions do not
expose `quantile_method` in `KBinsDiscretizer`. Supporting scikit-learn 1.7 or
newer requires an explicit quantile-method decision and a complete legacy
regression review; an upgrade must not silently inherit a new default.

For every numerical target, numerical field, and numerical joint pair, RUPA
records requested and effective bin counts. Tied or sparse values may produce
fewer effective bins. Such collapse is diagnostic rather than automatically
fatal: mild and severe collapse produce warnings, while a fully constant target
is rejected separately by calibration-target validation.
