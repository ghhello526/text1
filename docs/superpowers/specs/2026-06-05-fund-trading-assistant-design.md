# 守基宝 4% 定投法 — 可视化交易辅助软件设计文档

**日期**: 2026-06-05  
**技术栈**: PyQt6 + matplotlib + pandas + akshare + SQLite  
**状态**: 设计完成，待实施

---

## 一、项目概述

基于"守基宝 4% 定投法"策略文档，设计一个 PyQt6 桌面可视化软件，辅助用户对多只基金（默认4只，最多6只）进行交易决策。软件通过三线估值 + 三策略体系（建仓/波动/止盈），在合适的时机给出合适的操作建议。

### 核心能力

| 模块 | 功能 | 入口 |
|------|------|------|
| **模式A：实时交易辅助** | 信号灯 + 操作计划 + 交易记录闭环 | 顶部"实时交易"按钮 |
| **模式B：策略回测** | 三策略体系回测 + 收益分析 + 图表标注 | 顶部"策略回测"按钮 |

---

## 二、整体架构

### 2.1 单窗口双面板架构

```
┌─────────────────────────────────────────────────────┐
│                    MainWindow                         │
│  ┌───────────────────────────────────────────────┐  │
│  │ 顶部工具栏：[实时交易] [策略回测]              │  │
│  ├──────────────┬────────────────────────────────┤  │
│  │  左侧面板    │      右侧面板（随模式切换）     │  │
│  │  基金列表    │  A: 信号灯+操作计划+交易记录    │  │
│  │  信号灯摘要  │  B: 回测参数+图表+结果          │  │
│  │  + 添加基金  │                                │  │
│  │  ⚙ 资金设置  │                                │  │
│  └──────────────┴────────────────────────────────┘  │
│  状态栏                                              │
└─────────────────────────────────────────────────────┘
```

### 2.2 代码模块划分

| 层 | 文件 | 职责 | 状态 |
|---|---|---|---|
| UI | `ui/main_window.py` | 主窗口框架、模式切换、布局管理 | 重写 |
| UI | `ui/fund_list_panel.py` | 左侧基金列表面板，信号灯摘要 | 新建 |
| UI | `ui/trade_panel.py` | 模式A：信号灯+操作计划+交易记录 | 新建 |
| UI | `ui/backtest_panel.py` | 模式B：回测参数+图表+结果 | 新建 |
| UI | `ui/chart_widget.py` | 图表绘制，增加三线标注能力 | 改造 |
| 服务 | `services/strategy_engine.py` | 三策略引擎核心逻辑 | 新建 |
| 服务 | `services/signal_generator.py` | 实时信号生成器 | 新建 |
| 服务 | `services/fund_service.py` | 基金数据获取（akshare） | 保留 |
| 数据 | `services/database.py` | SQLite 数据访问层 | 新建 |
| 数据 | `services/models.py` | 数据模型定义 | 新建 |
| 入口 | `main.py` | 应用入口 | 保留 |

### 2.3 与现有代码的关系

- **保留**: `fund_service.py`、`chart_widget.py`（改造）、`main.py`
- **替换**: `investment_strategy.py` → `strategy_engine.py`
- **替换**: `optimizer.py` → 集成到 `backtest_panel.py`
- **重写**: `main_window.py` → 新架构

---

## 三、数据模型（SQLite）

数据库文件路径: `data/winwin.db`（应用目录下）

### 3.1 Fund 表（基金）

```sql
CREATE TABLE fund (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,       -- 6位基金代码
    name TEXT NOT NULL,              -- 基金名称
    fund_type TEXT,                  -- 类型标签（恒生科技/消费/创业板/电池/自定义）
    main_ratio REAL DEFAULT 0.6,    -- 主仓占比
    swing_ratio REAL DEFAULT 0.4,   -- 波动仓占比
    opportunity_line REAL,           -- 机会线对应净值
    middle_line REAL,                -- 中位线对应净值
    danger_line REAL,                -- 危险线对应净值
    per_share_amount REAL DEFAULT 1250.0, -- 每份金额
    total_shares_count INTEGER DEFAULT 10, -- 总份数N
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### 3.2 Position 表（持仓状态）

```sql
CREATE TABLE position (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER NOT NULL REFERENCES fund(id),
    total_shares REAL DEFAULT 0.0,       -- 当前持有总份额
    total_invested REAL DEFAULT 0.0,     -- 累计已投入金额
    main_shares REAL DEFAULT 0.0,        -- 主仓份额
    swing_shares REAL DEFAULT 0.0,       -- 波动仓份额
    anchor_nav REAL,                     -- 当前参考锚点净值
    highest_nav REAL,                    -- 买入后最高净值（用于回撤判断）
    consecutive_buy INTEGER DEFAULT 0,   -- 当前连续买入计数
    consecutive_sell INTEGER DEFAULT 0,  -- 当前连续卖出计数
    current_strategy TEXT DEFAULT 'none', -- 当前策略(build/swing/take_profit/none)
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(fund_id)
);
```

### 3.3 Trade 表（交易记录）

```sql
CREATE TABLE trade (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER NOT NULL REFERENCES fund(id),
    trade_date TEXT NOT NULL,            -- 交易日期
    trade_type TEXT NOT NULL,            -- 建仓/买入/卖出/止盈/清仓
    strategy_type TEXT,                  -- build/swing/take_profit
    nav REAL NOT NULL,                   -- 交易时净值
    amount REAL NOT NULL,                -- 交易金额
    shares REAL NOT NULL,                -- 交易份额
    trigger_reason TEXT,                 -- 触发原因说明
    confirmed INTEGER DEFAULT 0,         -- 是否已确认（0=待确认, 1=已确认）
    created_at TEXT DEFAULT (datetime('now'))
);
```

### 3.4 UserConfig 表（用户配置）

```sql
CREATE TABLE user_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- 预置键：age, total_assets, fund_count, risk_ratio
```

---

## 四、三策略引擎设计

### 4.1 策略判定流程

```
输入: 当前净值 nav + 三线位置 + Position状态
  │
  ├─ nav ≤ opportunity_line ────→ 【建仓策略】
  ├─ opportunity_line < nav ≤ middle_line ──→ 【波动策略】
  ├─ middle_line < nav ≤ danger_line ──→ 【止盈策略-减仓】
  └─ nav > danger_line ────→ 【止盈策略-清仓监控】
  │
  ▼
根据策略规则 + anchor_nav + consecutive计数 → 生成Signal
```

### 4.2 建仓策略（机会线以下）

| 规则 | 触发条件 | 操作 |
|------|---------|------|
| 规则1 | 以最近买入净值为锚，下跌5% | 买入1份 |
| 规则2 | 记录买入后最高净值(highest_nav)，从最高点回落5% | 买入1份 |
| 规则3 | 最后一笔是卖出，以卖出净值为锚，下跌5% | 买入1份 |
| 仓位上限 | 持仓占比达70% | 暂停操作 |

方向: **只买不卖**

### 4.3 波动策略（机会线~中位线）

| 规则 | 触发条件 | 操作 |
|------|---------|------|
| 规则1 | 以最近买入净值为锚，上涨5% | 卖出1份（波动仓） |
| 规则2 | 以最近买入净值为锚，下跌5% | 买入1份 |
| 规则3 | 最后一笔是卖出，以卖出净值为锚，下跌5% | 买入1份 |
| 循环 | 卖出后重置锚点，继续监控 | 重复 |

方向: **低买高卖，循环执行**

### 4.4 止盈策略（中位线以上）

| 区间 | 操作 | 目标 |
|------|------|------|
| 中位线~危险线 | 分批减仓 | 仓位从50%降至30% |
| > 危险线 | 继续减仓 | 保留≤10%底仓 |
| 回撤触发 | 从highest_nav回撤5% | 全部清仓 |

方向: **分批退出，锁定利润**

### 4.5 主仓与波动仓管理

```
买入分配:
  main_shares += 买入份额 × fund.main_ratio
  swing_shares += 买入份额 × fund.swing_ratio

卖出优先级:
  波动策略卖出 → 仅从 swing_shares 扣减
  止盈策略卖出 → 先从 swing_shares，不足时从 main_shares 补足
```

### 4.6 Signal 输出结构

```python
@dataclass
class TradingSignal:
    action: str              # "buy" | "sell" | "hold"
    urgency: str             # "high" | "medium" | "low"
    strategy: str            # "build" | "swing" | "take_profit"
    suggested_amount: float  # 建议操作金额
    suggested_shares: float  # 建议操作份额
    trigger_reason: str      # 触发原因说明
    next_trigger_up: float   # 下一个上涨触发净值
    next_trigger_down: float # 下一个下跌触发净值
    position_pct: float      # 当前仓位百分比
    zone: str                # 当前区间名称
```

### 4.7 回测模式复用

回测模式与实时模式共用 `strategy_engine.py`：
- **实时模式**: 单次调用，喂入当前净值，返回1个Signal
- **回测模式**: 遍历历史净值序列，逐日生成Signal并自动确认，输出完整交易记录列表

---

## 五、UI 详细设计

### 5.1 模式A：实时交易辅助面板（trade_panel.py）

从上到下三个区域：

**① 信号灯区**
- 醒目的操作指示（买入🟢 / 卖出🔴 / 持有🟡 / 未建仓⚪）
- 当前策略类型、当前净值、锚点净值、当前仓位

**② 操作计划区**
- 建议操作方向和金额
- 触发原因说明
- 下一触发条件（上涨到X卖出 / 下跌到Y买入）
- 「确认已操作」和「跳过本次」按钮

**③ 交易记录区**
- 可滚动的交易流水表格（日期、类型、金额、净值、策略、确认状态）
- 支持手动添加/编辑/删除记录

**交互逻辑**:
- 点击"确认已操作" → 写入Trade表 → 更新Position → 刷新Signal
- 点击"跳过本次" → 不写入，信号保持
- 手动编辑交易记录 → 重新计算Position状态

### 5.2 模式B：策略回测面板（backtest_panel.py）

从上到下三个区域：

**① 回测参数区**
- 三线设定（机会线/中位线/危险线净值输入框）
- 回测日期范围选择
- 单份金额、总份数、主仓/波动仓比例

**② 图表区**
- 净值走势图（复用 chart_widget.py）
- 三条估值线水平标注（红/黄/绿虚线）
- 买卖点标记（绿色▲买入 / 红色▼卖出）
- 区间背景色渐变（可选）

**③ 回测结果区**
- 关键指标：总收益率、买入次数、卖出次数、最大回撤
- 策略分布统计（建仓X次 / 波动Y次 / 止盈Z次）
- 可展开的交易明细表

### 5.3 左侧基金列表面板（fund_list_panel.py）

- 标题显示 "我的基金 (N/6)"
- 每只基金一个卡片：信号灯颜色 + 基金名称 + 当前净值 + 仓位进度条
- 点击选中后右侧面板切换到该基金的详情
- 底部「+ 添加基金」按钮（弹窗输入基金代码）
- 底部「⚙ 资金设置」按钮（设置年龄、总资产等）

### 5.4 信号灯颜色含义

| 颜色 | 含义 | 条件 |
|------|------|------|
| 🟢 绿色 | 建议买入 | 净值触发买入条件 |
| 🔴 红色 | 建议卖出 | 净值触发卖出条件 |
| 🟡 黄色 | 持有观望 | 接近触发但未到阈值 |
| ⚪ 灰色 | 未建仓 | 无持仓或无数据 |

---

## 六、数据流

### 6.1 实时交易模式数据流

```
用户打开软件
  → 从SQLite加载所有Fund和Position
  → 对每只已建仓基金调用 akshare 获取最新净值
  → 调用 signal_generator 生成每只基金的 TradingSignal
  → 左侧列表渲染信号灯颜色
  → 用户点击某基金 → 右侧面板显示详细Signal和操作建议
  → 用户点击"确认已操作" → 写入Trade → 更新Position → 刷新Signal
```

### 6.2 策略回测模式数据流

```
用户选中某基金，切换到回测模式
  → 从 akshare 拉取该基金完整历史净值
  → 用户设定三线位置 + 日期范围 + 参数
  → 调用 strategy_engine 遍历净值序列执行三策略
  → 输出完整交易记录列表 + 收益统计
  → chart_widget 绘制净值图 + 三线标注 + 买卖点标记
```

---

## 七、四只基金策略配置建议

| 基金 | 推荐主仓:波动仓 | 推荐主策略 | 特别提醒 |
|------|----------------|-----------|---------|
| 恒生科技 | 3:7 | 波动策略 | 港股无涨跌停，极端行情需保留充足现金 |
| 消费 | 7:3 | 建仓策略 | PE估值区间明确，适合历史百分位判断三线 |
| 创业板 | 5:5 | 波动策略+ | 回撤幅度大，建仓时适当拉大加仓间隔 |
| 电池/新能源 | 6:4 | 建仓→止盈 | 周期板块不可恋战，到危险线必须止盈 |

---

## 八、技术约束

- **Python 3.11** + **PyQt6** (GUI框架)
- **matplotlib** (图表绘制，通过 `backend_qtagg` 嵌入PyQt6)
- **pandas** (数据处理)
- **akshare** (基金净值数据源)
- **SQLite3** (内置，无需额外依赖)
- 阈值默认5%，三线位置由用户手动设定
- 不做自动交易，仅提供信号和操作建议
- 所有网络请求在QThread中执行，不阻塞UI

---

## 九、不在本期范围内

- 自动交易执行（本软件仅辅助决策）
- 估值百分位自动获取（需用户参考公众号手动设定三线）
- 升级版多因子策略（策略升级设计文档中的内容，后续迭代）
- 基金间相关性对冲
- 通知推送功能

---

*参考来源：守基宝 4% 定投法（研究员雷牛牛）*
