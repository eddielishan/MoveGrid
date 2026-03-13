"""基金/ETF 行情数据抓取模块（东方财富 push2 接口）"""

import json
import logging
import time

import requests

from models import FundData

logger = logging.getLogger(__name__)

# 东方财富行情接口
FUND_API_URL = "http://push2.eastmoney.com/api/qt/stock/get"
MAX_RETRIES = 3
RETRY_INTERVAL = 2  # 秒

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

# 请求的字段
# f43=最新价 f57=代码 f58=名称 f59=小数位数 f169=涨跌额 f170=涨跌幅
FIELDS = "f43,f57,f58,f59,f169,f170"


def fetch_fund_data(fund_code: str) -> FundData:
    """
    从东方财富 push2 接口获取基金/ETF 行情数据。

    fund_code 格式为 secid，例如 "1.515300"（沪市）或 "0.159915"（深市）。
    前缀: 1=沪市, 0=深市

    失败时重试最多3次。
    """
    params = {
        "secid": fund_code,
        "fields": FIELDS,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("正在获取 %s 行情数据（第%d次）...", fund_code, attempt)
            resp = requests.get(FUND_API_URL, params=params, headers=HEADERS, timeout=10)
            resp.raise_for_status()

            result = resp.json()
            if result.get("rc") != 0 or not result.get("data"):
                raise ValueError(f"接口返回异常: rc={result.get('rc')}, data={result.get('data')}")

            data = result["data"]
            decimal_places = data.get("f59", 2)
            divisor = 10 ** decimal_places

            price = data["f43"] / divisor
            change_pct = data["f170"] / 100  # 涨跌幅，百分比

            # 提取纯代码（去掉 secid 的市场前缀）
            code = data["f57"]

            fund = FundData(
                fund_code=code,
                name=data["f58"],
                gsz=price,
                gszzl=change_pct,
                gztime="",  # 此接口不返回时间，留空
            )
            logger.info(
                "获取成功: %s(%s) 最新价=%.4f 涨跌幅=%.2f%%",
                fund.name, fund.fund_code, fund.gsz, fund.gszzl,
            )
            return fund

        except requests.RequestException as e:
            logger.warning("网络请求失败（第%d次）: %s", attempt, e)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error("数据解析错误: %s", e)
            raise  # 解析错误直接抛出，不重试

        if attempt < MAX_RETRIES:
            logger.info("等待%d秒后重试...", RETRY_INTERVAL)
            time.sleep(RETRY_INTERVAL)

    raise ConnectionError(f"获取 {fund_code} 行情数据失败，已重试{MAX_RETRIES}次")
