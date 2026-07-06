```yaml
---
type: 概念
title: "GPU 互联拓扑"
created: 2026-05-29
updated: 2026-05-29
tags:
  - GPU互联
  - 网络拓扑
  - All-to-All
  - NVSwitch
  - 并行计算
related:
  - "[[entities/nvswitch-7]]"
  - "[[概念/铜缆互联]]"
  - "[[概念/共封装光学CPO]]"
sources:
  - "research-nvswitch-7-2026-05-29.md"
confidence_grade: B
confidence_reason: "基于英伟达公开技术文档和SemiAnalysis分析，拓扑概念清楚，但NVL576具体方案未定"
---
```

# GPU 互联拓扑

GPU 互联拓扑是指在大规模并行计算系统中，多个 GPU 之间通过物理网络连接的方式和结构。拓扑设计直接影响跨 GPU 通信的延迟、带宽和阻塞特性，是决定万亿参数级大模型训练效率的关键架构要素。

## 主要拓扑类型

### All-to-All Non-Blocking（全互联无阻塞）

- **定义**：任意两个 GPU 之间均能以满速通信，无需经过中间节点转发，无拥塞
- **实现方式**：通过 Crossbar 或 Clos 网络，典型代表是 NVSwitch 交换架构
- **优势**：最高通信效率，适合大张量并行（Tensor Parallelism）
- **代价**：端口数随规模平方增长，物理成本和布线复杂度极高
- **NVSwitch 代际实现**：NVSwitch 代际通过聚合带宽翻倍维持全互联特性，但 NVSwitch 7 可能首次打破这一规律

### Two-Tier Non-Clos（两层非Clos拓扑）

- **定义**：将 GPU 分组，组内全互联，组间通过上层交换机连接
- **优势**：大幅降低端口数和线缆成本
- **代价**：跨组通信可能产生阻塞（Oversubscription），需软件调度规避拥塞
- **NVL576 可能情景**：若 NVSwitch 7 带宽不变，英伟达可能采用此方案

### Dragonfly 拓扑

- **定义**：一种高基数低直径网络拓扑，通过组内全互联+组间单跳实现大规模扩展
- **优势**：在超大集群中，端口效率优于传统 Clos 网络
- **应用**：已有超算系统采用，Rubin Ultra 可能借鉴

## 拓扑选择对并行策略的影响

| 并行模式 | 通信模式 | 对拓扑的敏感度 |
|---------|---------|-------------|
| 数据并行 | All-Reduce | 低 |
| 张量并行 | All-to-All | **极高** |
| 专家并行 | All-to-All（稀疏） | **高** |
| 流水线并行 | 点对点 | 低 |

## 英伟达的拓扑演进趋势

1. **Hopper (H100)**：8 GPU NVLink 域，专用 NVSwitch 实现小规模全互联
2. **Blackwell (B200)**：72 GPU NVL72 域，统一 NVSwitch 背板实现机架内全互联
3. **Rubin (VR200)**：延续 NVL72 全互联，NVSwitch 6 带宽翻倍至 260 TB/s
4. **Rubin Ultra**：目标 NVL576，但拓扑方案未定——NVSwitch 7 带宽悬念将决定是继续 all-to-all 还是转向层级化网络

## 对 A 股硬件投资的指导意义

- **全互联情景**（NVSwitch 7 翻倍）：利好铜缆背板（线缆用量翻倍）、液冷（功耗密度增长）
- **层级化情景**（NVSwitch 7 持平）：铜缆增量逻辑弱化，CPO 跨机架需求可能提前

## 参考

- NVIDIA NVSwitch Technical Overview
- SemiAnalysis: GTC 2026 – The Inference Kingdom Expands
- SemiAnalysis: Vera Rubin – Extreme Co-Design

