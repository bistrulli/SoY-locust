"""Figures (matplotlib) + LaTeX report → PDF for the white paper.

Reads ``results/summary.csv`` (via :mod:`bench.aggregate`) and the per-run series
(``capacity/*.csv``, ``scaling/*.csv``) then produces, in ``<results>/report/``:

  * vectorial PDF figures (energy/request, p95 latency, scaling
    behavior, capacity curves, language impact);
  * ``report.tex`` + a summary table;
  * ``report.pdf`` (compiled if latexmk/pdflatex is present).

Usage: ``python run_experiment.py report``.
"""
from __future__ import annotations

import glob
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .aggregate import aggregate

logger = logging.getLogger(__name__)

NUM_COLS = [
    "duration_s", "rapl_package_J", "rapl_cores_J", "rapl_dram_J", "rapl_host_J",
    "wall_energy_J", "watts_peak", "wall_over_rapl", "cpu_pct_avg", "cpu_pct_peak",
    "mem_used_mi_avg", "mem_used_mi_peak", "replicas_mean", "replicas_max",
    "replica_seconds", "scale_actions", "cpu_util_mean", "requests", "failures",
    "fail_ratio", "rps", "rt_avg_ms", "rt_p95_ms", "rt_p99_ms", "users_max",
    "knee_rps", "breaking_rps", "breaking_users", "max_rps",
    "wall_J_per_req", "rapl_package_J_per_req",
]

CTRL_ORDER = ["none", "manual", "manual-sched", "uopt", "hpa", "openclass"]


# =============================================================================
# Loading
# =============================================================================

def load_summary(results_root: str) -> pd.DataFrame:
    aggregate(results_root)  # (re)generates summary.csv
    path = Path(results_root) / "summary.csv"
    df = pd.read_csv(path)
    for c in NUM_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _ctrl_cat(df: pd.DataFrame) -> pd.DataFrame:
    present = [c for c in CTRL_ORDER if c in set(df["controller"])]
    extra = [c for c in df["controller"].unique() if c not in CTRL_ORDER]
    df = df.copy()
    df["controller"] = pd.Categorical(df["controller"], present + extra, ordered=True)
    return df.sort_values("controller")


def _save(fig, outdir: Path, name: str) -> str:
    p = outdir / name
    fig.tight_layout()
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    logger.info("figure: %s", p.name)
    return p.name


# =============================================================================
# Figures
# =============================================================================

def fig_metric_by_controller(df: pd.DataFrame, outdir: Path, col: str, ylabel: str,
                             name: str) -> Optional[str]:
    sub = df[df[col].notna()]
    if sub.empty:
        return None
    g = _ctrl_cat(sub).groupby(["infra", "controller"], observed=True)[col].mean().reset_index()
    infras = list(g["infra"].unique())
    ctrls = [c for c in CTRL_ORDER if c in set(g["controller"])] + \
            [c for c in g["controller"].unique() if c not in CTRL_ORDER]
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(infras))
    w = 0.8 / max(1, len(ctrls))
    for i, c in enumerate(ctrls):
        vals = [g[(g.infra == inf) & (g.controller == c)][col].mean() for inf in infras]
        vals = [0 if pd.isna(v) else v for v in vals]
        ax.bar(x + i * w, vals, w, label=str(c))
    ax.set_xticks(x + w * (len(ctrls) - 1) / 2)
    ax.set_xticklabels(infras, rotation=10)
    ax.set_ylabel(ylabel)
    ax.set_title(ylabel + " by controller")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(axis="y", alpha=0.3)
    return _save(fig, outdir, name)


def fig_language_impact(df: pd.DataFrame, outdir: Path) -> Optional[str]:
    sub = df[df["infra"] == "microservices-demo"].copy()
    sub = sub[sub["variant"].notna() & (sub["variant"] != "")]
    if sub["variant"].nunique() < 2:
        return None
    metrics = [("wall_J_per_req", "Wall energy / request (J)"),
               ("rt_p95_ms", "p95 latency (ms)"),
               ("breaking_rps", "Breaking throughput (req/s)")]
    metrics = [(c, l) for c, l in metrics if c in sub and sub[c].notna().any()]
    if not metrics:
        return None
    fig, axes = plt.subplots(1, len(metrics), figsize=(4.5 * len(metrics), 4))
    if len(metrics) == 1:
        axes = [axes]
    order = ["node", "go", "python", "java", "csharp"]
    for ax, (col, lab) in zip(axes, metrics):
        g = sub.groupby("variant", observed=True)[col].mean()
        langs = [v for v in order if v in g.index] + [v for v in g.index if v not in order]
        ax.bar(langs, [g[v] for v in langs], color="tab:blue")
        ax.set_title(lab)
        ax.set_ylabel(lab)
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(axis="x", rotation=20)
    fig.suptitle("Impact of currencyservice language (Online Boutique)")
    return _save(fig, outdir, "fig_language_impact.pdf")


def _parse_tag(tag: str) -> Dict[str, str]:
    parts = tag.split("__")
    keys = ["infra", "controller", "variant", "loadshape", "rep"]
    return {k: parts[i] if i < len(parts) else "" for i, k in enumerate(keys)}


def fig_capacity_curves(results_root: str, outdir: Path) -> Optional[str]:
    files = glob.glob(str(Path(results_root) / "*" / "capacity" / "*.csv"))
    if not files:
        return None
    # group by infra; failure-rate vs offered-throughput curve, per controller
    byinfra: Dict[str, list] = {}
    for f in files:
        tag = Path(f).parent.parent.name
        meta = _parse_tag(tag)
        byinfra.setdefault(meta["infra"], []).append((meta, f))
    infras = sorted(byinfra)
    fig, axes = plt.subplots(1, len(infras), figsize=(5.2 * len(infras), 4), squeeze=False)
    drew = False
    for ax, inf in zip(axes[0], infras):
        for meta, f in byinfra[inf]:
            try:
                d = pd.read_csv(f)
            except Exception:
                continue
            if d.empty or "users" not in d:
                continue
            label = meta["controller"] + (f"/{meta['variant']}" if meta["variant"] not in ("", "default", "node") else "")
            ax.plot(d["users"], d["fail_ratio_inst"] * 100, marker=".", label=label)
            drew = True
        ax.axhline(2, ls="--", color="grey", lw=0.8)
        ax.set_title(f"Capacity — {inf}")
        ax.set_xlabel("Offered throughput (req/s)")
        ax.set_ylabel("Failure rate (%)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    if not drew:
        plt.close(fig)
        return None
    return _save(fig, outdir, "fig_capacity_curves.pdf")


def fig_scaling_timeline(results_root: str, outdir: Path) -> Optional[str]:
    files = glob.glob(str(Path(results_root) / "*" / "scaling" / "*.csv"))
    if not files:
        return None
    # one replicas(t) curve per controller (first run encountered of each)
    seen = set()
    series = []
    for f in sorted(files):
        meta = _parse_tag(Path(f).parent.parent.name)
        key = (meta["infra"], meta["controller"], meta["variant"])
        if key in seen:
            continue
        try:
            d = pd.read_csv(f)
        except Exception:
            continue
        if d.empty or "elapsed_s" not in d:
            continue
        seen.add(key)
        series.append((meta, d))
    if not series:
        return None
    infras = sorted({m["infra"] for m, _ in series})
    fig, axes = plt.subplots(1, len(infras), figsize=(5.2 * len(infras), 4), squeeze=False)
    for ax, inf in zip(axes[0], infras):
        for meta, d in series:
            if meta["infra"] != inf:
                continue
            lab = meta["controller"] + (
                f"/{meta['variant']}" if meta["variant"] not in ("", "default", "node") else "")
            ax.step(d["elapsed_s"], d["replicas_cur"], where="post", label=lab)
        ax.set_title(f"Scaling — {inf}")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Replicas")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    return _save(fig, outdir, "fig_scaling_timeline.pdf")


# =============================================================================
# Summary table + LaTeX
# =============================================================================

def _summary_table(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["rt_p95_ms", "rps", "wall_J_per_req", "rapl_package_J_per_req",
            "replicas_mean", "knee_rps", "breaking_rps"]
    cols = [c for c in cols if c in df.columns]
    g = _ctrl_cat(df).groupby(["infra", "controller", "variant"], observed=True)[cols].mean()
    g = g.reset_index().round(3)
    # labels without underscore (otherwise LaTeX breaks outside math mode)
    labels = {
        "infra": "Infra", "controller": "Controller", "variant": "Variant",
        "rt_p95_ms": "p95 (ms)", "rps": "RPS", "wall_J_per_req": "Wall J/req",
        "rapl_package_J_per_req": "RAPL J/req", "replicas_mean": "Repl. mean",
        "knee_rps": "Knee r/s", "breaking_rps": "Break r/s",
    }
    return g.rename(columns=labels)


def _tex_escape(s: str) -> str:
    for a, b in [("\\", r"\textbackslash{}"), ("_", r"\_"), ("%", r"\%"),
                 ("&", r"\&"), ("#", r"\#")]:
        s = str(s).replace(a, b)
    return s


def build_tex(df: pd.DataFrame, figs: Dict[str, Optional[str]], outdir: Path,
              date: str = "") -> Path:
    n_runs = len(df)
    infras = ", ".join(sorted(df["infra"].dropna().unique()))
    ctrls = ", ".join(sorted(df["controller"].dropna().unique()))
    table = _summary_table(df)
    try:
        table_tex = table.to_latex(index=False, na_rep="--", longtable=True, escape=True,
                                   float_format=lambda x: f"{x:.3g}")
    except Exception:
        table_tex = "\\emph{Table unavailable.}"

    def block(key, caption):
        name = figs.get(key)
        if not name:
            return ""
        return ("\\begin{figure}[H]\\centering\n"
                f"\\includegraphics[width=\\linewidth]{{{name}}}\n"
                f"\\caption{{{caption}}}\\end{{figure}}\n")

    parts = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=2.2cm]{geometry}",
        r"\usepackage{graphicx,booktabs,float,longtable,lmodern,hyperref}",
        r"\usepackage[T1]{fontenc}\usepackage[utf8]{inputenc}",
        r"\title{SoY-locust --- Autoscaling \& energy comparison}",
        r"\author{\texttt{bench/} harness}",
        (r"\date{%s}" % (date or r"\today")),
        r"\begin{document}\maketitle",
        r"\section{Methodology}",
        (f"Comparison of {len(df['controller'].dropna().unique())} scaling strategies "
         f"({_tex_escape(ctrls)}) across the {_tex_escape(infras)} infrastructures, "
         f"under \\emph{{constant offered throughput}} (\\texttt{{constant\\_throughput}}) and "
         f"identical actuation (\\texttt{{docker compose --scale}}). {n_runs} aggregated run(s). "
         r"Energy measured via RAPL (Scaphandre, CPU package) and a wall-plug wattmeter (Tasmota); "
         r"resources via \texttt{docker stats}. The wall/RAPL ratio separates the CPU cost from the rest."),
        r"\section{Energy}",
        block("energy_per_req", "Wall energy per request, by controller and infrastructure."),
        block("rapl_per_req", "RAPL energy (CPU package) per request."),
        r"\section{Performance}",
        block("latency", "p95 latency by controller and infrastructure."),
        r"\section{Scaling behavior}",
        block("scaling", "Replica count over time, by controller."),
        r"\section{Capacity (limits)}",
        block("capacity", "Failure rate as a function of offered throughput; the breaking point "
                          "is the throughput where the failure rate exceeds 2\\,\\% (dashed line)."),
        block("knee", "Maximum sustained throughput (knee) by controller."),
        r"\section{Language impact}",
        block("language", "Energy/request, latency and breaking throughput by "
                          "\\texttt{currencyservice} implementation language (Online Boutique)."),
        r"\section{Summary table}",
        r"\footnotesize",
        table_tex,
        r"\end{document}",
    ]
    tex = "\n".join(p for p in parts if p)
    tex_path = outdir / "report.tex"
    tex_path.write_text(tex)
    return tex_path


def compile_pdf(tex_path: Path) -> Optional[Path]:
    outdir = tex_path.parent
    tool = shutil.which("latexmk") or shutil.which("pdflatex")
    if not tool:
        logger.warning("No LaTeX (latexmk/pdflatex) → PDF not compiled.")
        return None
    if tool.endswith("latexmk"):
        cmd = [tool, "-pdf", "-interaction=nonstopmode", "-halt-on-error", tex_path.name]
    else:
        cmd = [tool, "-interaction=nonstopmode", "-halt-on-error", tex_path.name]
    for _ in range(2 if tool.endswith("pdflatex") else 1):
        r = subprocess.run(cmd, cwd=str(outdir), capture_output=True, text=True)
    pdf = tex_path.with_suffix(".pdf")
    if pdf.exists():
        logger.info("PDF: %s", pdf)
        return pdf
    logger.error("LaTeX compilation failed:\n%s", (r.stdout or "")[-1500:])
    return None


# =============================================================================
# Entry point
# =============================================================================

def generate_report(results_root: str, out: Optional[str] = None,
                    compile_pdf_flag: bool = True, date: str = "") -> str:
    outdir = Path(out) if out else (Path(results_root) / "report")
    outdir.mkdir(parents=True, exist_ok=True)
    df = load_summary(results_root)
    if df.empty:
        logger.warning("summary.csv empty: no run to report.")
    figs = {
        "energy_per_req": fig_metric_by_controller(
            df, outdir, "wall_J_per_req", "Wall energy / request (J)", "fig_energy_per_req.pdf"),
        "rapl_per_req": fig_metric_by_controller(
            df, outdir, "rapl_package_J_per_req", "RAPL package / request (J)", "fig_rapl_per_req.pdf"),
        "latency": fig_metric_by_controller(
            df, outdir, "rt_p95_ms", "p95 latency (ms)", "fig_latency_p95.pdf"),
        "knee": fig_metric_by_controller(
            df, outdir, "knee_rps", "Max sustained throughput (req/s)", "fig_knee_rps.pdf"),
        "capacity": fig_capacity_curves(results_root, outdir),
        "scaling": fig_scaling_timeline(results_root, outdir),
        "language": fig_language_impact(df, outdir),
    }
    tex = build_tex(df, figs, outdir, date=date)
    if compile_pdf_flag:
        compile_pdf(tex)
    logger.info("Report generated in %s", outdir)
    return str(outdir)
