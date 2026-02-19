# 需求文档

## 简介

A股股票趋势跟踪策略是一个基于双均线交叉的自动化交易系统，用于A股市场的量化交易。该策略通过监测短期和长期移动平均线的交叉信号来识别趋势变化，并结合止损止盈机制来管理风险。系统支持实时数据获取、持仓状态同步、模拟交易和实盘交易。

## 术语表

- **System**: A股趋势跟踪策略系统
- **Strategy_Engine**: 策略执行引擎，负责运行策略主循环
- **Data_Provider**: 数据提供者，负责获取K线数据
- **Signal_Detector**: 信号检测器，负责检测均线交叉信号
- **Position_Manager**: 持仓管理器，负责管理持仓状态
- **Risk_Controller**: 风险控制器，负责止损止盈检查
- **Trade_Executor**: 交易执行器，负责执行买卖操作
- **Golden_Cross**: 金叉，短期均线上穿长期均线
- **Death_Cross**: 死叉，短期均线下穿长期均线
- **MA**: 移动平均线（Moving Average）
- **Kline**: K线数据，包含开盘价、收盘价、最高价、最低价
- **Position**: 持仓，当前持有的股票数量和成本
- **Stop_Loss**: 止损，当亏损达到设定比例时自动卖出
- **Take_Profit**: 止盈，当盈利达到设定比例时自动卖出
- **Timeframe**: K线周期，如5分钟、15分钟、60分钟等
- **TS_Code**: Tushare股票代码格式，如000001.SZ
- **ATR**: 平均真实波动范围（Average True Range），衡量价格波动性
- **MACD**: 指数平滑异同移动平均线，趋势跟踪指标
- **RSI**: 相对强弱指标（Relative Strength Index），动量振荡指标
- **Bollinger_Bands**: 布林带，由中轨、上轨、下轨组成的波动性指标
- **ADX**: 平均趋向指标（Average Directional Index），衡量趋势强度
- **Slippage**: 滑点，实际成交价格与预期价格的差异
- **Kelly_Criterion**: 凯利公式，用于计算最优仓位比例的数学公式
- **Drawdown**: 回撤，从峰值到谷底的最大跌幅
- **Sharpe_Ratio**: 夏普比率，衡量风险调整后收益的指标
- **Win_Rate**: 胜率，盈利交易次数占总交易次数的比例

## 需求

### 需求 1: 策略配置管理

**用户故事:** 作为交易员，我希望能够灵活配置策略参数，以便适应不同的交易风格和市场环境。

#### 验收标准

1. WHEN 策略初始化时，THE System SHALL 从配置中读取短期均线窗口参数（默认5）
2. WHEN 策略初始化时，THE System SHALL 从配置中读取长期均线窗口参数（默认20）
3. WHEN 策略初始化时，THE System SHALL 从配置中读取交易数量参数（默认100股）
4. WHEN 策略初始化时，THE System SHALL 从配置中读取止损比例参数（默认0%）
5. WHEN 策略初始化时，THE System SHALL 从配置中读取止盈比例参数（默认0%）
6. WHEN 策略初始化时，THE System SHALL 从配置中读取K线周期参数（默认240分钟）
7. WHEN 策略初始化时，THE System SHALL 从配置中读取轮询间隔参数（默认60秒）
8. WHEN 短期窗口大于等于长期窗口时，THE System SHALL 重置为默认值5/20并记录警告日志
9. WHEN 交易数量小于100股时，THE System SHALL 调整为100股并记录警告日志
10. WHEN 轮询间隔小于5秒时，THE System SHALL 调整为5秒并记录警告日志

### 需求 2: 实时数据获取

**用户故事:** 作为策略系统，我需要获取实时的K线数据，以便计算技术指标和生成交易信号。

#### 验收标准

1. WHEN 请求K线数据时，THE Data_Provider SHALL 将TS_Code格式转换为Sina_Symbol格式
2. WHEN 调用新浪财经API时，THE Data_Provider SHALL 指定股票代码、K线周期和数据长度
3. WHEN API返回数据时，THE Data_Provider SHALL 解析JSON响应并提取收盘价列表
4. WHEN API请求失败时，THE Data_Provider SHALL 记录错误日志并返回空列表
5. WHEN API返回空数据时，THE Data_Provider SHALL 记录警告日志并返回空列表
6. WHEN 数据解析失败时，THE Data_Provider SHALL 记录错误日志并返回空列表
7. THE Data_Provider SHALL 支持5分钟、15分钟、30分钟、60分钟、240分钟K线周期
8. WHEN 请求超时时间超过10秒时，THE Data_Provider SHALL 中断请求并返回错误

### 需求 3: 技术指标计算

**用户故事:** 作为策略引擎，我需要计算移动平均线指标，以便识别趋势方向。

#### 验收标准

1. WHEN 计算移动平均线时，THE System SHALL 使用简单移动平均算法（SMA）
2. WHEN 数据长度小于窗口大小时，THE System SHALL 返回None
3. WHEN 数据长度大于等于窗口大小时，THE System SHALL 计算最近N个数据点的平均值
4. THE System SHALL 计算当前周期的短期均线和长期均线
5. THE System SHALL 计算前一周期的短期均线和长期均线用于交叉检测

### 需求 4: 交易信号检测

**用户故事:** 作为信号检测器，我需要识别均线交叉信号，以便生成买入和卖出信号。

#### 验收标准

1. WHEN 前一周期短期均线小于等于长期均线且当前周期短期均线大于长期均线时，THE Signal_Detector SHALL 生成金叉信号
2. WHEN 前一周期短期均线大于等于长期均线且当前周期短期均线小于长期均线时，THE Signal_Detector SHALL 生成死叉信号
3. WHEN 均线未发生交叉时，THE Signal_Detector SHALL 不生成任何信号
4. THE Signal_Detector SHALL 同时返回金叉和死叉的检测结果

### 需求 5: 持仓状态管理

**用户故事:** 作为持仓管理器，我需要跟踪当前的持仓状态，以便正确执行交易逻辑。

#### 验收标准

1. WHEN 策略启动时，THE Position_Manager SHALL 初始化持仓状态为未持仓
2. WHEN 连接到交易接口时，THE Position_Manager SHALL 从交易接口同步实际持仓信息
3. WHEN 检测到持仓数量大于0时，THE Position_Manager SHALL 更新持仓状态为已持仓
4. WHEN 首次检测到持仓时，THE Position_Manager SHALL 记录入场价格和入场时间
5. WHEN 检测到持仓数量为0时，THE Position_Manager SHALL 更新持仓状态为未持仓
6. WHEN 更新为未持仓状态时，THE Position_Manager SHALL 清除入场价格和入场时间
7. WHEN 交易接口获取持仓失败时，THE Position_Manager SHALL 记录警告日志并继续运行

### 需求 6: 风险控制

**用户故事:** 作为风险控制器，我需要监控持仓的盈亏情况，以便在达到止损或止盈条件时及时平仓。

#### 验收标准

1. WHEN 未持仓时，THE Risk_Controller SHALL 不执行止损止盈检查
2. WHEN 持仓且止损比例大于0时，THE Risk_Controller SHALL 计算当前盈亏比例
3. WHEN 亏损比例超过止损设定时，THE Risk_Controller SHALL 触发止损信号
4. WHEN 盈利比例超过止盈设定时，THE Risk_Controller SHALL 触发止盈信号
5. WHEN 触发止损或止盈时，THE Risk_Controller SHALL 返回触发原因和实际盈亏比例
6. WHEN 止损比例为0时，THE Risk_Controller SHALL 不执行止损检查
7. WHEN 止盈比例为0时，THE Risk_Controller SHALL 不执行止盈检查

### 需求 7: 交易执行

**用户故事:** 作为交易执行器，我需要执行买入和卖出操作，并支持模拟交易和实盘交易。

#### 验收标准

1. WHEN 收到买入信号且未持仓时，THE Trade_Executor SHALL 执行买入操作
2. WHEN 执行买入时，THE Trade_Executor SHALL 记录买入价格、数量和时间
3. WHEN 连接到交易接口时，THE Trade_Executor SHALL 调用交易接口的买入方法
4. WHEN 未连接交易接口时，THE Trade_Executor SHALL 执行模拟买入并更新持仓状态
5. WHEN 买入操作失败时，THE Trade_Executor SHALL 记录错误日志
6. WHEN 收到卖出信号且持仓时，THE Trade_Executor SHALL 执行卖出操作
7. WHEN 执行卖出时，THE Trade_Executor SHALL 记录卖出价格、数量、原因和盈亏比例
8. WHEN 连接到交易接口时，THE Trade_Executor SHALL 调用交易接口的卖出方法
9. WHEN 未连接交易接口时，THE Trade_Executor SHALL 执行模拟卖出并更新持仓状态
10. WHEN 卖出操作失败时，THE Trade_Executor SHALL 记录错误日志

### 需求 8: 策略主循环

**用户故事:** 作为策略引擎，我需要持续运行策略逻辑，以便实时监控市场并执行交易。

#### 验收标准

1. WHEN 策略启动时，THE Strategy_Engine SHALL 解析股票代码并转换为新浪格式
2. WHEN 股票代码解析失败时，THE Strategy_Engine SHALL 记录错误并停止运行
3. WHEN 策略启动时，THE Strategy_Engine SHALL 记录策略配置信息
4. WHILE 策略运行中，THE Strategy_Engine SHALL 按轮询间隔执行策略逻辑
5. WHILE 策略运行中，THE Strategy_Engine SHALL 获取K线数据并计算技术指标
6. WHILE 策略运行中，THE Strategy_Engine SHALL 同步持仓状态
7. WHILE 策略运行中，THE Strategy_Engine SHALL 检测交易信号
8. WHEN 未持仓且检测到金叉信号时，THE Strategy_Engine SHALL 执行买入操作
9. WHEN 持仓且检测到死叉信号时，THE Strategy_Engine SHALL 执行卖出操作
10. WHEN 持仓且触发止损止盈时，THE Strategy_Engine SHALL 执行卖出操作
11. WHEN K线数据不足时，THE Strategy_Engine SHALL 记录警告并等待下一轮
12. WHEN 均线计算失败时，THE Strategy_Engine SHALL 记录警告并等待下一轮

### 需求 9: 错误处理和稳定性

**用户故事:** 作为系统管理员，我希望策略能够稳定运行，并在遇到错误时能够恢复或安全停止。

#### 验收标准

1. WHEN 策略执行过程中发生异常时，THE System SHALL 捕获异常并记录错误日志
2. WHEN 发生异常时，THE System SHALL 增加错误计数器
3. WHEN 连续错误次数达到5次时，THE System SHALL 停止策略运行
4. WHEN 成功执行一轮策略后，THE System SHALL 重置错误计数器为0
5. WHEN 发生异常时，THE System SHALL 打印完整的异常堆栈信息
6. WHEN 策略停止时，THE System SHALL 记录停止原因

### 需求 10: 日志记录

**用户故事:** 作为系统管理员，我需要详细的日志记录，以便监控策略运行状态和排查问题。

#### 验收标准

1. WHEN 策略启动时，THE System SHALL 记录策略配置信息
2. WHEN 每轮执行时，THE System SHALL 记录当前价格和均线值
3. WHEN 检测到持仓时，THE System SHALL 记录入场价格
4. WHEN 生成买入信号时，THE System SHALL 记录买入价格和数量
5. WHEN 生成卖出信号时，THE System SHALL 记录卖出价格、数量、原因和盈亏比例
6. WHEN 交易执行成功时，THE System SHALL 记录成功信息
7. WHEN 交易执行失败时，THE System SHALL 记录失败原因
8. WHEN 发生警告或错误时，THE System SHALL 记录相应级别的日志
9. THE System SHALL 支持INFO、WARNING、ERROR三种日志级别
10. WHEN 有日志回调函数时，THE System SHALL 调用回调函数传递日志信息

### 需求 11: A股市场特性支持

**用户故事:** 作为策略系统，我需要支持A股市场的特殊规则，以便正确执行交易。

#### 验收标准

1. THE System SHALL 支持上海证券交易所股票代码格式（sh开头）
2. THE System SHALL 支持深圳证券交易所股票代码格式（sz开头）
3. THE System SHALL 正确转换Tushare代码格式到新浪财经代码格式
4. WHEN 股票代码包含.SH后缀时，THE System SHALL 转换为sh前缀格式
5. WHEN 股票代码包含.SZ后缀时，THE System SHALL 转换为sz前缀格式
6. THE System SHALL 支持最小交易单位100股的限制
7. THE System SHALL 确保交易数量为100的整数倍

### 需求 12: 回测功能支持

**用户故事:** 作为量化研究员，我希望能够使用历史数据回测策略，以便验证策略的有效性。

#### 验收标准

1. THE System SHALL 支持使用历史K线数据进行回测
2. WHEN 回测模式时，THE System SHALL 不连接实际交易接口
3. WHEN 回测模式时，THE System SHALL 使用模拟交易记录买卖操作
4. THE System SHALL 记录回测期间的所有交易信号和执行结果
5. THE System SHALL 计算回测期间的累计收益率
6. THE System SHALL 计算回测期间的最大回撤
7. THE System SHALL 统计回测期间的交易次数和胜率
8. THE System SHALL 支持自定义回测时间范围

### 需求 13: 高级趋势识别

**用户故事:** 作为量化交易员，我希望使用更先进的趋势识别方法，以便提高信号质量和减少虚假信号。

#### 验收标准

1. WHERE 启用MACD指标时，THE System SHALL 计算MACD、信号线和柱状图
2. WHERE 启用MACD指标时，WHEN MACD线上穿信号线时，THE System SHALL 生成买入确认信号
3. WHERE 启用MACD指标时，WHEN MACD线下穿信号线时，THE System SHALL 生成卖出确认信号
4. WHERE 启用RSI指标时，THE System SHALL 计算相对强弱指标
5. WHERE 启用RSI指标时，WHEN RSI低于超卖阈值（默认30）时，THE System SHALL 标记超卖状态
6. WHERE 启用RSI指标时，WHEN RSI高于超买阈值（默认70）时，THE System SHALL 标记超买状态
7. WHERE 启用布林带指标时，THE System SHALL 计算上轨、中轨和下轨
8. WHERE 启用布林带指标时，WHEN 价格突破上轨时，THE System SHALL 生成超买警告
9. WHERE 启用布林带指标时，WHEN 价格跌破下轨时，THE System SHALL 生成超卖警告
10. WHERE 启用ATR指标时，THE System SHALL 计算平均真实波动范围
11. WHERE 启用ATR指标时，THE System SHALL 使用ATR动态调整止损距离

### 需求 14: 多重信号确认

**用户故事:** 作为风险管理者，我希望通过多重信号确认来减少虚假信号，以便提高交易胜率。

#### 验收标准

1. WHERE 启用多重确认时，WHEN 生成买入信号时，THE System SHALL 检查所有启用的指标是否同时满足买入条件
2. WHERE 启用多重确认时，WHEN 生成卖出信号时，THE System SHALL 检查所有启用的指标是否同时满足卖出条件
3. WHERE 启用成交量确认时，WHEN 金叉发生时，THE System SHALL 检查成交量是否放大
4. WHERE 启用成交量确认时，WHEN 成交量未放大时，THE System SHALL 延迟买入信号
5. WHERE 启用趋势强度过滤时，THE System SHALL 计算ADX指标
6. WHERE 启用趋势强度过滤时，WHEN ADX低于阈值（默认25）时，THE System SHALL 过滤掉交易信号
7. THE System SHALL 支持配置信号确认的最小指标数量

### 需求 15: 动态仓位管理

**用户故事:** 作为资金管理者，我希望根据市场状况动态调整仓位，以便优化资金使用效率和控制风险。

#### 验收标准

1. WHERE 启用动态仓位时，THE System SHALL 根据账户总资金计算可用仓位
2. WHERE 启用动态仓位时，THE System SHALL 根据波动率调整单次交易金额
3. WHERE 启用动态仓位时，WHEN 市场波动率高时，THE System SHALL 降低仓位比例
4. WHERE 启用动态仓位时，WHEN 市场波动率低时，THE System SHALL 提高仓位比例
5. WHERE 启用凯利公式时，THE System SHALL 根据历史胜率和盈亏比计算最优仓位
6. WHERE 启用固定风险比例时，THE System SHALL 根据止损距离计算交易数量
7. THE System SHALL 确保单次交易金额不超过账户总资金的配置比例（默认10%）
8. THE System SHALL 确保总持仓金额不超过账户总资金的配置比例（默认80%）

### 需求 16: 自适应参数优化

**用户故事:** 作为策略研究员，我希望策略能够根据市场环境自动调整参数，以便适应不同的市场状态。

#### 验收标准

1. WHERE 启用自适应参数时，THE System SHALL 定期评估策略表现
2. WHERE 启用自适应参数时，WHEN 策略表现不佳时，THE System SHALL 调整均线周期参数
3. WHERE 启用自适应参数时，THE System SHALL 在预定义的参数范围内搜索最优参数
4. WHERE 启用自适应参数时，THE System SHALL 使用滑动窗口评估参数效果
5. WHERE 启用市场状态识别时，THE System SHALL 识别趋势市、震荡市和盘整市
6. WHERE 启用市场状态识别时，WHEN 识别为震荡市时，THE System SHALL 暂停交易或切换到震荡策略
7. WHERE 启用市场状态识别时，WHEN 识别为趋势市时，THE System SHALL 使用趋势跟踪参数
8. THE System SHALL 记录参数调整历史和效果评估结果

### 需求 17: 多品种组合管理

**用户故事:** 作为投资组合管理者，我希望同时运行多个股票的趋势策略，以便分散风险和提高收益稳定性。

#### 验收标准

1. THE System SHALL 支持同时监控多个股票代码
2. WHEN 运行多品种策略时，THE System SHALL 为每个股票维护独立的持仓状态
3. WHEN 运行多品种策略时，THE System SHALL 为每个股票独立计算技术指标
4. WHEN 运行多品种策略时，THE System SHALL 为每个股票独立生成交易信号
5. THE System SHALL 根据相关性分析避免同时持有高度相关的股票
6. THE System SHALL 根据配置的资金分配比例在多个股票间分配资金
7. THE System SHALL 监控组合整体的风险敞口
8. WHEN 组合整体亏损超过阈值时，THE System SHALL 触发组合级别的止损

### 需求 18: 滑点和交易成本模拟

**用户故事:** 作为回测分析师，我希望在回测中考虑滑点和交易成本，以便获得更真实的策略表现评估。

#### 验收标准

1. WHERE 回测模式时，THE System SHALL 在成交价格上添加滑点
2. WHERE 回测模式时，THE System SHALL 根据配置的滑点比例（默认0.1%）调整成交价格
3. WHERE 回测模式时，WHEN 买入时，THE System SHALL 在价格上增加滑点
4. WHERE 回测模式时，WHEN 卖出时，THE System SHALL 在价格上减少滑点
5. WHERE 回测模式时，THE System SHALL 计算佣金费用（默认万分之三）
6. WHERE 回测模式时，THE System SHALL 计算印花税（卖出时千分之一）
7. WHERE 回测模式时，THE System SHALL 从收益中扣除所有交易成本
8. THE System SHALL 在回测报告中显示总交易成本和净收益
