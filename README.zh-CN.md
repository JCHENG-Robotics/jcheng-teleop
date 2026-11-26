# jcheng-teleop
**简体中文** | [English](README.md)

> 状态：**实验性**，2026-11-26。版本 0.3.0。
> M0 设计已批准；M1 的 ROS-free 核心与 CLI 已实现，并有 L1 与进程内 L2 测试；
> M1 已在 L1/进程内 L2 层面验收；M2 进行中：System 侧 mock teleop intake/ROS 订阅端与 Teleop ROS publisher 已落地；ArmPi、Gate-2 与 PiPER X mock 的 L3 已通过 canonical 域 42 runtime + 域 43 仿真桥运行，Humble 构建通过。PiPER X 仅用于仿真：不存在 CAN Profile、驱动桥或实机路径。M3 已启动：采集核心（provenance 门禁、非阻塞写入、封包校验）可记录 mock CLI 会话，ROS 演示采集器可从系统 telemetry tap 记录带标签的 observation 行；媒体、实机采集与 30-episode 验收尚未实现。M4 已启动：离线 input replay、command wire-projection replay、anomaly 扫描、质量指标与 benchmark JSONL 导出可用；LeRobot 导出受 learning dataset 契约阻塞。M5 已启动：为 studio 面板提供 loopback-only 只读 teleop 状态 API；面板与 stop 接线尚未实现。目前仍无输入设备访问、无租约适配器、无生产网关客户端。实体操作员输入适配器位于本仓库之外；无设备输入源
> 与映射位于仓库内。运行中的机器人不会使用其中任何内容。
>
> 本文为英文主文档的中文对照；如有歧义，以英文版为准。

`jcheng-teleop` 是 JCHENG 生态的 L3 遥操作与示教采集能力。其职责是将操作员
输入转换为有界、受租约约束、受 deadman 保护的**遥操作意图**交给系统层，并在
不成为运动权威的前提下采集可复现的示教 episode。设计目标是用同一套代码和
机器人 Profile 适配 ArmPi Ultra 5 自由度机械臂、Gate-2 机械臂、PiPER X 6 自由度
机械臂及未来的主从机械臂，而不是复制多套控制核心。这是设计目标：PiPER X 的
CAN Profile 与实机路径尚不存在，Gate-2 目前仅用于仿真。

系统层始终是运动的唯一来源。遥操作只提出意图；网关、租约、运动仲裁器和安全
监督器决定是否执行。本仓库不打开机器人设备、不发布厂商话题、不调用
`ExecuteMotion`，也不发送舵机或电机命令。

## 范围与边界

| 项目 | 本仓库 |
|---|---|
| 层级 | L3 能力（`capability.yaml`） |
| 输入 | 来自无设备输入源（虚拟/键盘/JSONL/手柄映射）或操作员侧适配器的归一化输入样本（M1 起）；系统层只读的机器人、安全与租约状态（M2 起） |
| 输出 | 进程内 mock gateway 的有界动作意图（M1）；test-only ROS publisher 在 `/jcheng/intent/teleop` 上发布的预留 `TeleopCommand`，域 42（M2，分支）；git 之外的采集包（M3 起）。仅核心包时不离开进程 |
| 运动权威 | 无。系统网关、租约、仲裁器和安全监督器保持权威 |
| 硬件访问 | `none`（`capability.yaml`）；本仓库不打开机器人设备，也不打开操作员输入设备 |
| 自有设备 | 无。实体手柄、键盘、方向盘、示教器或主臂均位于操作员侧，不属于能力边界。M1 提供无设备映射与测试；操作系统设备驱动留在操作员侧 |
| 禁止 | 机器人设备访问、厂商话题、`/move_action`、`/cmd_vel`、`ExecuteMotion`、硬件命令、伪造状态、把仿真数据标记为实机数据 |
| v0.3.0 运行时 | 核心包：仅本地 CLI，无 DDS 域、无节点、无发布者、无设备。`ros2_ws`：test-only M2 意图发布节点，域 42，使用操作员提供的租约；无订阅者、无服务、无设备 |

`jcheng-system` 现在已有 mock/核心层 teleop intake（`TeleopIntake`）与
`/jcheng/intent/teleop` 的 ROS runtime 订阅端（PR #20），以及 test-only
仿真桥。但**尚无生产级遥操作消费端**：没有网关租约适配器、没有操作台租约
流程、没有 `TeleopState` 状态面，因此 M2 仍在进行中。该 intake 仅用于
mock/仿真，厂商执行器也无法流式执行多关节运动。接口提案见
[docs/INTEGRATION_CONTRACT.md](docs/INTEGRATION_CONTRACT.md) 和
[docs/proposals/SYSTEM_TELEOP_INTAKE.md](docs/proposals/SYSTEM_TELEOP_INTAKE.md)。

## 仓库结构

```text
jcheng-teleop/
├── capability.yaml                 # 准入清单（offline，hardware_access: none）
├── docs/
│   ├── ARCHITECTURE.md             # 上下文、模块、生命周期、决策
│   ├── TELEOP_CORE.md              # 输入调理、映射、会话、API
│   ├── SAFETY_MODEL.md             # 危害、状态机、停止路径、残余风险
│   ├── DATA_COLLECTION.md          # 采集、溯源、时间同步、LeRobot 映射
│   ├── INTEGRATION_CONTRACT.md     # 系统、仿真、Learning、Studio 契约
│   ├── DEPENDENCY_REVIEW.md        # 先例、许可证、依赖决策
│   ├── INPUT.md                    # 输入样本与适配器边界
│   ├── M1_PLAN.md                  # M1 工作包、目录树、测试矩阵、阻塞项
│   └── proposals/                  # 契约优先提案；未修改任何接口
├── src/jcheng_teleop/              # ROS-free 核心、适配器、采集、replay、CLI
├── ros2_ws/src/jcheng_teleop_ros/  # M2 ROS 2 意图发布节点
├── examples/armpi_ultra_demo/      # ArmPi 演示 profile 与 binding
├── examples/gate2_arm_demo/        # Gate-2 演示 profile 与 binding
├── examples/piper_x_demo/          # PiPER X 仅仿真 profile 与 binding
├── tests/                          # 单元、进程内 L2 与静态边界测试
├── scripts/check_repo_gate.sh      # 仓库门禁（本地与 CI）
├── evidence/                       # L0/L1/L2 证据记录
├── pyproject.toml                  # 包元数据与 pytest 配置
├── VERSION
├── README.md / README.zh-CN.md
├── ROADMAP.md / CHANGELOG.md / ACCEPTANCE.md
└── LICENSE-REVIEW.md
```

## 要求

- Python 3.10 或更高（CI 使用 3.12）；当前文档与门禁使用 `pytest` 7.4+ 和
  `PyYAML` 6.0+。CI 固定 `pytest==8.3.4` 与 `PyYAML==6.0.2`。
- M0 不需要 ROS。只有 M2 出现意图节点时才需要 ROS 2 Humble，并在
  `ros:humble` 容器中验证。
- 门禁不需要输入设备和机器人。实体适配器位于操作员侧；本仓库只消费归一化
  样本，不打开设备。
- 采集包和数据集保存在仓库之外的操作员数据根目录中，绝不提交。

## 快速开始

```bash
python3 -m pytest -q tests
bash scripts/check_repo_gate.sh

PYTHONPATH=src python3 -m jcheng_teleop \
  --profile examples/armpi_ultra_demo/profile.yaml \
  --binding examples/armpi_ultra_demo/binding.yaml \
  --input virtual --ticks 20
```

门禁检查文档集、准入清单、相对链接、密钥、模型权重、录制数据和静态边界测试。
CLI 只连接进程内 mock gateway；两者都不接触机器人，也不打开设备。

## 验证状态

| 声明 | 状态 | 证据 |
|---|---|---|
| M0 文档集、链接、清单和静态无设备扫描通过 | 已验证（L0/L1，2026-11-26） | `evidence/20261126_m0_design/`；`tests/` |
| 生态审计与跨仓库契约缺口已记录 | 已验证（L0，2026-11-26） | [docs/INTEGRATION_CONTRACT.md](docs/INTEGRATION_CONTRACT.md)；[docs/DEPENDENCY_REVIEW.md](docs/DEPENDENCY_REVIEW.md) |
| M1 ROS-free 核心：调理、映射、deadman、会话、mock gateway | 部分验证（L1，2026-11-26；M1 验收待定） | `evidence/20261126_m1_core/`；`tests/` |
| M1 确定性 trace 与无设备边界 | 部分验证（L1/进程内 L2，2026-11-26；验收待定） | `evidence/20261126_m1_core/`；`tests/test_runner_determinism.py` |
| 输入调理、映射、会话与 deadman 行为 | 部分验证（L1，2026-11-26；验收待定） | `tests/test_conditioning.py`、`test_deadman.py`、`test_session.py` |
| 意图发布、租约门控与抢占 | 未验证 | 未实现（M2）；System 消费端缺失 |
| 采集、回放与 LeRobot 导出 | 未验证 | 未实现（M3–M4） |
| 实机遥操作 | 未验证 | 未授权任何实机会话；平台无急停 |

完整报告见 [ACCEPTANCE.md](ACCEPTANCE.md)。M0 设计已批准；M1 测试通过 L1/进程内 L2，但 M1 验收在独立代码复审于冻结产物上完成前保持 **Inconclusive**；M2 与实机未验证。

## 相关仓库

- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces)：契约来源、`TeleopCommand.msg`、Schema 与契约哈希。
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system)：特权运行时；网关、租约、仲裁器、安全与唯一运动入口。
- [`jcheng-simulation`](https://github.com/JCHENG-Robotics/jcheng-simulation)：机器人目录与域 43 离线被控对象；一次一个 plant；Profile 与 `/sim/*` 接口。
- [`jcheng-learning`](https://github.com/JCHENG-Robotics/jcheng-learning)：数据集契约、训练与策略产物；拥有 `jcheng.dataset.v1`。
- [`jcheng-studio`](https://github.com/JCHENG-Robotics/jcheng-studio)：操作台；仅网关 HTTP/WS，无 DDS 与设备。
- [`jcheng-applications`](https://github.com/JCHENG-Robotics/jcheng-applications)：任务编排与可复用网关客户端模式。
- [`jcheng-benchmark`](https://github.com/JCHENG-Robotics/jcheng-benchmark)：离线 JSONL 评分；不执行回放。
- [`jcheng-mobile`](https://github.com/JCHENG-Robotics/jcheng-mobile)：底盘意图所有者。
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops)：无人值守健康巡检与看门狗。
- [`.github`](https://github.com/JCHENG-Robotics/.github)：治理、分类、文档标准与实机工作流。

## 许可证

第三方与版权审查尚未完成；未添加 `LICENSE` 文件。详见
[LICENSE-REVIEW.md](LICENSE-REVIEW.md)。
