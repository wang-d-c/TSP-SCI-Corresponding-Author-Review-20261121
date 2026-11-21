# 复算入口与 Git 行尾验收

验收基准为终审仓库提交 `ee5a8bbc98dd3e376e702dcce6aa0d70bae05f48` 的 149 项 SHA256 清单及随包冻结结果。正式输入、原输出和原仓库未改动。验收未运行求解器。

| 审阅问题 | 改动与交付 | 实测 |
|---|---|---|
| Windows 检出改变清单文件的字节 | 增加仓库根目录 `.gitattributes`，内容为 `* -text`。 | 两次空工作区均设置 `core.autocrlf=true`。修补前 42/149 项不符，全部是 LF 转为 CRLF。仅加属性文件后的检出 149/149 项通过。 |
| 审稿人未安装 Matplotlib 时复算退出 | 在 `03_数据与复算/reproduce.py` 增加 `--no-plot`，并更新同目录统计复现说明。 | 以 `python -I -S` 运行，确认 Matplotlib 不可导入。8 份 CSV 与冻结版逐字节相同，JSON 的统计字段完全相同，生成图为零。 |
| 默认复算与输入保护 | 保留默认绘图模式及 SHA256 校验。 | 默认模式的统计 JSON 和 3 个 PDF 与冻结版逐字节相同，3 个 PNG 的像素和图像元数据相同但压缩字节不同。故意改动的输入副本以退出码 1 拒绝，未创建输出目录。 |

复算说明的运行示例可直接在配置 Python 3.10 或更新版本的审稿环境运行。统计模式不需要安装 `requirements.txt`。需要重绘时按说明安装固定 Matplotlib 依赖。

[统计模式验收 JSON](reproduction_regression.json) · [行尾验收 JSON](line_ending_regression.json)
