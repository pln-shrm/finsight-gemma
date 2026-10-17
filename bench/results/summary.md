# FinSight Benchmark Results (Measured)

Generated on: 2026-10-17 19:10:23
Suite: Synthetic Charts (`bench/synth`)
Sample count: 10

## 1. Lie Factor Detection Performance

| Metric | Score | Definition |
|---|---|---|
| **Precision** | **100.0%** | TP / (TP + FP) — avoidance of false accusations |
| **Recall** | **100.0%** | TP / (TP + FN) — rate of catching truncated charts |
| **F1 Score** | **1.000** | Harmonic mean of precision and recall |
| **True Positives** | 4 | Correctly flagged distorted charts |
| **False Positives** | 0 | Faithful charts incorrectly flagged |
| **True Negatives** | 6 | Correctly identified faithful / zero-baseline charts |
| **False Negatives** | 0 | Missed distorted charts |

## 2. Computer Vision Geometry Measurement

| Metric | Measured | Notes |
|---|---|---|
| **CV Measurement Success Rate** | **100.0%** | Percentage of charts where pixel heights matched expected bar count |
| **Mean Lie Factor Absolute Error** | **0.3278** | Difference between CV-measured LF and ground truth |
| **Mean Audit Latency** | **39.3 ms** | Per-chart OpenCV measurement + Lie Factor math |

## 3. Summary Notes
- **Zero-Baseline Faithfulness**: Zero-baseline charts ($y_{min} = 0$) correctly pass with Lie Factor = 1.0.
- **Secondary Axis Handling**: Dual-axis charts are safely classified as `UNSCORED` rather than reporting invalid Lie Factors.
- **Analytic Fallback**: When pixel segmentation encounters background artifacts or text overlaps, FinSight automatically falls back to the analytic axis model with a `CHART_CV_FAILED` flag.
