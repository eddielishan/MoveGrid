# 基金自动网格买卖提醒系统 - 实现方案

## 项目背景

构建一个基于 Python 的自动化基金网格交易提醒系统。系统通过定时抓取天天基金网的基金净值数据，根据预设的网格交易策略判断买卖信号，并通过消息通知用户。**仅提醒，不自动下单。**

## 项目结构

```
jijin/
├── config.yaml              # 策略配置文件（基金代码、网格参数等，支持#注释）
├── state.json               # 策略运行状态持久化
├── main.py                  # 主入口，调度定时任务
├── strategy.py              # 网格策略判断核心逻辑
├── data_fetcher.py          # 基金净值数据抓取
├── notifier.py              # 通知模块（企业微信/日志）
├── models.py                # 数据模型定义
├── tests/
│   └── test_strategy.py     # 策略逻辑单元测试
├── requirements.txt         # 依赖
└── doc/
    └── 基金网格买卖提醒系统/
        └── implementation_plan.md
```

---

## 模块设计

### 1. 数据模型 (`models.py`)

定义两个核心数据类：

- **`FundConfig`** — 策略配置
  - `fund_code`: 基金代码
  - `grid_spacing`: 网格间距（如 0.04 = 4%）
  - `max_position`: 最大仓位
  - `min_position`: 最小仓位
  - `initial_position`: 初始仓位
  - `initial_price`: 初始基准价，0表示使用实时净值
  - `move_trigger`: 移动网格阈值（默认等于 `2 * grid_spacing`）
  - `invest_enabled`: 是否开启定投（默认 false）
  - `invest_amount`: 每次定投的固定金额或份额份额
  - `invest_interval_days`: 定投间隔天数（如每两周为 14 天）
  - `invest_weekday`: 定投触发的星期几（1-7，比如周四为 4）

- **`StrategyState`** — 策略运行状态
  - `fund_code`: 基金代码
  - `grid_center`: 当前网格中心价格
  - `last_sell_price`: 最近卖出价
  - `position`: 当前仓位
  - `update_time`: 更新时间
  - `last_trade_date`: 最后网格交易/移网日期
  - `last_invest_date`: 最近一次成功定投的日期（YYYY-MM-DD）

- **`FundData`** — 基金净值数据
  - `fund_code`, `name`, `gsz`(估值), `gszzl`(涨跌幅), `gztime`

---

### 2. 数据抓取 (`data_fetcher.py`)

- 从天天基金接口获取基金估值数据
- 接口地址: `https://fundgz.1234567.com.cn/js/{fundCode}.js`
- 返回 JSONP 格式，需解析提取 JSON
- 重试机制：失败重试3次，间隔2秒

---

### 3. 网格策略 (`strategy.py`)

核心判断逻辑：

```
1. 移动网格逻辑 (优先判断)
   如果 当前净值 >= grid_center × (1 + move_trigger) THEN
       触发网格上移：grid_center = grid_center × (1 + grid_spacing)
       更新买/卖基准价 = 新的 grid_center
   如果 当前净值 <= grid_center × (1 - move_trigger) THEN
       触发网格下移：grid_center = grid_center × (1 - grid_spacing)
       更新买/卖基准价 = 新的 grid_center

2. 买卖信号逻辑 (网格交易)
   买入条件: 当前净值 <= last_buy_price × (1 - grid_spacing) AND 仓位 < max_position
   卖出条件: 当前净值 >= last_sell_price × (1 + grid_spacing) AND 仓位 > min_position

3. 定投提醒逻辑 (独立于网格)
   如果 invest_enabled = true THEN
       判断今天是否是 invest_weekday (比如周四 = 4)
       判断距离 last_invest_date 是否大于等于 invest_interval_days (比如 14天)
       如果上述条件均满足：
           发送独立定投信号（Signal.INVEST）
           更新 last_invest_date = 今天
```

触发买入后：

- `position += trade_unit`
- `last_buy_price = 当前净值`

触发卖出后：

- `position -= trade_unit`
- `last_sell_price = 当前净值`

---

### 4. 通知模块 (`notifier.py`)

- 支持多种通知方式，通过配置选择
- 初始实现：**日志输出** + **企业微信机器人** Webhook
- 通知内容包含：基金代码、当前净值、触发策略、当前仓位、时间
- 企业微信 Webhook 等配置存在 `config.yaml` 中，为空则仅日志输出

---

### 5. 主入口 (`main.py`)

- 使用 `schedule` 库实现定时任务
- 默认在 15:30 和 20:00 运行
- 也支持手动立即执行（`--now` 参数）
- 流程：加载配置 → 抓取数据 → 策略判断 → 通知 → 保存状态

---

### 6. 配置文件 (`config.yaml`)

```yaml
funds:
  - fund_code: "1.515300"
    grid_spacing: 0.03 # 网格间距，0.03代表3%
    max_position: 20 # 最大持仓份额或金额
    min_position: 0 # 最小持仓份额
    initial_position: 10 # 初始持有份额
    trade_unit: 1 # 单次买卖交易单位
    initial_price: 0 # 初始基准价，0表示使用实时净值
    move_trigger: 0.08 # 偏离中心移动网格阈值
    invest_enabled: true # 定投防频次触发开关
    invest_amount: 1000 # 每次周定投单位
    invest_interval_days: 14 # 定投间隔周期天数
    invest_weekday: 4 # 定投周期，周四
notify:
  wechat_webhook: ""
  pushplus_token: "xxx"
schedule_times:
  - "15:30"
  - "20:00"
```

---

## 实现文件清单

| 文件                           | 操作 | 说明                  |
| ------------------------------ | ---- | --------------------- |
| [NEW] `models.py`              | 新建 | 数据模型（dataclass） |
| [NEW] `data_fetcher.py`        | 新建 | 基金数据抓取          |
| [NEW] `strategy.py`            | 新建 | 网格策略判断          |
| [NEW] `notifier.py`            | 新建 | 通知模块              |
| [NEW] `main.py`                | 新建 | 主程序入口            |
| [NEW] `config.yaml`            | 新建 | 默认配置              |
| [NEW] `requirements.txt`       | 新建 | 依赖列表              |
| [NEW] `tests/test_strategy.py` | 新建 | 策略逻辑单测          |

---

## 验证计划

### 自动化测试

运行策略逻辑单元测试：

```bash
cd /Users/eddie/work/python/jijin && python -m pytest tests/test_strategy.py -v
```

测试场景覆盖：

1. 正常触发买入信号
2. 正常触发卖出信号
3. 未触发任何信号（净值变动不够）
4. 仓位达到上限禁止买入
5. 仓位达到下限禁止卖出
6. 连续多次网格触发

### 手动验证

1. 运行 `python main.py --now` 立即执行一次策略
2. 检查控制台日志输出是否正确显示基金数据和策略判断结果
3. 检查 `state.json` 文件是否正确生成/更新
