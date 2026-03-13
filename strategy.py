"""网格交易策略核心逻辑"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from models import FundConfig, FundData, StrategyState

logger = logging.getLogger(__name__)


class Signal(Enum):
    """交易信号"""
    BUY = "买入"
    SELL = "卖出"
    HOLD = "持有"
    INVEST = "定投"


@dataclass
class TradeSignal:
    """交易信号结果"""
    signal: Signal
    fund_data: FundData
    state: StrategyState
    position_before: int
    position_after: int
    reason: str


def evaluate(
    config: FundConfig,
    state: StrategyState,
    fund_data: FundData,
) -> TradeSignal:
    """
    根据当前净值和策略状态，判断是否触发买卖信号。

    买入条件：当前净值 <= last_buy_price × (1 - grid_spacing) 且 仓位 < max_position
    卖出条件：当前净值 >= last_sell_price × (1 + grid_spacing) 且 仓位 > min_position
    """
    current_price = fund_data.gsz
    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y-%m-%d")

    # ----- 0.1 独立定投触发判断（最高优先级，不被冷却机制拦截） -----
    if config.invest_enabled:
        # iso格式 1-7对应周一到周日
        current_weekday = today_dt.isoweekday()
        if current_weekday == config.invest_weekday:
            # 判断间隔
            should_invest = False
            if not state.last_invest_date:
                should_invest = True
            else:
                last_dt = datetime.strptime(state.last_invest_date, "%Y-%m-%d")
                if (today_dt - last_dt).days >= config.invest_interval_days:
                    should_invest = True
            
            if should_invest:
                state.last_invest_date = today_str
                # 如果定投与网格在一天，定投优先提醒。
                logger.info("策略评估: 触发【周期定投】(周%d，间隔>=%d天)", config.invest_weekday, config.invest_interval_days)
                return TradeSignal(
                    signal=Signal.INVEST,
                    fund_data=fund_data,
                    state=state,
                    position_before=state.position,
                    position_after=state.position, # 定投暂不改变网格总仓位，或由用户配置
                    reason=f"周期定投触发：买入金额/份额 {config.invest_amount}"
                )

    # ----- 0.2 日内防重机制 -----
    # 如果今天已经发生过交易或网格移动，则不再触发任何信号
    if state.last_trade_date == today_str:
        logger.info("策略评估: 基金 %s 今日(%s)已触发过网格操作，进入冷却状态", config.fund_code, today_str)
        return TradeSignal(
            signal=Signal.HOLD,
            fund_data=fund_data,
            state=state,
            position_before=state.position,
            position_after=state.position,
            reason=f"今日({today_str})已触发过网格操作，进入冷却防频次触发限制",
        )

    # ----- 1. 移动网格逻辑判断（优先处理） -----
    move_upper = state.grid_center * (1 + config.move_trigger)
    move_lower = state.grid_center * (1 - config.move_trigger)

    moved = False
    old_center = state.grid_center

    while current_price >= state.grid_center * (1 + config.move_trigger):
        state.grid_center = state.grid_center * (1 + config.grid_spacing)
        moved = True
        
    while current_price <= state.grid_center * (1 - config.move_trigger):
        state.grid_center = state.grid_center * (1 - config.grid_spacing)
        moved = True

    if moved:
        # 移动网格后，更新基准价，避免原有的旧价格阻碍新的网格区间
        state.last_buy_price = state.grid_center
        state.last_sell_price = state.grid_center
        state.last_trade_date = today_str
        logger.info(
            "触发【网格移动】: 当前净值%.4f，超出移动阈值，中心从 %.4f 移动至 %.4f",
            current_price, old_center, state.grid_center
        )

        return TradeSignal(
            signal=Signal.HOLD,
            fund_data=fund_data,
            state=state,
            position_before=state.position,
            position_after=state.position,
            reason=f"网格中心移动至 {state.grid_center:.4f}，避免同一轮轮动双杀，冷却至今",
        )

    # 计算买卖阈值
    buy_threshold = state.last_buy_price * (1 - config.grid_spacing)
    sell_threshold = state.last_sell_price * (1 + config.grid_spacing)

    logger.info(
        "策略评估: 当前净值=%.4f 中心=%.4f 买入阈值=%.4f 卖出阈值=%.4f 仓位=%d",
        current_price, state.grid_center, buy_threshold, sell_threshold, state.position,
    )

    # 买入判断
    if current_price <= buy_threshold:
        if state.position >= config.max_position:
            logger.warning("触发买入信号，但仓位已达上限(%d)，禁止买入", config.max_position)
            return TradeSignal(
                signal=Signal.HOLD,
                fund_data=fund_data,
                state=state,
                position_before=state.position,
                position_after=state.position,
                reason=f"触发买入条件（净值{current_price:.4f} <= 阈值{buy_threshold:.4f}），但仓位已达上限{config.max_position}",
            )

        new_position = state.position + config.trade_unit
        reason = (
            f"净值{current_price:.4f} <= 买入阈值{buy_threshold:.4f}"
            f"（上次买入价{state.last_buy_price:.4f} × {1 - config.grid_spacing:.2f}）"
        )
        logger.info("触发买入信号: %s", reason)

        # 更新状态
        state.last_buy_price = current_price
        state.position = new_position
        state.update_time = fund_data.gztime if fund_data.gztime else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state.last_trade_date = today_str

        return TradeSignal(
            signal=Signal.BUY,
            fund_data=fund_data,
            state=state,
            position_before=new_position - config.trade_unit,
            position_after=new_position,
            reason=reason,
        )

    # 卖出判断
    if current_price >= sell_threshold:
        if state.position <= config.min_position:
            logger.warning("触发卖出信号，但仓位已达下限(%d)，禁止卖出", config.min_position)
            return TradeSignal(
                signal=Signal.HOLD,
                fund_data=fund_data,
                state=state,
                position_before=state.position,
                position_after=state.position,
                reason=f"触发卖出条件（净值{current_price:.4f} >= 阈值{sell_threshold:.4f}），但仓位已达下限{config.min_position}",
            )

        new_position = state.position - config.trade_unit
        reason = (
            f"净值{current_price:.4f} >= 卖出阈值{sell_threshold:.4f}"
            f"（上次卖出价{state.last_sell_price:.4f} × {1 + config.grid_spacing:.2f}）"
        )
        logger.info("触发卖出信号: %s", reason)

        # 更新状态
        state.last_sell_price = current_price
        state.position = new_position
        state.update_time = fund_data.gztime if fund_data.gztime else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state.last_trade_date = today_str

        return TradeSignal(
            signal=Signal.SELL,
            fund_data=fund_data,
            state=state,
            position_before=new_position + config.trade_unit,
            position_after=new_position,
            reason=reason,
        )

    # 无触发
    logger.info("未触发交易信号，继续持有")
    return TradeSignal(
        signal=Signal.HOLD,
        fund_data=fund_data,
        state=state,
        position_before=state.position,
        position_after=state.position,
        reason=f"净值{current_price:.4f}在网格区间内（买入阈值{buy_threshold:.4f}，卖出阈值{sell_threshold:.4f}）",
    )
