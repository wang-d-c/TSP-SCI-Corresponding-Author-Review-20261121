"""Render the conditional diagnostics from the authenticated R14 export."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def signed(value):
    return f"{value:+.2f}" if value is not None else "—"


def render_figures(path, info, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "font.family": "DejaVu Sans", "pdf.fonttype": 42})
    pools = list(info["pool_summaries"])
    fig, ax = plt.subplots(figsize=(8.0, 3.5), layout="constrained")
    ax.axvline(0, linestyle="--", linewidth=1.0, color="#696969")
    for y, pool in enumerate(pools):
        chosen = [row for row in rows if row["pool"] == pool and row["K_over_M_ppm"]]
        for order, color, marker, jitter in (
                ("K_first", "#17698f", "o", 0.09), ("M_first", "#b55434", "^", 0.22)):
            values = [float(r["K_over_M_ppm"]) for r in chosen if r["order"] == order]
            levels = [y - jitter + .018 * ((i % 5) - 2) for i in range(len(values))]
            ax.scatter(values, levels, color=color, marker=marker, alpha=.70,
                       s=32, label=order.replace("_", " ") if y == 0 else None, zorder=3)
        stats = info["pool_summaries"][pool]["paired"]
        average, band = stats["mean_ppm"], stats["seed_bootstrap_95_percentile_interval"]
        if band is not None:
            ax.plot(band, [y + .18] * 2, color="#242424", linewidth=1.6, zorder=4)
            ax.scatter([average], [y + .18], color="#242424", marker="D", s=31,
                       label="Mean and descriptive 95% interval" if y == 0 else None, zorder=5)
    ax.set(yticks=range(len(pools)), yticklabels=[p.replace(".seed100004", "") for p in pools],
           xlabel="K versus M final-tour shortening (ppm, positive favors K)")
    ax.invert_yaxis()
    ax.grid(axis="x", linewidth=.5, alpha=.3)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, 1.23), frameon=False, ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    for ext in ("pdf", "png"):
        fig.savefig(path / f"R14_paired_distribution.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def markdown(path, info):
    groups = info["pool_summaries"]
    slots = info["statuses"]
    if info["analysis_status"] == "complete_coverage":
        complete = (f'所有 120 槽均有终态。有效 {slots.get("valid", 0)}，'
                    f'正常未交付 {slots.get("budget_no_delivery", 0)}。')
    else:
        complete = f'台账尚未完整覆盖 120 槽。实际状态为 {json.dumps(slots, ensure_ascii=False)}。'
    lines = [
        "# R14 固定起点续搜结果", "", complete, "",
        "两个地图上的三个固定父池分别使用 20 个新续搜种子。每个种子比较既有 M 起点和既有 K 起点。"
        "两臂的续搜窗口各为 30 秒，既有起点及父池生成费用位于该窗口外。正 ppm 表示 K 的终点路线较短。",
        "",
        "| 选中起点来源 | 有效配对 | K 短 / 平 / 长 | 均值 ppm | 中位数 ppm | 条件种子 95% 区间 ppm |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for pool, details in groups.items():
        data = details["paired"]
        stats = "/".join(map(str, data["short_tied_long"]))
        band = data["seed_bootstrap_95_percentile_interval"]
        interval = f"[{signed(band[0])}, {signed(band[1])}]" if band else "—"
        lines.append(f"| {pool} | {data['pairs']} / 20 | {stats} | {signed(data['mean_ppm'])} | "
                     f"{signed(data['median_ppm'])} | {interval} |")
    lines += [
        "",
        "区间是在各预先选定父池内部对有效种子作 10,000 次条件重抽样。三个父池来自原主实验最显著的负例，"
        "两个同地图父池也共享地图几何。这些结果用于比较特定既有起点在新种子下的续搜表现，"
        "不能推广为独立地图效果、0.26 秒费用的因果效应或整体方法净收益。",
        "",
        "[120 槽终态表](outcomes_120.csv) · [60 对差值](pairs_60.csv) · [每池和顺序的完整统计](diagnostics_summary.json)",
        "",
    ]
    (path / "R14_条件续搜结果.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    path = args.report
    info = json.loads((path / "diagnostics_summary.json").read_text(encoding="utf-8"))
    with (path / "pairs_60.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    markdown(path, info)
    if any(row["K_over_M_ppm"] for row in rows):
        render_figures(path, info, rows)


if __name__ == "__main__":
    main()
