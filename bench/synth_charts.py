"""Synthetic chart generator with exact mathematical ground truth.

Generates seeded matplotlib bar charts with varied axis_min settings,
printed data labels, and optional secondary axes.
Saves ground-truth JSON including Lie Factor computed from the axis model.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from finsight.lie_factor import lie_factor_from_axis


def generate_synthetic_charts(
    n: int = 20,
    out_dir: Path | str = "bench/synth",
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Generate *n* synthetic bar charts with exact ground-truth JSON."""
    random.seed(seed)
    out_path = Path(out_dir)
    images_dir = out_path / "images"
    labels_dir = out_path / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    metrics = [
        "Revenue ($M)", "Operating Income ($M)", "EBITDA ($M)",
        "Free Cash Flow ($M)", "Gross Profit ($M)", "ARR ($M)",
    ]
    time_series = [
        ["2021", "2022", "2023", "2024"],
        ["Q1", "Q2", "Q3", "Q4"],
        ["FY22", "FY23", "FY24"],
        ["2020", "2021", "2022", "2023", "2024"],
        ["Segment A", "Segment B", "Segment C"],
    ]

    index: list[dict[str, Any]] = []

    for i in range(1, n + 1):
        chart_id = f"chart_{i:03d}"
        labels = random.choice(time_series)
        n_bars = len(labels)
        metric = random.choice(metrics)
        title = f"{metric} Comparison"

        # Generate realistic monotonically increasing or slightly fluctuating positive values
        start_val = random.uniform(80.0, 300.0)
        values: list[float] = [round(start_val, 1)]
        for _ in range(n_bars - 1):
            growth = random.uniform(0.05, 0.35)
            values.append(round(values[-1] * (1.0 + growth), 1))

        min_val = min(values)

        # Decide variant
        # ~40% zero-baseline (faithful), ~45% truncated baseline (distorted), ~15% secondary axis
        variant_roll = random.random()
        has_secondary_axis = False

        if variant_roll < 0.40:
            axis_min = 0.0
            chart_type = "bar"
        elif variant_roll < 0.85:
            trunc_fraction = random.choice([0.60, 0.75, 0.85, 0.90])
            axis_min = round(min_val * trunc_fraction, 1)
            chart_type = "bar"
        else:
            axis_min = 0.0
            chart_type = "bar"
            has_secondary_axis = True

        # Calculate true lie factor from axis model
        pairs = []
        for j in range(len(values) - 1):
            lf_res = lie_factor_from_axis(values[j], values[j + 1], axis_min)
            pairs.append({
                "from": labels[j],
                "to": labels[j + 1],
                **asdict(lf_res),
            })

        should_flag = any(p["verdict"] == "distorted" for p in pairs) if not has_secondary_axis else False

        # Render chart with matplotlib
        fig, ax = plt.subplots(figsize=(6, 4), dpi=120)
        x_indices = list(range(n_bars))
        color = random.choice(["#1f77b4", "#2ca02c", "#4c72b0", "#34495e"])
        bars = ax.bar(x_indices, values, color=color, width=0.55, edgecolor="none")

        ax.set_xticks(x_indices)
        ax.set_xticklabels(labels, fontsize=10)
        ax.set_ylim(bottom=axis_min, top=max(values) * 1.15)
        ax.set_title(title, fontsize=12, pad=12, weight="bold")
        ax.set_ylabel(metric, fontsize=10)
        ax.grid(axis="y", linestyle="--", alpha=0.4)

        # Print values above bars
        for bar, val in zip(bars, values, strict=False):
            h = bar.get_height()
            ax.annotate(
                f"{val:,.1f}",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
            )

        if has_secondary_axis:
            ax2 = ax.twinx()
            sec_vals = [round(v * 0.15, 1) for v in values]
            ax2.plot(x_indices, sec_vals, color="#e74c3c", marker="o", linewidth=2, label="Margin %")
            ax2.set_ylabel("Margin %", fontsize=10, color="#e74c3c")
            ax2.tick_params(axis="y", labelcolor="#e74c3c")

        plt.tight_layout()
        img_file = images_dir / f"{chart_id}.png"
        fig.savefig(img_file, format="png", facecolor="white")
        plt.close(fig)

        meta: dict[str, Any] = {
            "id": chart_id,
            "chart_type": chart_type,
            "title": title,
            "axis_min": axis_min,
            "values": values,
            "labels": labels,
            "has_secondary_axis": has_secondary_axis,
            "true_lie_factor_pairs": pairs,
            "should_flag": should_flag,
            "image_path": str(img_file.relative_to(out_path.parent)),
        }

        label_file = labels_dir / f"{chart_id}.json"
        label_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        index.append(meta)

    index_file = out_path / "index.json"
    index_file.write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"Generated {n} synthetic charts in {out_path} (Images: {images_dir}, Labels: {labels_dir})")
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic charts with ground truth")
    parser.add_argument("--n", type=int, default=20, help="Number of charts to generate")
    parser.add_argument("--out-dir", type=str, default="bench/synth", help="Output directory")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()
    generate_synthetic_charts(n=args.n, out_dir=args.out_dir, seed=args.seed)
