"""数据模型定义 — 守基宝交易辅助系统"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


# ==================== 枚举 ====================


class TradeType(Enum):
    """交易类型"""

    INITIAL = "建仓"
    BUY = "买入"
    SELL = "卖出"
    TAKE_PROFIT = "止盈"
    FINAL = "清仓"


class StrategyType(Enum):
    """策略类型"""

    BUILD = "build"        # 建仓策略
    SWING = "swing"        # 波动策略
    TAKE_PROFIT = "take_profit"  # 止盈策略
    NONE = "none"          # 无策略（未建仓）


class SignalAction(Enum):
    """信号操作方向"""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class SignalUrgency(Enum):
    """信号紧急程度"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Zone(Enum):
    """估值区间"""

    UNDERVALUED = "undervalued"       # 机会线以下（低估）
    FAIR = "fair"                     # 机会线~中位线（合理）
    OVERVALUED = "overvalued"         # 中位线~危险线（偏高）
    BUBBLE = "bubble"                 # 危险线以上（泡沫）


# ==================== 数据模型 ====================


@dataclass
class Fund:
    """基金模型"""

    id: int = 0
    code: str = ""
    name: str = ""
    fund_type: str = ""               # 恒生科技/消费/创业板/电池/自定义
    main_ratio: float = 0.6           # 主仓占比
    swing_ratio: float = 0.4          # 波动仓占比
    opportunity_line: float | None = None  # 机会线净值
    middle_line: float | None = None       # 中位线净值
    danger_line: float | None = None       # 危险线净值
    per_share_amount: float = 1250.0  # 每份金额
    total_shares_count: int = 10      # 总份数N
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Position:
    """持仓状态模型"""

    id: int = 0
    fund_id: int = 0
    total_shares: float = 0.0         # 当前持有总份额
    total_invested: float = 0.0       # 累计已投入金额
    main_shares: float = 0.0          # 主仓份额
    swing_shares: float = 0.0         # 波动仓份额
    anchor_nav: float | None = None   # 当前参考锚点净值
    highest_nav: float | None = None  # 买入后最高净值
    consecutive_buy: int = 0          # 当前连续买入计数
    consecutive_sell: int = 0         # 当前连续卖出计数
    current_strategy: str = "none"    # 当前策略
    updated_at: str = ""


@dataclass
class Trade:
    """交易记录模型"""

    id: int = 0
    fund_id: int = 0
    trade_date: str = ""              # 交易日期 YYYY-MM-DD
    trade_type: str = ""              # 建仓/买入/卖出/止盈/清仓
    strategy_type: str = ""           # build/swing/take_profit
    nav: float = 0.0                  # 交易时净值
    amount: float = 0.0               # 交易金额
    shares: float = 0.0               # 交易份额
    trigger_reason: str = ""          # 触发原因说明
    confirmed: int = 0                # 是否已确认（0=待确认, 1=已确认）
    created_at: str = ""


@dataclass
class UserConfig:
    """用户配置"""

    key: str = ""
    value: str = ""


# ==================== 信号与结果 ====================


@dataclass
class TradingSignal:
    """交易信号"""

    action: SignalAction = SignalAction.HOLD
    urgency: SignalUrgency = SignalUrgency.LOW
    strategy: StrategyType = StrategyType.NONE
    suggested_amount: float = 0.0     # 建议操作金额
    suggested_shares: float = 0.0     # 建议操作份额
    trigger_reason: str = ""          # 触发原因
    next_trigger_up: float = 0.0      # 下一个上涨触发净值
    next_trigger_down: float = 0.0    # 下一个下跌触发净值
    position_pct: float = 0.0         # 当前仓位百分比
    zone: Zone = Zone.FAIR            # 当前估值区间
    current_nav: float = 0.0          # 当前净值
    anchor_nav: float = 0.0           # 锚点净值


@dataclass
class BacktestTrade:
    """回测交易记录"""

    trade_date: date | None = None
    trade_type: TradeType = TradeType.BUY
    strategy_type: StrategyType = StrategyType.NONE
    nav: float = 0.0
    amount: float = 0.0
    shares: float = 0.0
    trigger_reason: str = ""
    position_pct: float = 0.0         # 交易后仓位百分比
    total_value: float = 0.0          # 交易后总资产价值


@dataclass
class BacktestResult:
    """回测结果"""

    trades: list[BacktestTrade] = field(default_factory=list)
    total_investment: float = 0.0     # 总投入
    final_value: float = 0.0          # 最终总资产
    total_return_rate: float = 0.0    # 总收益率
    max_drawdown: float = 0.0         # 最大回撤
    buy_count: int = 0
    sell_count: int = 0
    build_count: int = 0              # 建仓策略触发次数
    swing_count: int = 0              # 波动策略触发次数
    take_profit_count: int = 0        # 止盈策略触发次数
    start_date: date | None = None
    end_date: date | None = None
