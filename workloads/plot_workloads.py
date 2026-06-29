#!/usr/bin/env python3
"""Render load shape CSV files as JPG images."""

import sys
import glob
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


def plot_csv(csv_path: Path, output_dir: Path):
    values = [float(line.strip()) for line in csv_path.read_text().splitlines() if line.strip()]
    time = list(range(len(values)))

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(time, values, linewidth=1.5, color="#1f77b4")
    ax.fill_between(time, values, alpha=0.15, color="#1f77b4")

    ax.set_title(csv_path.stem, fontsize=14, fontweight="bold")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Users")
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.set_xlim(0, len(values) - 1)
    ax.set_ylim(0, max(values) * 1.1)

    fig.tight_layout()
    out = output_dir / f"{csv_path.stem}.jpg"
    fig.savefig(out, dpi=150, format="jpeg", bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def main():
    paths = sys.argv[1:] if len(sys.argv) > 1 else sorted(glob.glob("*.csv"))
    if not paths:
        print("No CSV files found.")
        sys.exit(1)

    output_dir = Path(".")
    for p in paths:
        plot_csv(Path(p), output_dir)


if __name__ == "__main__":
    main()