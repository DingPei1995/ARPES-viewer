# 第一部分 入门

本程序是什么、如何安装和启动、所有截图所用的演示数据、程序能读取哪些文件、如何连接 AI 智能体，以及代码和文件放在哪里。

## 1.1 ARPES viewer 是什么

ARPES viewer 是一个处理角分辨光电子能谱（ARPES）数据的 Python/PyQt5 程序。它可以浏览一次
beamtime 的全部测量，在独立窗口中打开每个数据，转换到动量空间，切片、拟合与处理，与能带计算
比较，并把结果排版成论文用图。每一步也都是普通的 Python 代码，脚本或 AI 智能体都可以调用。

本程序可免费用于**非商业用途**（学术研究与教学），采用 PolyForm Noncommercial License 1.0.0。
若在论文中使用，请引用：Ding Pei, *ARPES viewer*, Zenodo,
<https://doi.org/10.5281/zenodo.23771647>。

它不是采集程序，也不会修改你的数据文件：每个结果都是列表中的新数据集，或你指定的新文件。

## 1.2 安装与启动

需要 Python 3.9 或更高版本，以及五个依赖包：

```bash
pip install PyQt5 pyqtgraph numpy h5py scipy
```

然后在 `ARPES_viewer` 目录下运行：

```bash
python ARPES_viewer.py
```

**Windows 用户请双击程序文件夹中的 `ARPES viewer.pyw`**，而不是 `ARPES_viewer.py`：
Windows 用 `pythonw` 运行 `.pyw`，不会打开黑色的控制台窗口——以前误关这个窗口会
连带关闭程序。（若仍双击 `.py`，程序现在会隐藏为它单独打开的控制台；从命令提示符
启动时控制台保持不变。）程序的输出写入 `~/.arpes_viewer/launcher.log`；若程序因
错误停止，会弹窗显示该日志的末尾。

**错误信息自动保存为文本文件。** 出错时控制台会显示的内容——错误及其 traceback——
会自动保存到**程序文件夹中的 `error_logs/errors_<日期>_<时间>.txt`**（若该文件夹不可写，
则保存到 `~/.arpes_viewer/error_logs`），只在出错时才生成。届时会弹窗提示，程序
**继续运行**而不会关闭。报告 bug 时请**上传该文件**（在 GitHub Issues 中直接拖进文本框）
**或粘贴其内容**——主面板底部有 **Copy the newest error log**（把最新错误日志的内容
复制到剪贴板）和 **Open the error logs**（打开所在文件夹）。

**耗时操作显示进度条。** 在大数据或配置较低的电脑上可能需要较长时间的操作——读入整个
map、k 转换、FS correction、任意路径 cut、数据运算、合并数据、保存、ridge 检测、
各类拟合，以及 Calculated bands 中读取计算结果、计算平面上的能带和三维费米面——在
0.4 秒后都会显示进度窗口：进度条在动、显示已用秒数，能中断的步骤有 Cancel。程序是在
计算，不是卡死。

**Mac 用户无需打开终端：** 双击程序文件夹中的 **`ARPES viewer.app`** 即可启动
（可以拖到 Dock 里常驻）。它会自动找到装有上述依赖包的 Python——与终端里
`python3` 相同的那个，包括 conda 环境——并记住它。如果没有任何 Python 装了这些
包，对话框会给出 `pip install` 命令（已复制到剪贴板，粘贴到终端运行一次即可），
或让你手动选择一个 Python。

- 如果 macOS 提示 app *来自身份不明的开发者、无法打开*（程序是以 ZIP 下载的）：
  打开 **系统设置 → 隐私与安全性**，点 **仍要打开**（旧版 macOS：右键 app →
  **打开**）。只需第一次。
- 把 app 复制到程序文件夹以外（例如"应用程序"）时，第一次会询问程序文件夹的位置。
- 如果程序因错误退出，对话框会显示 `~/.arpes_viewer/launcher.log` 的最后几行；
  报告 bug 时请附上该文件。

本程序可读取的文件见 [§1.4](#14-支持的线站与文件格式)。

## 1.3 用演示数据试用

```bash
python devtools/demo_data.py            # 写入 ./demo_data/
```

生成的模拟数据与实测数据的打开方式完全相同：

- 原有的一组——一张费米面 map、一对 LH 与 LV 偏振的 cut、一个光子能量扫描、一条
  自旋分辨 EDC、一个小的实空间扫描，以及一张印有探测器网格的 map——来自一个简单的
  能带结构（Γ 点的六角电子口袋和空穴带，K 点的空穴口袋）；
- **一个三维层状晶体**（`demo_bulk_bands.nxs`）：Γ 平面（59.3 eV）与布里渊区顶面
  （77 eV）光子能量下的 map，沿 Γ-M（LH 与 LV）和 Γ-K 的 cut，以及沿 Γ-M、覆盖
  k_z 一个完整周期的光子能量扫描。其中两条能带沿一条贯穿布里渊区的线交叉，交叉能量
  随 k_z 变化；
- **这个晶体的计算结果**，就像理论组发来的那样：一个 Wannier90 哈密顿量
  （`demo_calc_hr.dat` 及 `demo_calc.win`）和同一能带的网格文件（`demo_calc.bxsf`）。
  它是未经重整化的晶体——能带宽 1/0.8 倍、高 50 meV——正是与数据拟合后能找回的值
  （[第 27 节](#65-计算能带calculated-bands)）；
- 两个 CIF 格式的晶体结构（`demo_crystal.cif`，1T 层状六角晶体；
  `demo_tetragonal_crystal.cif`，ZrSiS 型晶体）和一条 EDS 谱（`demo_eds.nxs`）。

所有数据都带有费米截断、分析器分辨率和泊松噪声。

修改窗口后，重新拍摄本指南中的所有截图：

```bash
python devtools/guide_screenshots.py    # 写入 docs/images/*.png
```

[第 30 节](#67-实例用作图器完成两张图)的两张示例图由演示数据、用程序自身的窗口
重新生成：

```bash
python devtools/figure_tests.py docs/images [存放 .afig 文件的文件夹]
```

## 1.4 支持的线站与文件格式

读取器会自动识别（[§2.2](#22-载入数据)）。

| 线站 | 文件 | 数据 |
|---|---|---|
| SOLEIL **ANTARES** | NeXus `*.nxs` | cut、偏转器 map、光子能量（PhD）扫描、空间扫描 |
| SOLEIL **CASSIOPEE** | Scienta 文本 `*.txt` | 单张谱；按编号组成的文件夹自动拼成 map 或光子能量扫描 |
| CASSIOPEE **自旋端站**（MBS A-1） | `*.krx`、`*.txt` | cut、偏转器 map、自旋分辨 EDC |
| ALS **MAESTRO** | `*.h5`、`*.hdf5` | cut、map、光子能量扫描与空间扫描 |
| ALBA **LOREA** | `*.nxs` | cut、map |
| Diamond **I05**（HR-ARPES）与 **I05-1**（nano-ARPES） | `*.nxs` | cut、map、光子能量扫描、空间扫描 |
| MAX IV **Bloch**（以及其他读取器都不认领的 Scienta SES 文件） | `*.ibw`、`*.zip`、`*.txt` | cut、偏转器 map、光子能量与样品架扫描 |
| Elettra **APE**、BESSY **One Cube / One Square**、SOLARIS **URANOS** | `*.ibw`、`*.zip`、`*.txt` | 按 SES 的写法 |
| ASTRID2 **SGM4** | `*.h5`、`*.hdf5` | cut、map、刀口扫描 |
| 本程序 | 自己的 `*.nxs` | 它保存的任何数据，一个文件可含多个数据集 |

数据集可以保存为本程序自己的 `.nxs`（可再次打开），或 Igor Pro 文本（`.itx`）。各线站文件的读法
及其格式带来的假设见[读取器参考文档](../../../arpes_viewer/loader/README.md)，其中也说明了如何添加新线站。

**扫描中途被中断的 map**（手动停止、束流丢失、控制软件崩溃）对所有线站都按实际测到的部分打开：从未测量的步（没有计数，或扫描轴没有数值）以及最后一步中强度明显低于前面各步的（不到其一半：采集中途被停）会被去掉；状态栏和 Information 面板（`incomplete.note`）说明去掉了几步以及原因。扫描中间的弱步来自样品本身，从不处理。

## 1.5 数据类型

| 类型 | 轴 | 含义 |
|---|---|---|
| `cut` | 角度（或 k）× E | 一张谱 |
| `map` | 角度 × 角度 × E | 偏转器或极角扫描 |
| `k_map` | kx × ky × E | 已转换到动量空间的 map |
| `kz_map` | hν × 角度 × E | 光子能量扫描 |
| `kz_map_k` | k_z × k∥ × E | 转换到动量空间的光子能量扫描 |
| `spem_4d`、`spem_1d` | x（× y）× 角度 × E | 实空间扫描 |
| `edc`、`mdc`、`spin_edc` | E（或 k）× 通道 | 曲线，可带 σ 误差通道 |

### 处理后数据的命名

每个处理结果都是列表中的新条目，名称为原数据名加上每一步处理的方括号标签，按处理先后排列：`Map80eV [norm] [E-E_F] [k]` 表示 Map80eV 先归一化，再以 E_F 为能量零点，最后转换到动量空间。标签按通常的处理顺序排列（`arpes_viewer/tools/runtime/naming.py`）：

| 标签 | 由什么产生 | 做了什么 |
|---|---|---|
| `[combined …]` | Combine…、重复扫描求和 | 多个数据拼接、堆叠或求和 |
| `[degrid] / [grid]` | Remove detector grid… | 去除探测器网格 / 网格本身 |
| `[det]` | 探测器校正 | 梯形与区域校正 |
| `[crop]` | Truncate…、`L.crop` | 按坐标范围截取 |
| `[bin]` | Compress…、`L.bin` | 按块求和（合并点） |
| `[despike]` | Smooth…（去尖峰） | 去除尖峰 |
| `[norm]` | Self-normalise…、`L.normalise` | 每条谱或每个平面除以自身总强度或峰值 |
| `[bg]` | Background subtraction… | 扣除背底 |
| `[E-E_F]` | Fermi edge fit（平移）、`L.shift_energy` | 能量以费米能级为零点 |
| `[dFD]` | Fermi edge fit（相除） | 除以费米–狄拉克函数 |
| `[FS corr]` | Straighten bands (FS correction) | 沿狭缝方向拉直能带 |
| `[sm]` | Smooth… | 平滑 |
| `[symm]` | Symmetrise… | 对称化 |
| `[k]` | k 转换（cut / map） | 转换到动量空间 |
| `[kz]` | kz 转换 | 光子能量扫描转换到 k_z |
| `[d2] / [grad] / [cur]` | Second derivative… / Curvature… | 二阶导数、梯度、曲率 |
| `[ridge]` | 脊线识别 | 能带位置 |
| `[arb cut]` | map 中的任意方向 cut | 沿自选直线的 cut |
| `[slice …]` | Save slice to list（查看器） | 从查看器取出的平面或 cut |
| `[EDC …] / [MDC …]` | 查看器的 EDC / MDC 加入列表 | 取出的曲线，附位置 |
| `[shifted] / [sigma]` | 曲线查看器 | 平移后的曲线 / 其泊松误差 |
| `[fit]` | 曲线拟合 | 拟合结果 |
| `[LD] [CD] [diff] [asym] [ratio] [sum]` | Cut arithmetic… | 两条 cut 的运算结果 |
| `[calc]` | 计算能带 | 计算结果，不是测量 |

**排序。** 在列表上右键 → **Sort by data type** 按名称中的**最后一个**标签（即最后一步处理）分组，组的先后按上表顺序：未处理的测量数据在最前，然后是 `[crop]`、`[norm]`、`[E-E_F]`、`[k]`……；不在表中的标签排在最后。组内先按数据类型（cut、map……），再按名称排序（数字按数值比较）。**Sort by name** 不考虑标签顺序。旧版本的名称同样能识别：`_s_nor` 视为 `[norm]`，`_tk` 为 `[crop]`，`_comb` 为 `[bin]`，`_sm`、`_d2`、`_cur` 为 `[sm]`、`[d2]`、`[cur]`，`[E-Ef]` 为 `[E-E_F]`。手动改名时保留标签，排序位置才不变。AI 智能体遵循同一规则，包括它自己起的名字（[§7.6](#76-智能体遵循的工作规则)）；`L.naming()` 会给出这张表。

## 1.6 配置 AI 智能体

AI 智能体可以替你操作本程序（[第七部分](#第七部分-ai-智能体)）。常用方式无需额外安装：

1. 准备一个能读写本机文件的 AI 应用：Claude 桌面版、Claude Code 或类似的智能体。
2. 在 ARPES viewer 中点击工具面板顶部的 **AI assistant...**，选择数据文件夹和结果文件夹，
   点击 **Copy the prompt and start**（[§7.3](#73-从-ai-assistant-面板启动)）。
3. 把提示词粘贴进 AI 应用，并允许它读取数据文件夹、读写结果文件夹。

使用 MCP 工具的应用需要先添加一次本程序的 MCP 服务器，提示词中会说明方法（[§7.5](#75-其他启动方式)）。
开始之前，请先了解哪些内容会离开你的电脑（[§7.1](#71-工作原理以及哪些内容会离开你的电脑)）。

## 1.7 代码结构

| 文件夹 | 内容 |
|---|---|
| `arpes_viewer/loader/` | 读取器：每个线站一个（`beamlines/`），通用格式（`formats/`），本程序自己的 `.nxs`，会话自动保存 |
| `arpes_viewer/tools/` | 不依赖窗口的计算：谱（费米边、拟合、芯能级、自旋）、动量（k 与 kz 转换）、处理（平滑、求导、cut 运算……）、晶体（晶格、布里渊区、计算能带）、输出（作图、导出） |
| `arpes_viewer/ui/` | 窗口：主面板（`launcher/`）、查看窗口（`viewers/`）、工具窗口（`panels/`）、公共部分（`common/`，包括智能体的操作 `L`，即 `common/live.py`） |
| `arpes_viewer/agent/` | MCP 服务器、agent bridge，以及由程序自动生成的智能体参考文档 `API.md` |
| `agentic/` | 面向智能体和脚本的示例与范例 |
| `devtools/` | 演示数据、截图、作图测试、本指南的构建脚本 |
| `test/` | 测试（`python -m pytest`） |

`tools/` 中的计算不需要窗口，脚本可以直接调用，例如
`arpes_viewer.tools.momentum.kspace.convert_map(...)`。每个文件夹都有 README，写明其背后的公式与测试；
代码布局与约定见[开发者说明](../../DEVELOPER.md)。

## 1.8 程序文件的存放位置

| 位置 | 内容 |
|---|---|
| `~/.arpes_viewer/` | 跨会话记住的设置、启动日志、agent bridge 运行时的令牌、AI assistant 上次用的文件夹 |
| `~/.arpes_viewer/sessions/` | 计算结果的自动保存副本（每个会话一个文件夹）以及 `operations.log`（[§8.1](#81-自动保存内存与恢复)） |
| 程序文件夹中的 `error_logs/`（不可写时为 `~/.arpes_viewer/error_logs/`） | 发生错误的会话各一个文本文件（[§8.3](#83-错误日志与-bug-报告)） |
| `<结果文件夹>/_agent/` | 从 AI assistant 启动时，智能体的命令文件、输出和图片（[§7.3](#73-从-ai-assistant-面板启动)） |

数据文件夹只会被读取；只有你自己选择把文件保存到那里时，程序才会写入。
