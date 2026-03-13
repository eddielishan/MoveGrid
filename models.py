"""数据模型定义"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FundConfig:
    """基金策略配置"""
    fund_code: str
    grid_spacing: float = 0.04       # 网格间距，默认4%
    max_position: int = 20           # 最大仓位
    min_position: int = 0            # 最小仓位
    initial_position: int = 10       # 初始仓位
    trade_unit: int = 1              # 单次交易单位
    initial_price: float = 0         # 初始基准价，0表示使用实时净值
    move_trigger: float = 0.08       # 触发移动网格中心阈值，默认8% (2个网格)
    
    # 定投配置（可选）
    invest_enabled: bool = False     # 是否开启定投
    invest_amount: float = 1000.0    # 每次定投金额或份额
    invest_interval_days: int = 14   # 定投间隔天数（14 = 两周）
    invest_weekday: int = 4          # 定投触发星期几（1-7，4 = 周四）


@dataclass
class StrategyState:
    """策略运行状态"""
    fund_code: str
    grid_center: float
    last_buy_price: float
    last_sell_price: float
    position: int
    update_time: str = ""
    last_trade_date: str = ""    # 最后一次发生交易（或网格移动）的日期，格式 YYYY-MM-DD
    last_invest_date: str = ""   # 最后一次发生定投提醒的日期，格式 YYYY-MM-DD

    def to_dict(self) -> dict:
        return {
            "fund_code": self.fund_code,
            "grid_center": getattr(self, "grid_center", self.last_buy_price),  # 兼容旧版本
            "last_buy_price": self.last_buy_price,
            "last_sell_price": self.last_sell_price,
            "position": self.position,
            "update_time": self.update_time,
            "last_trade_date": getattr(self, "last_trade_date", ""),
            "last_invest_date": getattr(self, "last_invest_date", ""),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyState":
        return cls(
            fund_code=data["fund_code"],
            grid_center=data.get("grid_center", data["last_buy_price"]),  # 兼容没有该字段的旧数据
            last_buy_price=data["last_buy_price"],
            last_sell_price=data["last_sell_price"],
            position=data["position"],
            update_time=data.get("update_time", ""),
            last_trade_date=data.get("last_trade_date", ""),
            last_invest_date=data.get("last_invest_date", ""),
        )


@dataclass
class FundData:
    """基金净值数据"""
    fund_code: str    # 基金代码
    name: str         # 基金名称
    gsz: float        # 当前估值
    gszzl: float      # 涨跌幅（%）
    gztime: str       # 更新时间
