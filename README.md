# alpha-azul-cc

A digital implementation of the board game **Azul** (花砖物语) with a graphical UI and MCTS AI opponent.

## Features

- Complete Azul rule implementation (2–4 players)
- Pygame-based graphical interface with tile animations
- Monte Carlo Tree Search (MCTS) AI opponent
- HiDPI/Retina display support (MacBook M1/M2)

## Requirements

- Python 3.12 or 3.13 (**Python 3.14 is not supported** — pygame 2.6.1 has a circular import bug on 3.14)
- pygame

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-username/alpha-azul-cc.git
cd alpha-azul-cc
```

### 2. Create a virtual environment

Use Python 3.12 or 3.13 explicitly:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install pygame
```

## Running

### Launch the game

```bash
python3 ui.py
```

### Play against the AI

The UI supports 2 players (5 factories). Use `--ai 1` to make player 1 an AI opponent:

```bash
python3 ui.py --ai 1
```

### Run tests

```bash
python3 test_engine.py
```

### Benchmark the AI

```bash
python3 -m ai.mcts_agent
```

## Project Structure

```
.
├── engine.py         # Core game engine (state, rules, scoring)
├── ui.py             # Pygame graphical interface
├── test_engine.py    # Unit tests
└── ai/
    └── mcts_agent.py # MCTS AI implementation
```

## Game Rules (Quick Reference)

Each round has two phases:

1. **Factory Phase** — Take all tiles of one color from a factory or the center. Leftover tiles go to the center. One tile from each draw goes to your floor if you take from the center while holding the first-player marker.
2. **Tiling Phase** — Complete pattern lines move a tile to your wall and score points based on adjacency.

**End condition:** Game ends when any player completes a full row on their wall.

**Bonuses:** +2 per completed row, +7 per completed column, +10 per completed color set.

---

# alpha-azul-cc

花砖物语（**Azul**）的数字化实现，包含图形界面与蒙特卡洛树搜索（MCTS）AI 对手。

## 功能特性

- 完整的 Azul 规则实现（支持 2–4 名玩家）
- 基于 Pygame 的图形界面，含棋子动画效果
- 蒙特卡洛树搜索（MCTS）AI 对手
- 支持 MacBook M1/M2 HiDPI / Retina 高分辨率屏幕

## 环境要求

- Python 3.12 或 3.13（**不支持 Python 3.14**——pygame 2.6.1 在 3.14 下存在循环导入 bug）
- pygame

## 安装与配置

### 1. 克隆仓库

```bash
git clone https://github.com/your-username/alpha-azul-cc.git
cd alpha-azul-cc
```

### 2. 创建虚拟环境

请明确指定 Python 3.12 或 3.13：

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install pygame
```

## 运行

### 启动游戏

```bash
python3 ui.py
```

### 与 AI 对战

UI 目前支持双人对战（5 个工厂）。用 `--ai 1` 让玩家 1 由 AI 控制：

```bash
python3 ui.py --ai 1
```

### 运行单元测试

```bash
python3 test_engine.py
```

### AI 性能基准测试

```bash
python3 -m ai.mcts_agent
```

## 项目结构

```
.
├── engine.py         # 核心游戏引擎（状态管理、规则、计分）
├── ui.py             # Pygame 图形界面
├── test_engine.py    # 单元测试
└── ai/
    └── mcts_agent.py # MCTS AI 实现
```

## 游戏规则（速查）

每轮分为两个阶段：

1. **拿砖阶段** — 从工厂或中央区域取走同一颜色的所有花砖，剩余花砖留在中央。持有先手标记时从中央取砖，需将一块花砖放入罚分区。
2. **铺砖阶段** — 已填满的样式行将一块花砖移至墙面并按相邻关系计分。

**游戏结束条件：** 任意玩家在墙面上完成完整一行时游戏结束。

**结算加分：** 完成一行 +2 分，完成一列 +7 分，集齐一种颜色 +10 分。
