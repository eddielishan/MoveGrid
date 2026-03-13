"""通知模块 - 支持企业微信机器人和日志输出"""

import json
import logging

import requests

from strategy import TradeSignal, Signal

logger = logging.getLogger(__name__)


def format_message(signal: TradeSignal) -> str:
    """格式化交易信号为通知消息"""
    lines = [
        f"📢 基金网格交易提醒",
        f"",
        f"基金代码：{signal.fund_data.fund_code}",
        f"基金名称：{signal.fund_data.name}",
        f"当前净值：{signal.fund_data.gsz:.4f}",
        f"涨跌幅：{signal.fund_data.gszzl:.2f}%",
        f"",
        f"触发策略：{signal.signal.value}",
        f"仓位变化：{signal.position_before} → {signal.position_after}",
        f"当前网格中心：{signal.state.grid_center:.4f}" if hasattr(signal, "state") and signal.state else "",
        f"触发原因：{signal.reason}",
        f"",
        f"时间：{signal.fund_data.gztime}",
    ]
    return "\n".join(lines)


def notify(signal: TradeSignal, wechat_webhook: str = "", pushplus_token: str = "") -> None:
    """
    发送交易提醒通知。

    仅在触发买入或卖出信号时发送通知，持有信号不通知。
    """
    if signal.signal == Signal.HOLD:
        logger.info("策略结果: 持有 - %s", signal.reason)
        return

    message = format_message(signal)

    # 始终输出到日志
    logger.info("交易提醒:\n%s", message)

    # 企业微信机器人通知
    if wechat_webhook:
        _send_wechat(wechat_webhook, message)

    # PushPlus 推送
    if pushplus_token:
        _send_pushplus(pushplus_token, signal)

    if not wechat_webhook and not pushplus_token:
        logger.info("未配置任何通知渠道，仅日志输出")


def _send_wechat(webhook_url: str, message: str) -> None:
    """发送企业微信机器人消息"""
    payload = {
        "msgtype": "text",
        "text": {"content": message},
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("errcode") == 0:
            logger.info("企业微信通知发送成功")
        else:
            logger.warning("企业微信通知返回异常: %s", result)
    except requests.RequestException as e:
        logger.error("企业微信通知发送失败: %s", e)


def _send_pushplus(token: str, signal: TradeSignal) -> None:
    """通过 PushPlus 发送推送通知"""
    title = f"基金网格提醒 | {signal.signal.value} | {signal.fund_data.name}"
    # 颜色区分
    color = 'green' if signal.signal == Signal.BUY else 'red'
    if signal.signal == Signal.INVEST:
        color = 'blue'

    content = (
        f"<h3>📢 基金网格交易提醒</h3>"
        f"<table border='1' cellpadding='6' cellspacing='0'>"
        f"<tr><td><b>基金代码</b></td><td>{signal.fund_data.fund_code}</td></tr>"
        f"<tr><td><b>基金名称</b></td><td>{signal.fund_data.name}</td></tr>"
        f"<tr><td><b>当前净值</b></td><td>{signal.fund_data.gsz:.4f}</td></tr>"
        f"<tr><td><b>涨跌幅</b></td><td>{signal.fund_data.gszzl:.2f}%</td></tr>"
        f"<tr><td><b>触发策略</b></td><td><b style='color:{color}'>{signal.signal.value}</b></td></tr>"
        f"<tr><td><b>仓位变化</b></td><td>{signal.position_before} → {signal.position_after}</td></tr>"
        f"<tr><td><b>网格中心</b></td><td>{signal.state.grid_center:.4f}</td></tr>" if hasattr(signal, "state") and signal.state else ""
        f"<tr><td><b>触发原因</b></td><td>{signal.reason}</td></tr>"
        f"</table>"
    )
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
    }
    try:
        resp = requests.post("https://www.pushplus.plus/send", json=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 200:
            logger.info("PushPlus 推送成功")
        else:
            logger.warning("PushPlus 推送返回异常: %s", result)
    except requests.RequestException as e:
        logger.error("PushPlus 推送失败: %s", e)
