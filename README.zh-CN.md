# jcheng-teleop

> 状态：**实验性**，2026-11-26。版本 0.1.0。
> 仅准入的骨架：本仓库定义遥操作意图边界，但不包含操作员输入适配器、
> 不包含 ROS 节点，也不发布任何意图。运行中的机器人不会使用其中任何内容。
> 本文为英文主文档的中文对照；如有歧义，以 [README.md](README.md) 为准。

`jcheng-teleop` 是 JCHENG 生态的 L3 遥操作能力。它的职责是把操作员输入转化为
有界、受租约约束、受 deadman 保护的**遥操作意图**，交给系统层。意图只是建议：
运动仲裁器对其采样，系统层在有任何东西移动之前应用租约、deadman、限幅与停止
锁存。本仓库绝不直接命令硬件、绝不打开设备，也绝不成为运动权威。

契约已经存在。`TeleopCommand.msg` 已在 `jcheng-interfaces` v0.1.0 中定义并预留。
该流只在第一次遥操作试点时启用；v0.1.0 不发布它。

## 范围与边界

| 项 | 本仓库 |
|---|---|
| 层 | L3 能力（`capability.yaml`） |
| 输入 | 来自本仓库之外适配器的操作员输入样本（M1 起）；来自系统层的机器人、安全与租约状态（M2） |
| 输出 | 计划中的 `/jcheng/intent/teleop` 遥操作意图流，域 42（M2）；v0.1.0 无输出 |
| 运动授权 | v0.1.0 无（`safety.class: offline`，运行时表面为空） |
| 硬件访问 | `none` |
| 拥有的设备 | 无；物理输入适配器位于操作员侧，在能力边界之外 |
| 禁止 | 设备访问、厂商话题、`/move_action`、`/cmd_vel`、`ExecuteMotion`、硬件命令、伪造状态 |

系统层是运动的唯一来源。本仓库只发布意图，绝不发布轨迹或伺服/电机命令。
底盘意图流属于 `jcheng-mobile`；遥操作不发布它。

## 目录

```text
jcheng-teleop/
├── capability.yaml                 # 准入清单（offline，hardware_access: none）
├── docs/
│   ├── ARCHITECTURE.md             # 输入、意图与系统三个平面
│   ├── INPUT.md                    # 输入样本、调理与 deadman 规则
│   └── INTEGRATION.md              # 准入、租约、抢占与失败语义
├── tests/
│   ├── test_contract.py            # 清单与文档集检查
│   └── test_no_hardware.py         # 无设备 / 无运动静态扫描
├── scripts/check_repo_gate.sh      # 仓库门禁（本地与 CI）
├── evidence/20261126_scaffold/     # M0 证据记录
├── VERSION
├── README.md / README.zh-CN.md
├── ROADMAP.md / CHANGELOG.md / ACCEPTANCE.md
└── LICENSE-REVIEW.md
```

## 依赖

- Python 3.10 或更新版本（CI 使用 3.12）、`pytest` 8.3.4、`PyYAML` 6.0.2。
- v0.1.0 不需要 ROS。只有 M2 出现意图节点时才需要 ROS 2 Humble。
- 门禁不需要任何输入设备。物理手柄、方向盘或示教器适配器位于操作员侧，
  本仓库绝不打开它们。
- 会话记录存放在本仓库之外；录制数据绝不提交。

## 快速开始

```bash
python3 -m pytest -q tests
bash scripts/check_repo_gate.sh
```

门禁检查文档集、准入清单、相对链接、密钥、模型权重、录制数据与两个测试模块。
它不接触机器人，也不打开任何设备。

## 验证状态

| 声明 | 状态 | 证据 |
|---|---|---|
| 仓库门禁与单元测试通过 | 部分验证（本地 2026-11-26；CI 待运行） | `evidence/20261126_scaffold/` |
| 清单声明 `hardware_access: none` 且运行时表面为空 | 已验证（L0，2026-11-26） | `tests/test_contract.py` |
| 仓库中不存在设备、厂商话题或运动调用 | 已验证（L0，2026-11-26） | `tests/test_no_hardware.py` |
| 遥操作意图行为 | 未验证 | 尚未实现（M1–M2） |

完整报告：[ACCEPTANCE.md](ACCEPTANCE.md)。

## 相关仓库

- [`jcheng-interfaces`](https://github.com/JCHENG-Robotics/jcheng-interfaces) — 契约来源、`TeleopCommand.msg` 与契约哈希。
- [`jcheng-system`](https://github.com/JCHENG-Robotics/jcheng-system) — 特权运行时；租约、仲裁、运动与硬件访问的唯一所有者。
- [`jcheng-mobile`](https://github.com/JCHENG-Robotics/jcheng-mobile) — 移动底盘能力与底盘意图流。
- [`jcheng-perception`](https://github.com/JCHENG-Robotics/jcheng-perception) — 建议感知目标；供操作员只读参考。
- [`jcheng-ops`](https://github.com/JCHENG-Robotics/jcheng-ops) — 无人值守健康检查与看门狗。
- [`.github`](https://github.com/JCHENG-Robotics/.github) — 生态路线图、变更日志、验收与仓库分类。

## 许可证

第三方与版权审查尚未完成；尚未添加 `LICENSE` 文件。见
[LICENSE-REVIEW.md](LICENSE-REVIEW.md)。
