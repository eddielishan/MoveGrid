"""基金自动网格买卖提醒系统 - 主程序入口"""

import argparse
import json
import logging
import os
import sys

import schedule
import time as time_module
import yaml

from models import FundConfig, StrategyState
from data_fetcher import fetch_fund_data
from strategy import evaluate
from notifier import notify

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")
STATE_FILE = os.path.join(BASE_DIR, "state.json")

# 日志配置
LOG_DIR = os.path.join(BASE_DIR, "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "grid_trading.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """加载配置文件 (YAML格式)"""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state(fund_code: str, initial_price: float, initial_position: int) -> StrategyState:
    """加载策略状态，如果不存在则创建初始状态"""
    states = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                states = json.load(f)
        except json.JSONDecodeError as e:
            logger.error("解析 state.json 失败: %s，将使用空状态", e)
            states = {}

    if fund_code in states:
        return StrategyState.from_dict(states[fund_code])

    # 创建初始状态：以当前净值作为初始买入/卖出价、网格中心
    logger.info("基金 %s 无历史状态，创建初始状态（仓位=%d，基准价/中心=%.4f）",
                fund_code, initial_position, initial_price)
    return StrategyState(
        fund_code=fund_code,
        grid_center=initial_price,
        last_buy_price=initial_price,
        last_sell_price=initial_price,
        position=initial_position,
    )


def save_state(state: StrategyState) -> None:
    """保存策略状态到文件（使用原子写入，防止进程崩溃导致文件损坏）"""
    states = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                states = json.load(f)
        except json.JSONDecodeError:
            pass  # 如果文件损坏，直接覆盖

    states[state.fund_code] = state.to_dict()

    # 先写入临时文件，再原子替换，防止写一半中断导致文件完全损坏
    tmp_file = STATE_FILE + ".tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(states, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, STATE_FILE)
    except OSError as e:
        # 在 Docker 环境下，如果 state.json 是以单文件形式挂载的，os.replace 会报 [Errno 16] Device or resource busy
        # 此时降级为直接覆盖写入
        if e.errno == 16:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(states, f, ensure_ascii=False, indent=2)
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        else:
            raise e
    
    logger.info("状态已保存: %s", state.to_dict())


def run_strategy() -> None:
    """执行一次完整的策略流程"""
    logger.info("=" * 60)
    logger.info("开始执行网格交易策略检查")
    logger.info("=" * 60)

    config_data = load_config()
    notify_cfg = config_data.get("notify", {})
    wechat_webhook = notify_cfg.get("wechat_webhook", "")
    pushplus_token = notify_cfg.get("pushplus_token", "")

    for fund_cfg in config_data["funds"]:
        fc = FundConfig(**fund_cfg)
        logger.info("处理基金: %s", fc.fund_code)

        try:
            # 1. 获取基金数据
            fund_data = fetch_fund_data(fc.fund_code)

            # 2. 加载状态（优先使用配置的初始价格，否则用实时净值）
            init_price = fc.initial_price if fc.initial_price > 0 else fund_data.gsz
            state = load_state(fc.fund_code, init_price, fc.initial_position)

            # 3. 策略评估
            signal = evaluate(fc, state, fund_data)

            # 4. 发送通知
            from strategy import Signal
            show_hold = notify_cfg.get("show_hold", True)
            
            # 仅在不是 HOLD 信号，或者开启了 show_hold 时发送通知
            if signal.signal != Signal.HOLD or show_hold:
                notify(signal, wechat_webhook, pushplus_token)

            # 5. 保存状态
            save_state(state)

        except Exception as e:
            logger.error("基金 %s 策略执行失败: %s", fc.fund_code, e, exc_info=True)

    logger.info("策略检查完成")


def main():
    parser = argparse.ArgumentParser(description="基金自动网格买卖提醒系统")
    parser.add_argument("--now", action="store_true", help="立即执行一次策略")
    args = parser.parse_args()

    logger.info("基金自动网格买卖提醒系统启动")

    if args.now:
        logger.info("模式: 立即执行")
        run_strategy()
        return

    # 定时任务模式
    config_data = load_config()
    schedule_times = config_data.get("schedule_times", ["15:30", "20:00"])

    for t in schedule_times:
        schedule.every().day.at(t).do(run_strategy)
        logger.info("已设置定时任务: 每天 %s", t)

    logger.info("系统进入定时运行模式，等待执行...")
    while True:
        schedule.run_pending()
        time_module.sleep(60)


if __name__ == "__main__":
    main()
