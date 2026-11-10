# ARPES viewer 用户指南

*[English version](../../USER_GUIDE_en.md) · [Version française](../../USER_GUIDE_fr.md)*

*最后更新：2026 年 11 月 10 日 —— 适用于 ARPES viewer v1.3.3*

版本号及日期显示在主窗口的标题栏和最下一行。bug 报告、问题和最新版本：
<https://github.com/DingPei1995/ARPES-viewer>（报告 bug 时请注明版本号）。

本指南按程序在屏幕上的样子组织：

- **第一部分**入门：安装、演示数据、程序可读取的文件、配置 AI 智能体、代码结构。
- **第二部分**主面板：数据集列表及其周围的一切。
- **第三部分**数据查看窗口：cut、map、kz map、k-map、曲线、自旋与空间分辨扫描。
- **第四、五、六部分**是工具面板的三个标签页（**Basic**、**Advanced**、**Figure**）；第六部分最后
  给出一个从载入数据到成图的实例。
- **第七部分** AI 智能体：它如何操作本程序、如何启动和监控，以及一个从配置到成图的实例。
- **第八部分**日常维护：自动保存与恢复、保存工作、错误日志、版本与常见问题。

所有截图都取自运行中的程序，使用 `devtools/demo_data.py` 生成的模拟数据，没有 beamtime 也能跟着
操作（[§1.3](#13-用演示数据试用)）。**这些都不是真实的实验数据。**每一步的技术背景（公式、测试、
设计取舍）见代码旁的参考文档：[读取数据](../../../arpes_viewer/loader/README.md)、
[窗口](../../../arpes_viewer/ui/README.md)、[分析](../../../arpes_viewer/tools/README.md)，以及
[CHANGELOG](../../../CHANGELOG.md)。

<!-- contents -->
