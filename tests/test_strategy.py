"""网格交易策略单元测试"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
import pytest
from models import FundConfig, FundData, StrategyState
from strategy import evaluate, Signal


def make_fund_data(gsz: float) -> FundData:
    """创建测试用基金数据"""
    return FundData(
        fund_code="018387",
        name="测试基金",
        gsz=gsz,
        gszzl=0.0,
        gztime="2026-03-12 15:00",
    )


def make_config(**kwargs) -> FundConfig:
    """创建测试用配置"""
    defaults = {
        "fund_code": "018387",
        "grid_spacing": 0.04,
        "max_position": 20,
        "min_position": 0,
        "initial_position": 10,
        "trade_unit": 1,
    }
    defaults.update(kwargs)
    return FundConfig(**defaults)


def make_state(**kwargs) -> StrategyState:
    """创建测试用策略状态"""
    defaults = {
        "fund_code": "018387",
        "grid_center": 1.0,
        "last_buy_price": 1.0,
        "last_sell_price": 1.0,
        "position": 10,
        "last_trade_date": "2026-03-01",  # 默认在过去，不触发冷却
    }
    defaults.update(kwargs)
    return StrategyState(**defaults)


class TestBuySignal:
    """买入信号测试"""

    def test_trigger_buy(self):
        """净值下跌4%，触发买入"""
        config = make_config()
        state = make_state(last_buy_price=1.0, position=10)
        fund = make_fund_data(gsz=0.96)  # 刚好跌4%

        result = evaluate(config, state, fund)

        assert result.signal == Signal.BUY
        assert result.position_before == 10
        assert result.position_after == 11
        assert state.last_buy_price == 0.96
        assert state.position == 11

    def test_trigger_buy_below_threshold(self):
        """净值跌超过4%，触发买入"""
        config = make_config(move_trigger=0.15) # 调高移动阈值避免干扰
        state = make_state(last_buy_price=1.0, position=5)
        fund = make_fund_data(gsz=0.90)  # 跌了10%

        result = evaluate(config, state, fund)

        assert result.signal == Signal.BUY
        assert result.position_after == 6

    def test_no_buy_above_threshold(self):
        """净值跌不到4%，不触发"""
        config = make_config()
        state = make_state(last_buy_price=1.0, position=10)
        fund = make_fund_data(gsz=0.97)  # 跌3%

        result = evaluate(config, state, fund)

        assert result.signal == Signal.HOLD
        assert state.position == 10

    def test_buy_blocked_max_position(self):
        """仓位已满，禁止买入"""
        config = make_config(max_position=20)
        state = make_state(last_buy_price=1.0, position=20)
        fund = make_fund_data(gsz=0.96)

        result = evaluate(config, state, fund)

        assert result.signal == Signal.HOLD
        assert state.position == 20
        assert "上限" in result.reason


class TestSellSignal:
    """卖出信号测试"""

    def test_trigger_sell(self):
        """净值上涨4%，触发卖出"""
        config = make_config()
        state = make_state(last_sell_price=1.0, position=10)
        fund = make_fund_data(gsz=1.04)  # 涨4%

        result = evaluate(config, state, fund)

        assert result.signal == Signal.SELL
        assert result.position_before == 10
        assert result.position_after == 9
        assert state.last_sell_price == 1.04
        assert state.position == 9

    def test_trigger_sell_above_threshold(self):
        """净值涨超4%，触发卖出"""
        config = make_config(move_trigger=0.15) # 调高移动阈值避免干扰
        state = make_state(last_sell_price=1.0, position=15)
        fund = make_fund_data(gsz=1.10)  # 涨10%

        result = evaluate(config, state, fund)

        assert result.signal == Signal.SELL
        assert result.position_after == 14

    def test_no_sell_below_threshold(self):
        """净值涨不到4%，不触发"""
        config = make_config()
        state = make_state(last_sell_price=1.0, position=10)
        fund = make_fund_data(gsz=1.03)  # 涨3%

        result = evaluate(config, state, fund)

        assert result.signal == Signal.HOLD
        assert state.position == 10

    def test_sell_blocked_min_position(self):
        """仓位已空，禁止卖出"""
        config = make_config(min_position=0)
        state = make_state(last_sell_price=1.0, position=0)
        fund = make_fund_data(gsz=1.04)

        result = evaluate(config, state, fund)

        assert result.signal == Signal.HOLD
        assert state.position == 0
        assert "下限" in result.reason


class TestConsecutiveGrids:
    """连续多次网格触发测试"""

    def test_consecutive_buys(self):
        """连续下跌触发多次买入"""
        config = make_config(move_trigger=0.15)
        state = make_state(last_buy_price=1.0, position=10)

        # 第一次买入：1.0 → 0.96
        fund1 = make_fund_data(gsz=0.96)
        result1 = evaluate(config, state, fund1)
        assert result1.signal == Signal.BUY
        assert state.position == 11
        assert state.last_buy_price == 0.96

        # 第二次买入：0.96 → 0.9216 (需跨日)
        state.last_trade_date = "2026-03-02" # 模拟上一次交易是昨天
        fund2 = make_fund_data(gsz=0.92)
        # 将 data time 也设为新的一天，保证更新逻辑正确
        fund2.gztime = "2026-03-13 15:00"
        result2 = evaluate(config, state, fund2)
        assert result2.signal == Signal.BUY
        assert state.position == 12
        assert state.last_buy_price == 0.92

    def test_consecutive_sells(self):
        """连续上涨触发多次卖出"""
        config = make_config(move_trigger=0.15)
        state = make_state(last_sell_price=1.0, position=10)

        # 第一次卖出：1.0 → 1.04
        fund1 = make_fund_data(gsz=1.04)
        result1 = evaluate(config, state, fund1)
        assert result1.signal == Signal.SELL
        assert state.position == 9
        assert state.last_sell_price == 1.04

        # 第二次卖出：1.04 → 1.0816 (需跨日)
        state.last_trade_date = "2026-03-02" 
        fund2 = make_fund_data(gsz=1.09)
        fund2.gztime = "2026-03-13 15:00"
        result2 = evaluate(config, state, fund2)
        assert result2.signal == Signal.SELL
        assert state.position == 8
        assert state.last_sell_price == 1.09


class TestMoveGrid:
    """移动网格机制测试"""

    def test_move_grid_up(self):
        """净值上涨超移动阈值，网格上移，同步更新买卖阈值"""
        config = make_config(grid_spacing=0.04, move_trigger=0.08)
        state = make_state(grid_center=1.0, last_buy_price=1.0, last_sell_price=1.0, position=10)
        
        # 价格突然涨到 1.08 （刚好达到阈值）
        fund = make_fund_data(gsz=1.08)
        result = evaluate(config, state, fund)
        
        # 网格中心上移 1.0 * (1 + 0.04) = 1.04
        assert state.grid_center == 1.04
        assert state.last_buy_price == 1.04
        assert state.last_sell_price == 1.04
        
        # 此回合因为最新价1.08大于新的卖出阈值(1.04 * 1.04 = 1.0816)？ 
        # 1.04 * 1.04 = 1.0816，所以 1.08 未达到卖出阈值，应持有
        assert result.signal == Signal.HOLD

    def test_move_grid_down(self):
        """净值下跌超移动阈值，网格下移"""
        config = make_config(grid_spacing=0.04, move_trigger=0.08)
        state = make_state(grid_center=1.0, last_buy_price=1.0, last_sell_price=1.0, position=10)
        
        # 价格跌到 0.92 （刚到底部阈值）
        fund = make_fund_data(gsz=0.92)
        result = evaluate(config, state, fund)
        
        # 注：因为触发了跨距网格移动，移动后触发了单日限制，所以不会再触发买入，而是返回 HOLD 冷却。
        # 因此，这里的 last_buy_price 和 last_sell_price 都停留在移动网格后的 0.96。
        
        assert state.last_buy_price == 0.96
        assert state.last_sell_price == 0.96
        
        # 冷却结束前，不会触发真正的买入，保护交易！
        assert result.signal == Signal.HOLD

    def test_move_grid_multiple_steps(self):
        """净值剧烈变动，一次性跨越多个移动阈值，网格应连续移动"""
        config = make_config(grid_spacing=0.04, move_trigger=0.08)
        state = make_state(grid_center=1.0, last_buy_price=1.0, last_sell_price=1.0, position=10)
        
        # 价格直接暴涨到 1.18 （上涨 18%）
        # 第一次判定 1.18 >= 1.0 * 1.08  -> 中心上移到 1.04
        # 第二次判定 1.18 >= 1.04 * 1.08=1.1232 -> 中心上移到 1.04 * 1.04 = 1.0816
        # 第三次判定 1.18 >= 1.0816 * 1.08=1.1681 -> 中心上移到 1.0816 * 1.04 = 1.124864
        # 第四次判定 1.18 < 1.124864 * 1.08=1.2148 -> 停止移动
        fund = make_fund_data(gsz=1.18)
        result = evaluate(config, state, fund)
        
        # 中心应连续上移 3 次 (1.0 * 1.04^3)
        expected_center = 1.0 * 1.04 * 1.04 * 1.04
        assert abs(state.grid_center - expected_center) < 0.0001
        # 预期买入和卖出基准价是网格中心
        assert state.last_buy_price == expected_center
        assert state.last_sell_price == expected_center
        # 网格移动触发了冷却机制，因此不应该发送真实的买卖信号，而是 HOLD
        assert result.signal == Signal.HOLD

    def test_no_move_in_range(self):
        """净值在移动阈值内部，不移动网格中心"""
        config = make_config(grid_spacing=0.04, move_trigger=0.08)
        state = make_state(grid_center=1.0, last_buy_price=1.0, last_sell_price=1.0, position=10)
        
        fund = make_fund_data(gsz=1.05)
        result = evaluate(config, state, fund)
        
        assert state.grid_center == 1.0
        assert result.signal == Signal.SELL  # 触发原有的卖出（1.05 > 1.04）


class TestHoldSignal:
    """持有信号测试"""

    def test_hold_in_range(self):
        """净值在网格区间内，保持持有"""
        config = make_config()
        state = make_state(last_buy_price=1.0, last_sell_price=1.0)
        fund = make_fund_data(gsz=1.0)
        
        result = evaluate(config, state, fund)
        assert result.signal == Signal.HOLD


class TestInvestSignal:
    """定投功能测试"""
    from datetime import datetime
    
    def test_invest_trigger(self, monkeypatch):
        """满足定投间隔并匹配定投日，则触发定投"""
        # 配置定投：每14天、周三定投
        config = make_config(invest_enabled=True, invest_interval_days=14, invest_weekday=3, invest_amount=500)
        # 且上次定投是半个月前
        state = make_state(last_invest_date="2026-03-01")
        fund = make_fund_data(gsz=1.0)
        
        # mock datetime.now 使今天是 2026-03-18 (星期三, 距离 3-1 > 14天)
        class MockDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                from datetime import datetime as real_datetime
                return real_datetime(2026, 3, 18, 15, 0, 0)
        
        import strategy
        monkeypatch.setattr(strategy, 'datetime', MockDatetime)
        
        result = strategy.evaluate(config, state, fund)
        
        assert result.signal == strategy.Signal.INVEST
        assert state.last_invest_date == "2026-03-18"
        assert "500" in result.reason
        
    def test_invest_not_trigger_wrong_day(self, monkeypatch):
        """即使间隔到了，但不是定投日，也不会触发"""
        config = make_config(invest_enabled=True, invest_interval_days=14, invest_weekday=3)  # 周三
        state = make_state(last_invest_date="2026-03-01")
        fund = make_fund_data(gsz=1.0)
        
        # mock 今天是 2026-03-17 (星期二)
        class MockDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                from datetime import datetime as real_datetime
                return real_datetime(2026, 3, 17, 15, 0, 0)
        
        import strategy
        monkeypatch.setattr(strategy, 'datetime', MockDatetime)
        result = strategy.evaluate(config, state, fund)
        assert result.signal != strategy.Signal.INVEST
        assert result.position_before == 10
        assert result.position_after == 10
