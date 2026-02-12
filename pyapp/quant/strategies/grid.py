# -*- coding: utf-8 -*-
import time
import threading
import json
import requests
import math
import datetime
from ..base import BaseStrategy

class GridStrategy(BaseStrategy):
    def __init__(self, data, log_callback=None):
        super().__init__(data, log_callback)
        self.log_layer_base = 0.01 # Default
        self._init_config()

    def _init_config(self):
        config = self.data.get('task', {}).get('config', {})
        if isinstance(config, str):
            try: config = json.loads(config)
            except: pass
        
        layer_percent = float(config.get('layerPercent', 1.0)) / 100.0
        if layer_percent > 0:
            self.log_layer_base = math.log(1 + layer_percent)
        else:
            self.log_layer_base = 0.01

        # 任务有效期
        self.expiration_time = None
        validity_period = config.get('validityPeriod')
        if validity_period:
            try:
                if isinstance(validity_period, str):
                    dt = datetime.datetime.strptime(validity_period[:10], "%Y-%m-%d")
                    self.expiration_time = dt.replace(hour=15, minute=0, second=0, microsecond=0)
            except Exception as e:
                self.log(f"任务({self.data.get('id', 0)})：无效的有效期格式 {validity_period}: {e}", "ERROR")
        
        self.ignore_trading_time = bool(config.get('ignoreTradingTime', False))
        self.enable_real_trade = bool(config.get('enableRealTrade', True))

    def run(self):
        id = self.data.get('id', 0)
        name = self.data.get('name', 'Unknown')
        self.log(f"任务({id})：初始化已完成。")
        mode_str = "实盘交易" if self.enable_real_trade else "模拟演示 (仅日志)"
        self.log(f"任务({id})：当前运行模式: {mode_str}")
        
        # 1. 解析配置
        config = self.data.get('task', {}).get('config', {})
        if isinstance(config, str):
            try: config = json.loads(config)
            except: pass
        
        stock_info = self.data.get('task', {}).get('stock', {})
        if isinstance(stock_info, str):
            try: stock_info = json.loads(stock_info)
            except: pass
                
        ts_code = stock_info.get('ts_code', '')
        if not ts_code:
            self.log(f"任务({id})：未找到股票代码", "ERROR")
            return

        stock_code = ''.join(filter(str.isdigit, ts_code))
        
        # 2. 数据源初始化
        if not getattr(self.trader, 'tushare', None) and not getattr(self.trader, 'akshare', None):
            self.trader.init_data_source('easyquotation', 'sina')

        # 3. 策略参数提取
        # 基础策略参数
        trade_layers = int(config.get('tradeLayers', 0))
        layer_percent = float(config.get('layerPercent', 1.0)) / 100.0
        base_quantity = int(config.get('baseQuantity', 100))
        monitor_interval = int(config.get('monitorInterval', 10))
        trade_direction = int(config.get('tradeDirection', 0)) # 0:双向 1:只买 2:只卖
        
        max_resets = int(config.get('maxResets', 0))
        reset_ratio = float(config.get('resetRatio', 0))
        reset_count = 0
        last_layer_index = 0
        
        # 运行时状态记录
        last_trade_time = 0      # 上次交易时间戳
        last_trade_price = 0     # 上次交易价格
        layer_repeat_counts = {}  # 各层级已交易次数 {index: count}
        
        # 回落标志/峰值记录
        waiting_for_fallback = False
        peak_price = 0.0
        fallback_monitor_start_layer_index = 0

        # 反弹标志/谷值记录
        waiting_for_rebound = False
        valley_price = 0.0
        rebound_monitor_start_layer_index = 0

        # 基准价参数
        base_price_type = int(config.get('basePriceType', 0)) # 0:无/默认 1:指定 2:当前 3:开盘 4:昨收
        manual_base_price = float(config.get('basePrice', 0))
        base_price_float_ratio = float(config.get('basePriceFloatRatio', 0))
        reset_base_price_daily = bool(config.get('resetBasePriceDaily', False))
        
        # 交易量参数
        trade_quantity_type = int(config.get('tradeQuantityType', 1)) # 1:固定 2:倍数
        auto_align = bool(config.get('autoAlign', False))
        auto_open_position = bool(config.get('autoOpenPosition', False))
        open_position_type = int(config.get('openPositionType', 0))
        open_position_quantity = int(config.get('openPositionQuantity', 100))
        open_position_amount = float(config.get('openPositionAmount', 10000))
        open_position_ratio = float(config.get('openPositionRatio', 10))
        
        fallback_ratio = float(config.get('fallbackRatio', 0)) / 100.0
        rebound_ratio = float(config.get('reboundRatio', 0)) / 100.0
        
        # 交易保护参数
        max_repeat_times = int(config.get('maxRepeatTimes', 0))
        min_price_gap = float(config.get('minPriceGap', 0.1)) / 100.0
        min_trade_interval = int(config.get('minTradeInterval', 5))
        
        # 交易模式：全区间 vs 分治
        # deploymentMode: FULL_RANGE(默认) - 全区间策略，任意位置均可买卖
        #                 PARTITIONED - 分治模式，基准线之上只卖不买，基准线之下只买不卖
        deployment_mode = config.get('deploymentMode', 'FULL_RANGE')
        include_base_layer = bool(config.get('includeBaseLayer', True))
        # self.log(f"任务({id})策略模式: {deployment_mode}")
        
        # 更新 Grid Type (确保与 run 中获取的 config 一致)
        self.zeroLayerMode = int(config.get('zeroLayerMode', 1))

        # 价格区间
        upper_price = float(config.get('upperPrice', 0))
        lower_price = float(config.get('lowerPrice', 0))
        
        # 持仓限制
        max_hold_type = int(config.get('maxHoldType', -2)) # -2:未定义(旧逻辑) -1:不限 0:任意 1:量 2:额 3:比例
        max_hold_quantity = int(config.get('maxHoldQuantity', 10000))
        max_hold_amount = float(config.get('maxHoldAmount', 0))
        max_hold_ratio = float(config.get('maxHoldRatio', 0))
        
        # 止盈
        tp_type = int(config.get('takeProfitType', -1)) # -1:不限 0:任意 1:比例 2:价格
        tp_ratio = float(config.get('takeProfitRatio', 0))
        tp_price = float(config.get('takeProfitPrice', 0))
        
        # 止损
        sl_type = int(config.get('stopLossType', -1)) # -1:不限 0:任意 1:比例 2:价格
        sl_ratio = float(config.get('stopLossRatio', 0))
        sl_price = float(config.get('stopLossPrice', 0))

        def resolve_base_price(quote_data, fallback_price):
            current = quote_data.get('price', fallback_price)
            open_price = quote_data.get('open', 0)
            pre_close = quote_data.get('pre_close', 0)
            base_price = 0.0
            if base_price_type == 1:
                base_price = manual_base_price
            elif base_price_type == 2:
                base_price = current
            elif base_price_type == 3:
                base_price = open_price if open_price > 0 else current
            elif base_price_type == 4:
                base_price = pre_close if pre_close > 0 else current
            else:
                base_price = manual_base_price if manual_base_price > 0 else current

            if base_price <= 0:
                base_price = current

            if base_price_float_ratio != 0:
                base_price = base_price * (1 + base_price_float_ratio / 100.0)

            return base_price

        # 4. 初始化基准价格
        
        # 等待交易时间
        is_waiting_start = False
        while self.running and not self._is_trading_time():
            if self.expiration_time and datetime.datetime.now() > self.expiration_time:
                self.log(f"任务({id})有效期已至 ({self.expiration_time})，自动停止任务...", "WARNING")
                from ..manager import TaskManager
                TaskManager().stop_task(id)
                return

            if not is_waiting_start:
                self.log(f"任务({id})：非交易日期或时段（周一到周五：9:25-11:30，13:00-15:00），等待开盘...", "WARNING")
                is_waiting_start = True

            time.sleep(10)

        if is_waiting_start and self.running:
            self.log(f"任务({id})：交易时间到达，开始初始化...")
            
        if not self.running:
            return

        # 获取股票详细信息
        quote = self.trader.get_stock_quote(ts_code)
        current_price = quote.get('price', 0)
        
        if current_price <= 0:
            # 尝试再次获取
            time.sleep(1)
            quote = self.trader.get_stock_quote(ts_code)
            current_price = quote.get('price', 0)
            if current_price <= 0:
                self.log(f"任务({id})：无法获取实时行情数据。", "ERROR")
                return

        base_price = resolve_base_price(quote, current_price)
            
        base_price_type_map = {
            0: "无",
            1: "指定价 (静态)",
            2: "当前价 (动态)",
            3: "开盘价 (动态)",
            4: "前收盘价 (动态)"
        }
        type_str = base_price_type_map.get(base_price_type, str(base_price_type))
        self.log(f"任务({id})基准价格确定为：{base_price:.3f}，类型: {type_str}")

        # 5. 计算交易层级/范围
        if upper_price <= 0: 
            if trade_layers > 0 and layer_percent > 0:
                upper_price = base_price * math.pow(1 + layer_percent, trade_layers)
            else:
                upper_price = base_price * 1.2

        if lower_price <= 0: 
            if trade_layers > 0 and layer_percent > 0:
                lower_price = base_price * math.pow(1 + layer_percent, -trade_layers)
            else:
                lower_price = base_price * 0.8
        
        self.log(f"任务({id})配置：标的={ts_code}, 价格范围=[{lower_price:.3f}, {upper_price:.3f}], 层级={trade_layers}, 间隔={layer_percent*100:.2f}%, 基数={base_quantity}(股)")
        
        # 优化：预计算对数常数
        if layer_percent > 0:
            self.log_layer_base = math.log(1 + layer_percent)
        else:
            self.log_layer_base = 0.01 
            
        # 初始层级状态
        last_layer_index = self._get_layer_index(current_price, base_price)
        if trade_layers > 0:
            last_layer_index = max(-trade_layers, min(trade_layers, last_layer_index))
        self.log(f"任务({id})初始价格：{current_price}, 索引：{last_layer_index}")
        
        # 启动时自动对齐层级（一次性买卖）
        if auto_align and last_layer_index != 0:
            self.log(f"任务({id})启动时层级偏离({last_layer_index})，执行自动对齐...")
            
            # 计算需要对齐的数量
            align_vol = base_quantity
            if trade_quantity_type == 2:
                align_vol = base_quantity * abs(last_layer_index)

            if last_layer_index > 0:
                # 价格在基准之上 -> 价格上涨，应减少持仓 -> 补卖
                if trade_direction not in [0, 2]:
                    self.log(f"任务({id})启动需卖出但方向限制，跳过")
                else:
                    pos = self.trader.get_position(stock_code)
                    available = pos.get('available_quantity', 0)
                    self.log(f"任务({id})启动补卖: {available} {align_vol} (索引 {last_layer_index})")

                    if available >= align_vol:
                        res = self._safe_sell(stock_code, current_price, align_vol, reason=f"任务: {name}({id})\n原因: 启动自动补卖")
                        if res:
                            self._save_trade_record("sell", current_price, align_vol, f"Auto Align {last_layer_index}")
                            self._update_task_position(stock_code)
                    else:
                        self.log(f"任务({id})启动补卖失败：持仓不足(需{align_vol}, 有{available})，可能是T+1限制导致无法卖出。", "WARNING")

            elif last_layer_index < 0:
                # 价格在基准之下 -> 价格下跌，应增加持仓 -> 补买
                if trade_direction not in [0, 1]:
                    self.log(f"任务({id})启动需买入但方向限制，跳过")
                else:
                    self.log(f"任务({id})启动补买: {align_vol} (索引 {last_layer_index})")
                    
                    # 检查资金
                    balance = self.trader.get_balance()
                    available_balance = balance.get('available_balance', 0)
                    need_cash = align_vol * current_price
                    
                    if not self.enable_real_trade or available_balance >= need_cash:
                        res = self._safe_buy(stock_code, current_price, align_vol, reason=f"任务: {name}({id})\n原因: 启动自动补买")
                        if res:
                            self._save_trade_record("buy", current_price, align_vol, f"Auto Align {last_layer_index}")
                            self._update_task_position(stock_code)
                    else:
                        self.log(f"任务({id})启动补买失败：资金不足(需{need_cash}, 有{available_balance})", "WARNING")
        
        # 5.1 自动建仓逻辑
        if auto_open_position:
            pos = self.trader.get_position(stock_code)
            current_hold = pos.get('total_quantity', 0)
            if current_hold == 0:
                open_vol = 0
                calc_desc = ""
                
                if open_position_type == 0:
                    open_vol = base_quantity
                    calc_desc = f"按单格基数 {base_quantity}"
                elif open_position_type == 1:
                    open_vol = open_position_quantity
                    calc_desc = f"按指定股数 {open_position_quantity}"
                elif open_position_type == 2:
                    if current_price > 0:
                        open_vol = int(open_position_amount / current_price / 100) * 100
                        calc_desc = f"按金额 {open_position_amount} (折合 {open_vol} 股)"
                elif open_position_type == 3:
                    balance = self.trader.get_balance()
                    total_asset = balance.get('total_asset', 0)
                    if current_price > 0 and total_asset > 0:
                        target_amount = total_asset * (open_position_ratio / 100.0)
                        open_vol = int(target_amount / current_price / 100) * 100
                        calc_desc = f"按总资产 {total_asset} 的 {open_position_ratio}% (折合 {open_vol} 股)"

                if open_vol < 100:
                    self.log(f"任务({id})自动建仓计算数量为 {open_vol} (小于100)，取消建仓 ({calc_desc})", "WARNING")
                else:
                    self.log(f"任务({id})检测到持仓为0且开启自动建仓，正在买入底仓... {calc_desc}")
                    
                    # 检查资金
                    balance = self.trader.get_balance()
                    available_balance = balance.get('available_balance', 0)
                    need_cash = open_vol * current_price
                    
                    if not self.enable_real_trade or available_balance >= need_cash:
                        reason = f"任务: {name}({id})\n原因: 自动建仓"
                        res = self._safe_buy(stock_code, current_price, open_vol, reason=reason)
                        if res:
                            self.log(f"任务({id})自动建仓委托已发送：{res}")
                            self._save_trade_record("buy", current_price, open_vol, "Auto Open")
                            self._update_task_position(stock_code)
                            # 重新获取持仓以确保状态同步
                            time.sleep(1)
                        else:
                            self.log(f"任务({id})自动建仓失败！", "ERROR")
                    else:
                        self.log(f"任务({id})自动建仓失败：资金不足(需{need_cash}, 有{available_balance})", "WARNING")

        # 优化：重用会话
        self.session = requests.Session()

        # 初始更新持仓
        self._update_task_position(stock_code)

        is_paused = False
        last_trading_date = None
        self.log(f"任务({id})：初始化完成，运行主策略...")

        while self.running:
            try:
                # 0. 有效期检查
                if self.expiration_time and datetime.datetime.now() > self.expiration_time:
                    self.log(f"任务({id})有效期已至 ({self.expiration_time})，自动停止任务...", "WARNING")
                    from ..manager import TaskManager
                    TaskManager().stop_task(id)
                    # 退出当前循环，结束 _run_loop
                    break

                # 检查交易时间
                trading_status = self._is_trading_time()
                
                # 非交易时间
                if not trading_status:
                    if not is_paused:
                        self.log(f"任务({id})非交易日期或时段（周一到周五：9:25-11:30，13:00-15:00），等待开盘...", "WARNING")
                        is_paused = True
                    time.sleep(10)
                    continue
                
                # 交易时间
                if is_paused:
                    self.log(f"任务({id})交易时间到达，恢复运行...", "INFO")
                    is_paused = False

                # 获取价格
                quote = self.trader.get_stock_quote(ts_code)
                current_price = quote.get('price', 0)
                if current_price <= 0:
                    time.sleep(monitor_interval)
                    continue

                # 跨交易日重置逻辑
                if reset_base_price_daily:
                    current_date = datetime.datetime.now().date()
                    if last_trading_date is None:
                        last_trading_date = current_date
                    elif current_date != last_trading_date:
                        base_price = resolve_base_price(quote, current_price)
                        last_layer_index = self._get_layer_index(current_price, base_price)
                        if trade_layers > 0:
                            last_layer_index = max(-trade_layers, min(trade_layers, last_layer_index))

                        conf_upper = float(config.get('upperPrice', 0))
                        conf_lower = float(config.get('lowerPrice', 0))
                        if conf_upper <= 0:
                            if trade_layers > 0 and layer_percent > 0:
                                upper_price = base_price * math.pow(1 + layer_percent, trade_layers)
                            else:
                                upper_price = base_price * 1.2
                        else:
                            upper_price = conf_upper

                        if conf_lower <= 0:
                            if trade_layers > 0 and layer_percent > 0:
                                lower_price = base_price * math.pow(1 + layer_percent, -trade_layers)
                            else:
                                lower_price = base_price * 0.8
                        else:
                            lower_price = conf_lower

                        last_trade_time = 0
                        last_trade_price = 0
                        layer_repeat_counts = {}
                        waiting_for_fallback = False
                        peak_price = 0.0
                        fallback_monitor_start_layer_index = 0
                        waiting_for_rebound = False
                        valley_price = 0.0
                        rebound_monitor_start_layer_index = 0
                        type_str = base_price_type_map.get(base_price_type, str(base_price_type))
                        last_trading_date = current_date
                        self.log(f"任务({id})跨交易日刷新基准价：{base_price:.3f}，类型: {type_str}，范围：[{lower_price:.3f}, {upper_price:.3f}]")

                # 6. 策略重置检查
                if max_resets > 0 and reset_count < max_resets and reset_ratio > 0:
                    if base_price <= 0:
                        base_price = current_price
                        time.sleep(monitor_interval)
                        continue

                    deviation = (current_price - base_price) / base_price
                    if abs(deviation) >= reset_ratio / 100.0:
                        direction_str = "上涨" if deviation > 0 else "下跌"
                        self.log(f"任务({id})触发{direction_str}重置：价格 {current_price} 偏离基准 {base_price} 达 {abs(deviation)*100:.2f}% (阈值 {reset_ratio}%)，进度 ({reset_count+1}/{max_resets})")
                        
                        base_price = current_price
                        last_layer_index = 0 # current_price is new base
                        
                        # 重新获取配置以支持动态调整（如果 config 对象内容更新）
                        conf_upper = float(config.get('upperPrice', 0))
                        conf_lower = float(config.get('lowerPrice', 0))
                        
                        # 更新上限
                        if conf_upper <= 0: 
                            if trade_layers > 0 and layer_percent > 0:
                                upper_price = base_price * math.pow(1 + layer_percent, trade_layers)
                            else:
                                upper_price = base_price * 1.2
                        else:
                            upper_price = conf_upper # 确保固定上限也更新（如果用户修改了配置）
                        
                        # 更新下限
                        if conf_lower <= 0: 
                            if trade_layers > 0 and layer_percent > 0:
                                lower_price = base_price * math.pow(1 + layer_percent, -trade_layers)
                            else:
                                lower_price = base_price * 0.8
                        else:
                            lower_price = conf_lower # 确保固定下限也更新
                        
                        # 检查新基准价是否在有效范围内
                        if (upper_price > 0 and base_price > upper_price) or (lower_price > 0 and base_price < lower_price):
                            self.log(f"警告：重置后的基准价 {base_price} 超出策略范围 [{lower_price}, {upper_price}]，请检查参数设置。", "WARNING")

                        reset_count += 1
                        self.log(f"任务({id})重置完成，新基准：{base_price:.3f}, 范围：[{lower_price:.3f}, {upper_price:.3f}]")
                        time.sleep(monitor_interval)
                        continue

                # 7. 风险控制 (止盈止损)
                # 止盈检查
                trigger_tp = False
                if tp_type == 0: # 任意满足
                    if (tp_price > 0 and current_price >= tp_price) or \
                       (tp_ratio > 0 and (current_price - base_price)/base_price >= tp_ratio/100.0):
                        trigger_tp = True
                elif tp_type == 1: # 按比例
                    if tp_ratio > 0 and (current_price - base_price)/base_price >= tp_ratio/100.0:
                        trigger_tp = True
                elif tp_type == 2: # 按价格
                    if tp_price > 0 and current_price >= tp_price:
                        trigger_tp = True

                if trigger_tp:
                    self.log(f"任务({id})触发止盈，价格：{current_price}！正在退出...", "WARNING")
                    self._stop_profit_sell(stock_code, current_price)
                    break
                
                # 止损检查
                trigger_sl = False
                if sl_type == 0: # 任意满足
                    if (sl_price > 0 and current_price <= sl_price) or \
                       (sl_ratio > 0 and (base_price - current_price)/base_price >= sl_ratio/100.0):
                        trigger_sl = True
                elif sl_type == 1: # 按比例
                    if sl_ratio > 0 and (base_price - current_price)/base_price >= sl_ratio/100.0:
                        trigger_sl = True
                elif sl_type == 2: # 按价格
                    if sl_price > 0 and current_price <= sl_price:
                        trigger_sl = True

                if trigger_sl:
                    self.log(f"任务({id})触发止损，价格：{current_price}！正在退出...", "WARNING")
                    self._stop_loss_sell(stock_code, current_price)
                    break

                # 8. 交易逻辑
                if current_price > upper_price:
                    # 超过上限，保持观望
                    pass
                elif current_price < lower_price:
                    # 低于下限，保持观望
                    pass
                else:
                    curr_index = self._get_layer_index(current_price, base_price)
                    if trade_layers > 0:
                        curr_index = max(-trade_layers, min(trade_layers, curr_index))
                    
                    # 交易前置检查函数
                    def check_trade_safety(action_type, price, index):
                        nonlocal last_trade_time, last_trade_price, layer_repeat_counts
                        
                        # 1. 最小交易间隔检查
                        if min_trade_interval > 0 and time.time() - last_trade_time < min_trade_interval:
                            return False, f"未满足最小交易间隔 {min_trade_interval}s"
                            
                        # 2. 最小价差检查 (如果是重复交易或震荡)
                        if last_trade_price > 0:
                            gap = abs(price - last_trade_price) / last_trade_price
                            if gap < min_price_gap:
                                return False, f"未满足最小价差 {min_price_gap*100}% (当前 {gap*100:.2f}%)"

                        # 3. 同层级最大交易次数检查
                        # max_repeat_times 为 0 时表示不限制
                        if max_repeat_times > 0:
                            current_count = layer_repeat_counts.get(index, 0)
                            if index == last_layer_index and current_count >= max_repeat_times:
                                return False, f"层级 {index} 交易次数已达上限 {max_repeat_times}"
                            
                        return True, ""

                    # 更新交易状态函数
                    def update_trade_state(price, index):
                        nonlocal last_trade_time, last_trade_price, layer_repeat_counts, last_layer_index
                        last_trade_time = time.time()
                        last_trade_price = price
                        
                        # 如果是新层级，重置该层级计数
                        if index != last_layer_index:
                            layer_repeat_counts[index] = 1
                        else:
                            layer_repeat_counts[index] = layer_repeat_counts.get(index, 0) + 1
                            
                        last_layer_index = index

                    # 优化：支持同层级震荡交易（重复买入卖出）
                    # 只要跨过层级线（index变化）就触发，无需完全穿越
                    # 或者：允许同层级重复交易且满足价差
                    is_sell_signal = False
                    is_buy_signal = False
                    sell_triggered_by_fallback = False

                    raw_sell_signal = False
                    raw_buy_signal = False
                    if curr_index > last_layer_index:
                        raw_sell_signal = True
                    elif curr_index < last_layer_index:
                        raw_buy_signal = True
                    elif curr_index == last_layer_index and last_trade_price > 0:
                        if current_price > last_trade_price:
                            raw_sell_signal = True
                        elif current_price < last_trade_price:
                            raw_buy_signal = True

                    buy_allowed = trade_direction in [0, 1] and not (deployment_mode == 'PARTITIONED' and (curr_index > 0 if include_base_layer else curr_index >= 0))
                    sell_allowed = trade_direction in [0, 2] and not (deployment_mode == 'PARTITIONED' and (curr_index < 0 if include_base_layer else curr_index <= 0))

                    # 1. 回落卖出逻辑
                    if fallback_ratio > 0 and sell_allowed:
                        if waiting_for_fallback:
                            if current_price > peak_price:
                                peak_price = current_price

                            if current_price <= peak_price * (1 - fallback_ratio):
                                self.log(f"任务({id})满足回落卖出条件：峰值 {peak_price} -> 当前 {current_price}")
                                is_sell_signal = True
                                sell_triggered_by_fallback = True
                            elif curr_index < fallback_monitor_start_layer_index:
                                self.log(f"任务({id})价格回落至原层级线({curr_index})，未满足回落比例，取消回落卖出监控。")
                                waiting_for_fallback = False
                                peak_price = 0
                        elif raw_sell_signal:
                            waiting_for_fallback = True
                            peak_price = current_price
                            fallback_monitor_start_layer_index = curr_index
                            self.log(f"任务({id})触发上涨({curr_index})，进入回落监控... (目标回落 {fallback_ratio*100}%)")
                    elif sell_allowed:
                        is_sell_signal = raw_sell_signal

                    # 2. 反弹买入逻辑
                    buy_triggered_by_rebound = False
                    if rebound_ratio > 0 and buy_allowed:
                        if waiting_for_rebound:
                            if valley_price == 0 or current_price < valley_price:
                                valley_price = current_price
                            
                            if current_price >= valley_price * (1 + rebound_ratio):
                                self.log(f"任务({id})满足反弹买入条件：谷值 {valley_price} -> 当前 {current_price}")
                                is_buy_signal = True
                                buy_triggered_by_rebound = True
                            elif curr_index > rebound_monitor_start_layer_index:
                                self.log(f"任务({id})价格反弹至原层级线({curr_index})，未满足反弹比例，取消反弹买入监控。")
                                waiting_for_rebound = False
                                valley_price = 0
                        elif raw_buy_signal:
                            waiting_for_rebound = True
                            valley_price = current_price
                            rebound_monitor_start_layer_index = curr_index
                            self.log(f"任务({id})触发下跌({curr_index})，进入反弹监控... (目标反弹 {rebound_ratio*100}%)")
                    elif buy_allowed:
                        is_buy_signal = raw_buy_signal

                    if is_sell_signal:
                        # 价格上涨 -> 卖出
                        
                        # 分治模式检查：基准线及之下禁止卖出（若包含基准层则Layer<0，否则Layer<=0）
                        if deployment_mode == 'PARTITIONED' and (curr_index < 0 if include_base_layer else curr_index <= 0):
                            self.log(f"任务({id})分治模式限制：基准线及之下不执行卖出 (当前 {curr_index})", "DEBUG")
                            if sell_triggered_by_fallback:
                                waiting_for_fallback = False
                                peak_price = 0
                            if curr_index != last_layer_index:
                                last_layer_index = curr_index
                            time.sleep(monitor_interval)
                            continue

                        if trade_direction not in [0, 2]: # 0:双向 1:只买 2:只卖
                            # self.log(f"任务({id})触发卖出信号但方向限制，跳过")
                            if sell_triggered_by_fallback:
                                waiting_for_fallback = False
                                peak_price = 0
                            if curr_index != last_layer_index:
                                last_layer_index = curr_index
                            time.sleep(monitor_interval)
                            continue
                        
                        # 安全检查
                        is_safe, unsafe_reason = check_trade_safety('sell', current_price, curr_index)
                        if not is_safe:
                             if sell_triggered_by_fallback:
                                 self.log(f"任务({id})满足回落卖出条件，但未通过安全检查: {unsafe_reason}", "WARNING")
                             time.sleep(monitor_interval) # 避免死循环空转
                             continue

                        # 计算交易量
                        trade_vol = base_quantity
                        if trade_quantity_type == 2: # 层级倍数
                            # 进出平衡逻辑：取绝对值较大的索引作为倍数
                            # 跌下去买入2倍(curr=-2)，涨回来卖出2倍(last=-2)
                            idx_val = max(abs(curr_index), abs(last_layer_index))
                            factor = idx_val if idx_val > 0 else 1
                            trade_vol = base_quantity * factor
                        
                        self.log(f"任务({id})上涨：{current_price} (层级 {last_layer_index} -> {curr_index}) -> 卖出 {trade_vol}")
                        
                        # 检查持仓
                        pos = self.trader.get_position(stock_code)
                        available = pos.get('available_quantity', 0)
                        
                        if available >= trade_vol:
                            reason = f"任务: {name}({id})\n原因: 上涨触发"
                            res = self._safe_sell(stock_code, current_price, trade_vol, reason=reason)
                            if res:
                                self.log(f"任务({id})卖出委托已发送：{res}")
                                self._save_trade_record("sell", current_price, trade_vol, f"Grid Sell {curr_index}")
                                self._update_task_position(stock_code)
                                update_trade_state(current_price, curr_index)
                                if sell_triggered_by_fallback:
                                    waiting_for_fallback = False
                                    peak_price = 0
                            elif not res:
                                pass
                        else:
                            self.log(f"任务({id})可卖持仓不足。需 {trade_vol}，有 {available}，可能是T+1限制导致无法卖出。", "WARNING")
                            if sell_triggered_by_fallback:
                                waiting_for_fallback = False
                                peak_price = 0
                            last_layer_index = curr_index 
                             
                    elif is_buy_signal:
                        # 价格下跌 -> 买入
                        
                        # 分治模式检查：基准线及之上禁止买入（若包含基准层则Layer>0，否则Layer>=0）
                        if deployment_mode == 'PARTITIONED' and (curr_index > 0 if include_base_layer else curr_index >= 0):
                            self.log(f"任务({id})分治模式限制：基准线及之上不执行层级买入 (当前 {curr_index})", "DEBUG")
                            last_layer_index = curr_index
                            time.sleep(monitor_interval)
                            continue

                        if trade_direction not in [0, 1]: # 0:双向 1:只买 2:只卖
                            # self.log(f"任务({id})触发买入信号但方向限制，跳过")
                            last_layer_index = curr_index
                            time.sleep(monitor_interval)
                            continue
                            
                        # 安全检查
                        is_safe, unsafe_reason = check_trade_safety('buy', current_price, curr_index)
                        if not is_safe:
                             if buy_triggered_by_rebound:
                                 self.log(f"任务({id})满足反弹买入条件，但未通过安全检查: {unsafe_reason}", "WARNING")
                             time.sleep(monitor_interval)
                             continue

                        # 计算交易量
                        trade_vol = base_quantity
                        if trade_quantity_type == 2:
                            # 进出平衡逻辑
                            idx_val = max(abs(curr_index), abs(last_layer_index))
                            factor = idx_val if idx_val > 0 else 1
                            trade_vol = base_quantity * factor

                        self.log(f"任务({id})下跌：{current_price} (层级 {last_layer_index} -> {curr_index}) -> 买入 {trade_vol}")
                        
                        # 持仓检查 (Max Hold)
                        pos = self.trader.get_position(stock_code)
                        total_pos = pos.get('total_quantity', 0)
                        
                        allow_buy = True
                        
                        # Max Hold Check
                        if max_hold_type == -1: # 不限制
                             pass
                        elif max_hold_type == 0: # 任意满足
                             is_limit_reached = False
                             
                             # 1. Check Quantity
                             if max_hold_quantity > 0 and total_pos + trade_vol > max_hold_quantity:
                                 is_limit_reached = True
                                 
                             # 2. Check Amount
                             elif max_hold_amount > 0 and (total_pos + trade_vol) * current_price > max_hold_amount:
                                 is_limit_reached = True
                                 
                             # 3. Check Ratio
                             elif max_hold_ratio > 0:
                                 balance = self.trader.get_balance()
                                 total_asset = balance.get('total_asset', 0)
                                 if total_asset > 0:
                                     current_hold_value = total_pos * current_price
                                     new_hold_value = trade_vol * current_price
                                     total_hold_value = current_hold_value + new_hold_value
                                     new_ratio = (total_hold_value / total_asset) * 100
                                     if new_ratio > max_hold_ratio:
                                         is_limit_reached = True

                             if is_limit_reached:
                                 allow_buy = False
                                 self.log(f"任务({id})超过最大持仓限制(任意: 量/额/率)", "WARNING")
                        elif max_hold_type == 1: # 按量
                             if max_hold_quantity > 0 and total_pos + trade_vol > max_hold_quantity:
                                 allow_buy = False
                                 self.log(f"任务({id})超过最大持仓量 {max_hold_quantity}", "WARNING")
                        elif max_hold_type == 2: # 按额
                             if max_hold_amount > 0 and (total_pos + trade_vol) * current_price > max_hold_amount:
                                 allow_buy = False
                                 self.log(f"任务({id})超过最大持仓金额 {max_hold_amount}", "WARNING")
                        elif max_hold_type == 3: # 按比例
                            if max_hold_ratio > 0:
                                # 需要获取总资产
                                balance = self.trader.get_balance()
                                total_asset = balance.get('total_asset', 0)
                                if total_asset > 0:
                                    new_ratio = ((total_pos + trade_vol) * current_price / total_asset) * 100
                                    if new_ratio > max_hold_ratio:
                                        allow_buy = False
                                        self.log(f"任务({id})超过最大持仓比例 {max_hold_ratio}% (当前预测 {new_ratio:.2f}%)", "WARNING")
                        
                        if allow_buy:
                            reason = f"任务: {name}({id})\n原因: 下跌触发"
                            balance = self.trader.get_balance()
                            available_balance = balance.get('available_balance', 0)
                            need_cash = trade_vol * current_price

                            if self.enable_real_trade and available_balance < need_cash:
                                self.log(f"任务({id})资金不足，跳过买入。需 {need_cash:.2f}，有 {available_balance:.2f}", "WARNING")
                                if buy_triggered_by_rebound:
                                    waiting_for_rebound = False
                                    valley_price = 0
                                last_layer_index = curr_index
                            else:
                                res = self._safe_buy(stock_code, current_price, trade_vol, reason=reason)
                                if res:
                                    self.log(f"任务({id})买入委托已发送：{res}")
                                    self._save_trade_record("buy", current_price, trade_vol, f"Grid Buy {curr_index}")
                                    self._update_task_position(stock_code)
                                    update_trade_state(current_price, curr_index)
                                    if buy_triggered_by_rebound:
                                        waiting_for_rebound = False
                                        valley_price = 0
                        else:
                            if buy_triggered_by_rebound:
                                waiting_for_rebound = False
                                valley_price = 0
                            last_layer_index = curr_index
            
            except Exception as e:
                self.log(f"任务({id})循环错误：{e}", "ERROR")
                import traceback
                traceback.print_exc()
            
            time.sleep(monitor_interval)

    def _get_layer_index(self, price, base_price):
        """计算层级索引"""
        if price <= 0 or base_price <= 0 or self.log_layer_base == 0: return 0
        
        raw_float = math.log(price / base_price) / self.log_layer_base

        if self.zeroLayerMode == 1: # 双倍宽(Base±P)
            raw_int = int(math.floor(raw_float))
            if raw_int == -1:
                return 0
            elif raw_int < -1:
                return raw_int + 1
            else:
                return raw_int

        elif self.zeroLayerMode == 2: # 中心对称(Base±P/2)
            return int(math.floor(raw_float + 0.5))
            
        else: # self.zeroLayerMode == 3: # 标准单边(Base~Base+P)
            return int(math.floor(raw_float))


    def _stop_profit_sell(self, stock_code, price):
        pos = self.trader.get_position(stock_code)
        avail = pos.get('available_quantity', 0)
        if avail > 0:
            name = self.data.get('name', 'Unknown')
            reason = f"任务: {name}({self.data.get('id')})\n原因: 触发止盈"
            res = self._safe_sell(stock_code, price, avail, reason=reason)
            if res:
                self._save_trade_record("sell", price, avail, "Stop Profit")
        else:
            self.log(f"任务({self.data.get('id')})触发止盈，但可用持仓不足(可能是T+1限制)，无法执行卖出。", "WARNING")

    def _stop_loss_sell(self, stock_code, price):
        pos = self.trader.get_position(stock_code)
        avail = pos.get('available_quantity', 0)
        if avail > 0:
            name = self.data.get('name', 'Unknown')
            reason = f"任务: {name}({self.data.get('id')})\n原因: 触发止损"
            res = self._safe_sell(stock_code, price, avail, reason=reason)
            if res:
                self._save_trade_record("sell", price, avail, "Stop Loss")
        else:
            self.log(f"任务({self.data.get('id')})触发止损，但可用持仓不足(可能是T+1限制)，无法执行卖出。", "WARNING")

    def _safe_buy(self, stock_code, price, quantity, reason):
        if not self.enable_real_trade:
            self.log(f"【模拟交易】触发买入：{stock_code}, 价格 {price}, 数量 {quantity}\n原因: {reason}", "WARNING")
            return {"id": "sim_buy", "status": "simulated"}
        return self.trader.buy(stock_code, price, quantity, reason=reason)

    def _safe_sell(self, stock_code, price, quantity, reason):
        if not self.enable_real_trade:
            self.log(f"【模拟交易】触发卖出：{stock_code}, 价格 {price}, 数量 {quantity}\n原因: {reason}", "WARNING")
            return {"id": "sim_sell", "status": "simulated"}
        return self.trader.sell(stock_code, price, quantity, reason=reason)

    def _update_task_position(self, stock_code):
        try:
            position = self.trader.get_position(stock_code)
            
            data = {
                "id": self.data.get('id'),
                "positions": [position], 
            }
            
            self._update_trade_task(data)
        except Exception as e:
            self.log(f"更新持仓数据失败: {e}", "WARNING")

    def _update_trade_task(self, data):
        backend_url = self.data.get('backend_url')
        token = self.data.get('token')
        
        if not backend_url or not token:
            return

        if backend_url.endswith('/'):
            backend_url = backend_url[:-1]
            
        url = f"{backend_url}/quant/tradeTask/updateTradeTask"
        
        headers = {
            "x-token": token,
            "Content-Type": "application/json"
        }
        
        try:
            if hasattr(self, 'session'):
                self.session.put(url, json=data, headers=headers, timeout=5)
            else:
                requests.put(url, json=data, headers=headers, timeout=5)
            
            # 通知前端刷新交易任务
            self.log("TRADE_TASK_UPDATE_TRIGGER")
        except Exception as e:
            pass

    def _save_trade_record(self, action, price, quantity, reason="grid_trade"):
        backend_url = self.data.get('backend_url')
        token = self.data.get('token')
        
        if not backend_url or not token:
            return

        if backend_url.endswith('/'):
            backend_url = backend_url[:-1]
            
        url = f"{backend_url}/quant/tradeRecord/createTradeRecord"
        
        stock_info = self.data.get('task', {}).get('stock', {})
        if isinstance(stock_info, str):
            try: stock_info = json.loads(stock_info)
            except: pass

        account = self.data.get('account', {})

        data = {
            "member_id": account.get('member_id'),
            "account_id": account.get('id'),
            "task_id": self.data.get('id'),
            "symbol": stock_info.get('ts_code', ''),
            "name": stock_info.get('name', ''),
            "price": float(price),
            "quantity": float(quantity),
            "amount": float(price) * float(quantity),
            "action": action, 
            "reason": reason,
            "traded_at": time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
        }
        
        headers = {
            "x-token": token,
            "Content-Type": "application/json"
        }
        
        try:
            if hasattr(self, 'session'):
                self.session.post(url, json=data, headers=headers, timeout=5)
            else:
                requests.post(url, json=data, headers=headers, timeout=5)
            
            # 通知前端刷新交易记录
            self.log("TRADE_RECORD_UPDATE_TRIGGER")
        except Exception as e:
            pass

    def _is_trading_time(self):
        if getattr(self, 'ignore_trading_time', False):
            return True
        now = datetime.datetime.now()

        if now.weekday() > 4:
            return False

        current = now.time()
        morning_start = datetime.time(9, 25, 0)
        morning_end = datetime.time(11, 30, 0)
        afternoon_start = datetime.time(13, 0, 0)
        afternoon_end = datetime.time(15, 0, 0)

        return (morning_start <= current < morning_end) or (afternoon_start <= current < afternoon_end)
