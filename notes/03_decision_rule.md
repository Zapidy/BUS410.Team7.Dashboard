# Decision Rule — Phase B Threshold

## Why AP, not PR-AUC ≥ 0.6

The user's voice memo aimed for "PR-AUC ≈ 0.6" as the bar for the influenceable-only model to stand alone. **That bar is unrealistic** for this target.

For a binary classifier on imbalanced data:
- **Random-baseline AP equals the positive rate.**
- `target_becomes_service_desert_h1` is built from the bottom decile of `n_cra_lenders` *conditional on not already being a desert*. Round 5 reports the resulting positive rate at **≈ 1.7%** of supervised rows.
- **Random-baseline AP ≈ 0.017.**
- Round 5's full-feature diagnostic (39 features incl. all ACS structural) achieves **AP 0.172, lift 9.25×**.

A 14-feature influenceable-only model hitting AP 0.6 would mean it beats Round 5's full-feature model by ~4×. That's not a realistic bar.

PR-AUC and Average Precision are mathematically equivalent in the limit; the user's "0.6" likely reflects intuition from a different (more balanced) classification regime, not the rare-event regime this target lives in.

## Reset thresholds

| Outcome | AP threshold | Lift over random | Action |
|---|---|---|---|
| **Strong** | AP ≥ 0.10 | ≥ 6× | Ship Model 2 standalone. Expand to Phase 2 (policy slider). |
| **Moderate** | 0.05 ≤ AP < 0.10 | 3×–6× | Run **both** fallback variants in Phase C; pick the more informative. |
| **Weak** | AP < 0.05 | < 3× | Run only Variant B (bolt-on) and report negatively. Drop slider. |

**Per-fold stability check** — require **≥ 6 of 8 folds to clear the AP threshold** to qualify for Strong / Moderate. This avoids pinning the verdict on COVID-distorted years (Round 5's F5–F8 already degrade to 0.79–0.83 AUC).

## Reporting alongside

For comparability with Round 5's headline 0.857 AUC, also report:
- Mean test ROC-AUC across 8 folds (with std-dev — flag if > 0.06).
- Top-100 precision, top-1,000 precision (Round 5: 70%, 42%).
- Brier score after isotonic calibration (Round 5: 0.0201).
- Per-state AP — flag any state with AP below random.

## Phase C — both fallback variants if Moderate

### Variant A — Directional overlay

`walk_forward_overlay.py`:
```
final_score = round5_prob × (1 + α × directional_sign × |model2_prob − model2_baseline|)
α ∈ {0.1, 0.25, 0.5}
```

`directional_sign` = sign of the residual between Model 2's calibrated prob and the peer-group baseline. `model2_baseline` = mean Model 2 prob within (year × peer_group).

Pick α that maximizes test-set lift while preserving Round 5's calibration (Brier degradation < 10%).

### Variant B — Bolt-on

`walk_forward_boltOn.py`:
- Train Round 5's full 39-feature set + the 14 influenceable.
- Same 8 folds, same XGBoost config.
- Report ΔAUC and ΔAP vs Round 5 baseline.
- Use **sklearn `permutation_importance` on val set, restricted to the 14 new features** — XGBoost gain importance is biased toward high-cardinality features and unreliable here.

### Comparison table (post-run)

| Metric | Round 5 baseline | Variant A | Variant B |
|---|---|---|---|
| Mean test AUC | 0.857 | _ | _ |
| Mean test AP | 0.172 | _ | _ |
| Top-100 precision | 70% | _ | _ |
| Brier (calibrated) | 0.0201 | _ | _ |
| Per-state AP min | _ | _ | _ |

To be filled in.

## Phase A results

To be filled in after `walk_forward_round7.py` runs.

| Fold | Train years | Val | Test | Test AUC | Test AP | Lift | Top-100 prec |
|---|---|---|---|---|---|---|---|
| F1 | 2009–2014 | 2015 | 2016–2017 | _ | _ | _ | _ |
| F2 | 2009–2015 | 2016 | 2017–2018 | _ | _ | _ | _ |
| F3 | 2009–2016 | 2017 | 2018–2019 | _ | _ | _ | _ |
| F4 | 2009–2017 | 2018 | 2019–2020 | _ | _ | _ | _ |
| F5 | 2009–2018 | 2019 | 2020–2021 | _ | _ | _ | _ |
| F6 | 2009–2019 | 2020 | 2021–2022 | _ | _ | _ | _ |
| F7 | 2009–2020 | 2021 | 2022–2023 | _ | _ | _ | _ |
| F8 | 2009–2021 | 2022 | 2023–2024 | _ | _ | _ | _ |
| **Mean** | | | | _ | _ | _ | _ |

Verdict: ___ (Strong / Moderate / Weak).
