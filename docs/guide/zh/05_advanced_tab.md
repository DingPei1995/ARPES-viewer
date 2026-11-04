# 第五部分 工具面板：Advanced 标签页

**Advanced** 标签页包含后续的分析：能带锐化滤波与对称化、脊线提取、堆叠图、MDC 与 EDC 拟合、cut 运算、切片序列图和三维视图。

## 5.1 平滑、求导、曲率与对称化

每种滤波都有自己的窗口，在列表中选中一个或多个 cut（或 map）后从工具面板打开：

| 标签页 | 按钮 | 作用 |
|---|---|---|
| Basic | **Background subtraction...** | 扣除不属于能带的强度：Shirley 或 Tougaard 非弹性背景、所有角度共有的本底、平滑多项式——或除去费米截断 |
| Advanced | **Smooth...** | 高斯、Savitzky–Golay 或滑动平均平滑，可先去尖峰 |
| Advanced | **Second derivative...** | 预平滑后求 −d²I/dE² 或 −d²I/dk²，使能带更锐利 |
| Advanced | **Curvature...** | 一维或二维曲率（Zhang 等人），比二阶导数更贴合能带 |
| Advanced | **Symmetrise...** | 以一条线为镜面对称化 cut；对 map，镜像或旋转其等能面 |

每个结果都是新的数据集，并记录生成它的处理步骤。

![曲率窗口](../../images/process_dialog.png)

- **Source**（原图）与 **Result**（结果）并排显示、色阶一致，便于看出参数是否把
  能带"吃掉"了；两者同步平移和缩放。
- **先平滑。** 二阶导数和曲率窗口打开时会给出提示：两者都会放大噪声，通常对先平滑
  过的数据效果更好——先运行 **Smooth...**，在列表中选中其结果，再对它打开滤波；
  或者在窗口中加大预平滑宽度。平滑过的结果在列表中带有 **‹smoothed›** 标签（由它
  生成的数据也带此标签）；对这样的数据，窗口不再给出提示，只显示一行"已平滑"，
  预平滑宽度默认为 0。
- **Shape**：*Square pixels*（每个数据点为正方形——对角度-能量 cut 不失真）、
  *Equal axes*（两轴单位长度相同——适合角度-角度或 k-k 图，两轴单位相同时自动
  选用）、*Fill the box*（填满窗口）。
- **Live preview** 在修改参数时实时重算；**Apply** 把结果加入列表。
- 初始值：**Symmetrise** 默认以过角度（或 k）= 0 的竖直线为镜面，即 k → −k；
  *Background subtraction* 中的 **Fermi cut-off** 的 E_F 取文件记录的值，若没有则取
  角积分 EDC 下降最陡处，温度和分辨率也从文件读取。

对 map，处理按平面进行，并首先询问**作用于哪组平面**——等能面还是色散切面，
因为等能面的曲率与 cut 的曲率是不同的物理量。**Preview at** 选择预览的平面；
**Apply to the whole cube** 对所有平面执行。各操作和宽度以所选平面的真实轴名标注
（如 *Second derivative along Kinetic energy*），平滑宽度默认取各轴范围的 1/100。

![对 map 平滑](../../images/volume_process_dialog.png)

列表下方的 **Truncate...**、**Compress...** 和 **Self-normalise...** 可同时改变一个
或多个数据集的网格或标度——前提是它们类型相同，且各轴点数一致：**Truncate** 裁剪
到某一范围，**Compress** 合并像素，**Self-normalise** 每张谱除以自身总强度。

**Self-normalise** 把数据的每一部分除以它自身的总强度（或峰值）：

- **Normalise** 下拉框用 ARPES 的说法选择“每一部分”是什么，并默认选常规做法：
  cut 默认 *each EDC*（每条 EDC），map、k-map、kz map 默认 *each cut (slit ×
  energy at one scan step)*（每张 cut 各自归一，可去除扫描过程中光通量或束流的
  漂移）。其他选项：每条 MDC、map 的每条 EDC、每张等能面，或 *custom*（自定义）。
- **Summed over** 显示求和所沿的轴，可以手动勾选；下方的一句话说明当前勾选的
  效果（例如 “Each plane over Angle, slit × Kinetic energy is divided by its own
  total — one factor for every Angle, deflector”）。
- **Sum only over** 把求和限制在某个求和轴上的一个窗口内——默认是能量轴——例如
  只用某个芯能级的能量范围。

![自归一](../../images/data_operations.png)

## 5.2 脊线提取（Ridge detection）

工具面板 → Advanced → **Ridge detection...**（cut 或 map）把能带当作强度的脊线
来追踪，每个点精确到亚像素，比二阶导数更锐利，也不会画出虚假的双线。

- **Smoothing**：每个轴的平滑宽度，以该轴的单位计——约为能带宽度。
- **Threshold**：逐渐提高，直到只剩下能带（源数据上的黄色点）。
- **Result to list**——脊线图像（map 逐平面处理，可选平面）；**Save ridge
  points...**——一个 CSV，紧束缚拟合（[第 26 节](#64-紧束缚拟合)）可以读取。

## 5.3 堆叠图

**Stack plot (EDC / MDC)...**（工具面板 → Advanced，选中一张 cut）：EDC 或 MDC 的
瀑布图，可设置曲线条数、合并、归一化、偏移、错切与配色；**Send to figure
composer** 把它作为一个图面板送入作图器。

![堆叠图](../../images/stack_plot.png)

## 5.4 MDC 拟合与 EDC 拟合

工具面板的 Advanced 页中有两个逐行拟合峰的工具：

- **MDC fit (k-cut only)...** 拟合动量分布曲线，再从拟合峰位读出能带：费米速度、
  有效质量、自能。它只接受横轴已经是 Å⁻¹ 的 cut——以 eV·deg 为单位的费米速度没有
  意义——否则按钮显示为灰色。
- **EDC fit...** 拟合能量分布曲线，适用于任何 cut，可在模型中包含费米截断。由拟合
  能带得到 v_F 和 m\* 需要 cut 已在动量空间。

![MDC 拟合面板](../../images/mdc_fit_panel.png)

面板顶部的 **Guided fit (step by step)** 会在控件旁逐步引导完成整个拟合，每一步
简要说明这一步的意义，并用橙色框标出要用到的部分：MDC（EDC）拟合在做什么、峰形、
拟合范围（把蓝线拖到能带起点 / 终点，按 *Start here* / *End here*）、能带、种子点
（引导会把蓝线依次移到范围内的五个位置——在每个位置点击右侧曲线上该能带的峰）、
试拟合一行、拟合整个序列、读取结果。每一步具备拟合所需的条件后 *Next* 才可点击。

图像和控件之间有可拖动的分隔条，控件始终可见；窗口放不下时，鼠标滚轮在图像上滚动的是
窗口本身（Ctrl + 滚轮缩放图像）。

手动操作：

1. **Bands** 页：每条能带分支点一次 **Add band**；选中一条能带，按 **Place a
   seed**，再在右侧曲线上点击峰的位置。沿能带放四五个种子点就够了；**Line at**
   切换当前查看的行。
2. **Try this line** 显示当前行的拟合结果（虚线为初始猜测）。
3. **Fit settings** 页：峰形（Lorentzian、Gaussian、Voigt）、背景、步长，然后
   **Fit the series**。拟合出的峰位画在图上，点的大小代表振幅。
4. **Dispersion...** 拟合能带：**v_F**（直线）、**m\***（抛物线），并检查拟合
   在多大范围内稳定。**Self-energy...** 给出 Re Σ 与 Im Σ。

![色散窗口](../../images/dispersion_window.png)

**Save table...** 保存所有行的拟合结果；**Band to list** 把一条能带加入主列表。

**两条直线分支的交点。** 在 **Dispersion...** 窗口中选择 *v_F*（直线）时，其他
每条已拟合的能带也以同样方式拟合，并给出两条直线的交点及其不确定度（由两次拟合
传递而来）：把狄拉克锥的两侧分别拟合得到的狄拉克点，或任意两条能带的交叉点。
若某个拟合点的误差坍缩（峰宽拟合到零），它不再独占色散拟合的全部权重：任何一点的
权重都不超过十个典型点。

## 5.5 Cut 运算：二色性与参考谱归一

把两张 cut 组合成第三张：线二色性（LH − LV）、圆二色性、除以金参考谱，或普通的
差、比、和。在列表中选中两张 cut，点工具面板 → Advanced → **Cut arithmetic (two
cuts)...**（先选的为 A；窗口中可交换）。只有恰好选中两张 cut 时该按钮才可用。

![Cut 运算](../../images/cut_arithmetic.png)

- **顶部表格**对比两次测量记录的条件（偏振、光子能量、角度、样品位置、温度、
  通能、透镜模式）。橙色行表示差异超过容差——在样品上两个不同位置之间做的
  二色性图，反映的其实是*位置*差异。
- **Purpose** 预设：*Linear dichroism*（A − B，B 按总强度缩放）、*Circular
  dichroism*（(A − B)/(A + B)）、*Divide by a reference*（除以参考谱）、*Custom*。
  若偏振看起来颠倒了会给出警告（可用 **Swap A ↔ B** 交换）。
- **Scale B to A** 按总强度或某一区域的强度缩放；**Hide where A+B below** 屏蔽
  背景区域。
- A、B 使用同一色阶；结果用以零为中心对称的红-白-蓝色阶。若两者都是原始计数，
  会传播泊松误差，并在图下方给出统计。
- **Result to list**、**Uncertainty to list**、**All three as a figure**。

## 5.6 切片序列图（Slice series figure）

选中 map → 工具面板 → Advanced → **Slice series figure...**：把数据立方的一系列二维
平面切片排成一页论文图——一系列能量处的等能面，或一系列角度 / 动量处的 cut——可等
间距或指定位置，可积分，共用一个色阶，只在外侧边缘标注坐标。（注意与 **3D slices**
区分，后者是在三维视图中画三个平面。）

- 面板标题使用所要求的名义值（−0.2 eV），而不是实际平面的值（−0.2022 eV）；实际使用的
  平面和积分窗口记录在面板信息中。
- 色图、反转、色阶（百分位）和 gamma 在对话框中一次设好，作用于所有面板。
- **Draw the Brillouin zone, as on the map**：把 BZ overlap 画在 map 上的布里渊区画到每个
  等能面面板上，每条边只画一次。
- 脚本或智能体可直接调用 `contour.slice_figure(values=[0, -0.1, -0.2], half_width=0.02)`
  （或对选中行调用 `A.open_slice_series(values=...)`），不弹出对话框。

| 设置 | 结果 |
|---|---|
| ![切片序列图设置](../../images/slice_figure_dialog.png) | ![切片序列图](../../images/slice_figure.png) |

## 5.7 三维视图

Advanced 页中有四个以三维方式显示 map 的工具，各自在独立窗口中打开——拖动图像即可
旋转：

- **3D slices...**——穿过数据立方的三个正交平面，每个平面的位置可自行设定（每个轴
  有勾选框、滑块和输入框）。
- **Notched cube...**——切掉一个角的立方体：一张等能面和两张色散图合在一幅图中。
- **Volume projection...**——整个体数据沿视线方向投影：最大强度、求和、alpha 合成，
  或带光照的等值面。
- **Stacked slices...**——平行切片在三维中层叠排列（见下文）。
- 对 **k-map**，三维视图从第一个充满数据的 k_x、k_y 平面开始显示：转换后的数据立方是远离
  E_F 时逐渐收窄的光锥的外包盒，最外侧的平面原本会画成空白面。*Change sampling... →
  Whole range* 可显示全部范围。

| 3D slices | Notched cube |
|---|---|
| ![3D slices](../../images/volume_slices.png) | ![Notched cube](../../images/volume_view.png) |

- **采样。** 每一帧都要对数据立方重新采样，因此窗口默认以 *Balanced* 采样打开，
  能跟上鼠标操作。当前采样写在 **Save the view...** 下方；**Change sampling...**
  可选择区域以及 *Fast*、*Balanced* 或 *Fine*，并从完整数据重新绘制。

  ![更改采样](../../images/volume_range_dialog.png)

- **颜色。** *Apply to* 可一次设置**所有切片**的颜色，或只设置某一方向（例如等能面
  用一种色表，色散面用另一种）：色表（及 *reversed*）、色阶（**Auto**，或 **Each its
  own** 每个切片各用自己的色阶）、gamma、**Opacity**（不透明度）和 **Fade low
  values**（让弱强度部分变透明，从而看到后面的平面）。
- **坐标轴。** 勾选 **Draw the axes, with ticks and values**。*Placement* 可以是自动的
  ——放在朝向你的外侧棱上，随视角转动而变化——也可以手动指定：每个轴沿立方体的
  哪条棱，以及从 **from min** 还是 **from max** 开始计数。
- **Camera**：方位角、仰角、深度比例；**Look into it** 正对所选平面。
  **Outline the faces** 和 **Orientation tripod** 为可选项。
- **Save the view...** 通过与所有面板相同的导出窗口导出图像（PNG、TIFF、JPEG，可设
  尺寸和 dpi）。**To figure composer...** 把当前视图作为一个面板加入论文图。

### 层叠切片（Stacked slices）

**Stacked slices...**（工具面板 → Advanced → 3D only）把数据立方的平行切片在三维
中层叠画出：等能面沿能量轴一张叠一张，或 cut 沿 k_z（或光子能量）一张排在另一张
后面——这是展示能带演化的常见画法。

![层叠切片](../../images/stacked_slices.png)

- **Layers**——层叠所沿的轴；**How many** 均匀分布各层，或在 **At** 中输入位置
  （逗号分隔，以该轴的单位计）；**Integrate** 把每层在该宽度内平均。
- **Frames**——每层的外框（灰色、黑色或无）。
- **Spread** 沿层叠轴拉伸盒子，使斜视时各层彼此分开而不互相遮挡：沿 k_z 层叠几张
  cut 时，*Spread* 取 3、方位角约 40°，每张 cut 几乎都能完整看到。
- **Fade low values**（*Colour*）在这里从 35 % 起：每层的背景透明，后面的层可以
  透过来。
- **Mark a curve through the layers**——以数据自身单位给出的点（每层一个，例如两条
  能带的交点），用红、黑、蓝……曲线连接并画在层叠图上方，可在第一个点处加标注。
- 所有三维视图的坐标轴现在都会让图像*及其标签*适应窗口或图面板（不再是固定边距），
  按每个轴的空间稀疏刻度，并在轴标题中写出上下标（`E - E_F`、`k_x`）。
