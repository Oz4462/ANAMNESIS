# Conformal Theory Backing the Reuse Bound

This document derives the marginal-coverage guarantee that `ConformalCalibrator`
ships in every receipt. The point of the derivation is auditability: a
notified body should be able to follow it line by line.

## Setting

Let `X` be a user query and `Y_*(X)` be the answer a reasoning model would
produce de novo. Let `Y_anam(X)` be the answer Anamnesis composes from
retrieved prior reasoning steps. Define the non-conformity score

    S(X) := d(Y_*(X), Y_anam(X))

where `d` is `one_minus_cosine` on a fixed sentence-embedding space.

We observe `S_1, ..., S_n` from a calibration set of past queries where both
fresh and retrieved answers were computed, and a single test point
`S_{n+1}` from the same distribution.

## Exchangeability assumption

We assume `(S_1, ..., S_{n+1})` is exchangeable: the joint distribution is
invariant under any permutation of indices. This is weaker than iid; it suffices
for split-conformal to deliver a finite-sample coverage guarantee
(Vovk, Gammerman, Shafer 2005; Angelopoulos & Bates 2021).

In practice exchangeability holds when (a) the same model is used for both
fresh and retrieved comparisons during calibration and at test time, and
(b) the calibration window is updated continuously as the underlying model is
swapped or fine-tuned. The `MondrianCalibrator` enforces (a) at the group
level by giving each model/tenant its own calibration window.

## Threshold definition

Pick miscoverage level `alpha ∈ (0, 1)`. Define

    q_level := ⌈(n + 1)(1 - alpha)⌉ / n          (always in (0, 1])

    tau := the q_level-quantile (method='higher') of {S_1, ..., S_n}

## Guarantee

Under exchangeability, for any new score `S_{n+1}` from the same distribution,

    P[S_{n+1} ≤ tau]  ≥  1 - alpha

This is a marginal (over the calibration draw + the test draw) finite-sample
guarantee, distribution-free over the law of `S`. It does NOT depend on any
parametric model of S.

### Why the ⌈(n+1)(1 - alpha)⌉ / n correction matters

The naive plug-in `(1 - alpha)`-quantile of the empirical distribution
under-shoots coverage at finite `n`, because the test point itself is one of
`n + 1` rank-equivalent draws. Using the corrected index inflates the
threshold just enough to recover marginal coverage exactly.

See Angelopoulos & Bates 2021, Eq. (1), for the proof sketch.

## Empirical validation in this repo

`test_marginal_coverage_holds_across_alphas` runs 300 simulation rounds across
`alpha ∈ {0.05, 0.1, 0.2, 0.3}` on uniform `S` and verifies that the empirical
coverage stays above `1 - alpha - 0.02`. The 2% slack absorbs the Monte-Carlo
noise at 300 × 200 = 60000 test samples per alpha. Tighter slack is
recoverable by increasing the trial count.

`test_coverage_uniform_distribution`, `_beta_`, and `_normal_` do the same on
those three reference distributions individually.

## Mondrian (per-group) variant

`MondrianCalibrator` maintains an independent `ConformalCalibrator` per group
label. Coverage is preserved **per group** under within-group exchangeability.
We use this so a tenant running both `claude-opus-4-7` and `o3` gets a
per-model bound rather than a pooled one that would be loose on whichever
model has the higher fresh-vs-retrieved divergence.

## What the bound does NOT guarantee

- **Conditional coverage.** Marginal coverage averages over the input
  distribution. It does not promise coverage on any individual hard subset.
  Conditional-conformal extensions exist (Romano et al. 2019; Gibbs et al. 2023)
  and can be plugged into a future `ConditionalCalibrator` if a customer needs
  per-slice guarantees.
- **Causal validity.** The bound bounds semantic drift `d(fresh, retrieved)`.
  It does NOT bound business-loss from a bad reuse; the user should pick
  `alpha` based on their loss function, e.g. via a small empirical study.
- **Distributional drift.** Exchangeability breaks when the model changes
  silently. The continuous calibration loop fixed-window erases stale scores
  but cannot detect overnight provider-side changes; users should add their
  own monitoring on receipt-level coverage statistics over time.

## References

1. Vovk V., Gammerman A., Shafer G. (2005). *Algorithmic Learning in a Random
   World*. Springer.
2. Angelopoulos A. N., Bates S. (2021). *A Gentle Introduction to Conformal
   Prediction and Distribution-Free Uncertainty Quantification.*
   arXiv:2107.07511.
3. Romano Y., Patterson E., Candes E. J. (2019). *Conformalized Quantile
   Regression.* NeurIPS.
4. Gibbs I., Cherian J., Candes E. J. (2023). *Conformal Prediction with
   Conditional Guarantees.* arXiv:2305.12616.
