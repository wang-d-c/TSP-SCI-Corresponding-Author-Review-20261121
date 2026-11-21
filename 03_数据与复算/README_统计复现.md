# 从随包数据重算 600 项统计与图

本目录可独立运行。统计模式需要 `reproduce.py` 与 `data/`。复算读取 600 行首试账本及冻结参考结果，写出新的统计和敏感性表，并可同时生成 PDF/PNG 图。CSV 中的路线长度来自原研究已经完成的独立验环与计长。

使用 Python 3.10 或更新版本。统计模式仅使用 Python 标准库，可从任意工作目录按脚本实际路径启动。

```text
python reproduce.py --no-plot --output recomputed_statistics
```

该模式执行同样的输入 SHA256 和冻结统计校验，生成相同的 CSV 及 JSON 统计字段，结果 JSON 中 `environment.matplotlib` 记为 `null`。完整制图模式使用 `requirements.txt`。验收环境为 Windows、CPython 3.13.9、Matplotlib 3.10.6。

```text
python -m pip install -r requirements.txt
python reproduce.py --output recomputed
```

无 `--output` 时输出到脚本同级的 `recomputed/`。建议为重算指定新目录以保留随包结果。程序核验输入 CSV 的 SHA256，随后独立计算主、次比较并与冻结结果比对。检查不通过时退出。

| 文件 | 用途 |
|---|---|
| [data/core_600_runs.csv](data/core_600_runs.csv) | 600 项可携带的逐项数值、终态、实例、路线及终态摘要。 |
| [data/frozen_reference.json](data/frozen_reference.json) | 原账本、统计 JSON 和计划的 SHA256，携带版 CSV 的 SHA256，以及原冻结比对值。 |
| [复算产物/statistical_reproduction.json](复算产物/statistical_reproduction.json) | 主分析的效应、区间、检验、逐图留一及 196 组敏感性效应。 |
| [复算产物/map_effects.csv](复算产物/map_effects.csv) · [复算产物/paired_effects.csv](复算产物/paired_effects.csv) | 主分析的逐图及同图同种子配对结果。 |
| [复算产物/complete_triplet_summary.csv](复算产物/complete_triplet_summary.csv) · [复算产物/complete_triplet_map.csv](复算产物/complete_triplet_map.csv) · [复算产物/excluded_triplets.csv](复算产物/excluded_triplets.csv) | 三方法齐备的 196 组与 4 组缺失原因。 |
| [复算产物/four_strata.csv](复算产物/four_strata.csv) · [复算产物/leave_one_map.csv](复算产物/leave_one_map.csv) · [复算产物/delivery_by_method.csv](复算产物/delivery_by_method.csv) | 四来源组、逐图留一和单独的交付状态。 |
| [总体效应及 95% 区间](复算产物/overall_effects_95ci.pdf) · [逐图点图](复算产物/map_effects.pdf) · [有效配对累积分布](复算产物/pair_ecdf.pdf) | 三张图均有同名 PNG 版本。 |

路线核验另需匹配的地图坐标与路线城市顺序。可用本目录账本的 `run_id`、`instance_sha256` 和 `route_sha256` 关联原始证据。获取条件见终审包的原始证据与审稿访问索引。重新求解另需依法取得的软件、冻结配置和计时执行环境。

详见[数据字典](数据字典.md)、[统计补充与图注](统计补充与图注.md)及[隔离复算验收](复算验收.md)。
