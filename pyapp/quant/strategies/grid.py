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
                # validityPeriod 可能是 YYYY-MM-DD 字符串
                if isinstance(validity_period, str):
                    dt = datetime.datetime.strptime(validity_period[:10], "%Y-%m-%d")
                    # 设置为当天收盘时间 (15:00:00)
                    self.expiration_time = dt.replace(hour=15, minute=0, second=0, microsecond=0)
            except Exception as e:
                self.log(f"配置错误: 无效的有效期格式 {validity_period}: {e}", "ERROR")

    def run(self):
        id = self.data.get('id', 0)
        name = self.data.get('name', 'Unknown')
        self.log(f"正在启动任务({id})：{name}...") 
        
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
            self.log(f"任务({id})错误：未找到股票代码。", "ERROR")
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
         
        waiting_for_fallback = False
        peak_price = 0.0

        # 基准价参数
        base_price_type = int(config.get('basePriceType', 0)) # 0:无/默认 1:指定 2:当前 3:开盘 4:昨收
        manual_base_price = float(config.get('basePrice', 0))
        base_price_float_ratio = float(config.get('basePriceFloatRatio', 0))
        
        # 交易量参数
        trade_quantity_type = int(config.get('tradeQuantityType', 1)) # 1:固定 2:倍数
        auto_align = bool(config.get('autoAlign', False))
        auto_open_position = bool(config.get('autoOpenPosition', False))
        open_position_type = int(config.get('openPositionType', 0))
        open_position_quantity = int(config.get('openPositionQuantity', 100))
        open_position_amount = float(config.get('openPositionAmount', 10000))
        open_position_ratio = float(config.get('openPositionRatio', 10))
        allow_repeat_trade = bool(config.get('allowRepeatTrade', True))
        
        fallback_ratio = float(config.get('fallbackRatio', 0)) / 100.0
        # 交易保护参数
        min_price_gap = float(config.get('minPriceGap', 0.1)) / 100.0
        min_trade_interval = int(config.get('minTradeInterval', 5))
        max_repeat_times = int(config.get('maxRepeatTimes', 3))
        
        # 交易模式：全区间 vs 分治
        # deploymentMode: FULL_RANGE(默认) - 全区间策略，任意位置均可买卖
        #                 PARTITIONED - 分治模式，基准线之上只卖不买，基准线之下只买不卖
        deployment_mode = config.get('deploymentMode', 'FULL_RANGE')
        # self.log(f"任务({id})策略模式: {deployment_mode}")

        # 价格区间
        upper_price = float(config.get('upperPrice', 0))
        lower_price = float(config.get('lowerPrice', 0))
        
        # 持仓限制
        max_hold_type = int(config.get('maxHoldType', -1)) # -1:不限 0:任意 1:量 2:额 3:比例
        max_hold = int(config.get('maxHold', 10000))
        max_hold_amount = float(config.get('maxHoldAmount', 0))
        max_hold_ratio = float(config.get('maxHoldRatio', 0))
        
        # 止盈止损
        tp_type = int(config.get('takeProfitType', -1)) # -1:不限 0:任意 1:比例 2:价格
        tp_ratio = float(config.get('takeProfitRatio', 0))
        tp_price = float(config.get('takeProfitPrice', 0))
        
        sl_type = int(config.get('stopLossType', -1))
        sl_ratio = float(config.get('stopLossRatio', 0))
        sl_price = float(config.get('stopLossPrice', 0))

        # 4. 初始化基准价格
        # 获取股票详细信息
        quote = self.trader.get_stock_quote(ts_code)
        current_price = quote.get('price', 0)
        
        if current_price <= 0:
            # 尝试再次获取
            time.sleep(1)
            quote = self.trader.get_stock_quote(ts_code)
            current_price = quote.get('price', 0)
            if current_price <= 0:
                self.log(f"任务({id})错误：无法获取实时行情数据。", "ERROR")
                return

        open_price = quote.get('open', 0)
        pre_close = quote.get('pre_close', 0)
        
        # 确定基准价
        base_price = 0.0
        if base_price_type == 1: # 指定价
            base_price = manual_base_price
        elif base_price_type == 2: # 当前价
            base_price = current_price
        elif base_price_type == 3: # 开盘价
            base_price = open_price if open_price > 0 else current_price
        elif base_price_type == 4: # 昨收价
            base_price = pre_close if pre_close > 0 else current_price
        else: # 默认逻辑
            base_price = manual_base_price if manual_base_price > 0 else current_price
            
        if base_price <= 0:
            base_price = current_price
            
        # 应用基准价浮动
        if base_price_float_ratio != 0:
            base_price = base_price * (1 + base_price_float_ratio / 100.0)
            
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
        
        self.log(f"任务({id})配置：标的={ts_code}, 价格范围=[{lower_price:.3f}, {upper_price:.3f}], 层级={trade_layers}, 间隔={layer_percent*100}%, 基数={base_quantity}(股)")
        
        # 优化：预计算对数常数
        if layer_percent > 0:
            self.log_layer_base = math.log(1 + layer_percent)
        else:
            self.log_layer_base = 0.01 
            
        # 初始层级状态
        last_layer_index = self._get_layer_index(current_price, base_price)
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
                        res = self.trader.sell(stock_code, current_price, align_vol, reason=f"任务: {name}({id})\n原因: 启动自动补卖")
                        if res:
                            self._save_trade_record("sell", current_price, align_vol, f"Auto Align {last_layer_index}")
                            self._update_task_position(stock_code)
                    else:
                        self.log(f"任务({id})启动补卖失败：持仓不足(需{align_vol}, 有{available})", "WARNING")

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
                    
                    if available_balance >= need_cash:
                        res = self.trader.buy(stock_code, current_price, align_vol, reason=f"任务: {name}({id})\n原因: 启动自动补买")
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
                    
                    if available_balance >= need_cash:
                        reason = f"任务: {name}({id})\n原因: 自动建仓"
                        res = self.trader.buy(stock_code, current_price, open_vol, reason=reason)
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
        self.log(f"任务({id})初始化完成，运行主策略...")

        while self.running:
            try:
                # 0. 有效期检查
                if self.expiration_time:
                    now = datetime.datetime.now()
                    if now > self.expiration_time:
                        self.log(f"任务({id})有效期已至 ({self.expiration_time})，自动停止任务...", "WARNING")
                        
                        # 自动停止任务
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

                # 6. 策略重置检查
                if max_resets > 0 and reset_count < max_resets and reset_ratio > 0:
                    if base_price <= 0:
                        base_price = current_price
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
                    
                    # 交易前置检查函数
                    def check_trade_safety(action_type, price, index):
                        nonlocal last_trade_time, last_trade_price, layer_repeat_counts
                        
                        # 1. 最小交易间隔检查
                        if min_trade_interval > 0 and time.time() - last_trade_time < min_trade_interval:
                            # self.log(f"未满足最小交易间隔 {min_trade_interval}s", "DEBUG")
                            return False
                            
                        # 2. 最小价差检查 (如果是重复交易或震荡)
                        if last_trade_price > 0:
                            gap = abs(price - last_trade_price) / last_trade_price
                            if gap < min_price_gap:
                                # self.log(f"未满足最小价差 {min_price_gap*100}% (当前 {gap*100:.2f}%)", "DEBUG")
                                return False

                        # 3. 同层级最大交易次数检查
                        # max_repeat_times 为 0 时表示不限制
                        if max_repeat_times > 0:
                            current_count = layer_repeat_counts.get(index, 0)
                            if index == last_layer_index and current_count >= max_repeat_times:
                                # self.log(f"层级 {index} 交易次数已达上限 {max_repeat_times}", "DEBUG")
                                return False
                            
                        return True

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
                    elif allow_repeat_trade and curr_index == last_layer_index and last_trade_price > 0:
                        if current_price > last_trade_price:
                            raw_sell_signal = True
                        elif current_price < last_trade_price:
                            raw_buy_signal = True

                    sell_allowed = trade_direction in [0, 2] and not (deployment_mode == 'PARTITIONED' and curr_index < 0)
                    buy_allowed = trade_direction in [0, 1] and not (deployment_mode == 'PARTITIONED' and curr_index > 0)

                    if fallback_ratio > 0 and sell_allowed:
                        if waiting_for_fallback:
                            if current_price > peak_price:
                                peak_price = current_price

                            if curr_index <= last_layer_index:
                                self.log(f"任务({id})价格回落至原层级线({curr_index})，取消回落卖出监控。")
                                waiting_for_fallback = False
                                peak_price = 0
                                if buy_allowed:
                                    is_buy_signal = raw_buy_signal
                            elif current_price <= peak_price * (1 - fallback_ratio):
                                self.log(f"任务({id})满足回落卖出条件：峰值 {peak_price} -> 当前 {current_price}")
                                is_sell_signal = True
                                sell_triggered_by_fallback = True
                            else:
                                pass
                        else:
                            if raw_sell_signal:
                                waiting_for_fallback = True
                                peak_price = current_price
                                self.log(f"任务({id})触发上涨({curr_index})，进入回落监控... (目标回落 {fallback_ratio*100}%)")
                            else:
                                if buy_allowed:
                                    is_buy_signal = raw_buy_signal
                    else:
                        if sell_allowed:
                            is_sell_signal = raw_sell_signal
                        if buy_allowed:
                            is_buy_signal = raw_buy_signal

                    if is_sell_signal:
                        # 价格上涨 -> 卖出
                        
                        # 分治模式检查：基准线之下禁止卖出（除非是止盈止损，但止盈止损在前面已处理）
                        # 注意：curr_index < 0 表示在基准线之下
                        if deployment_mode == 'PARTITIONED' and curr_index < 0:
                            self.log(f"任务({id})分治模式限制：基准线之下不执行卖出 (当前 {curr_index})", "DEBUG")
                            if sell_triggered_by_fallback:
                                waiting_for_fallback = False
                                peak_price = 0
                            if curr_index != last_layer_index:
                                last_layer_index = curr_index
                            continue

                        if trade_direction not in [0, 2]: # 0:双向 1:只买 2:只卖
                            # self.log(f"任务({id})触发卖出信号但方向限制，跳过")
                            if sell_triggered_by_fallback:
                                waiting_for_fallback = False
                                peak_price = 0
                            if curr_index != last_layer_index:
                                last_layer_index = curr_index
                            continue
                        
                        # 安全检查
                        if not check_trade_safety('sell', current_price, curr_index):
                             time.sleep(1) # 避免死循环空转
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
                            res = self.trader.sell(stock_code, current_price, trade_vol, reason=reason)
                            if res:
                                self.log(f"任务({id})卖出委托已发送：{res}")
                                self._save_trade_record("sell", current_price, trade_vol, f"Grid Sell {curr_index}")
                                self._update_task_position(stock_code)
                                update_trade_state(current_price, curr_index)
                                if sell_triggered_by_fallback:
                                    waiting_for_fallback = False
                                    peak_price = 0
                            # 卖出失败时
                            elif allow_repeat_trade:
                                # 如果允许重复交易，不更新 last_layer_index，允许下次重试
                                pass
                            else:
                                # 否则跳过该层级
                                last_layer_index = curr_index
                        else:
                            self.log(f"任务({id})可卖持仓不足。需 {trade_vol}，有 {available}", "WARNING")
                            if sell_triggered_by_fallback:
                                waiting_for_fallback = False
                                peak_price = 0
                            if not allow_repeat_trade:
                                last_layer_index = curr_index 
                             
                    elif is_buy_signal:
                        # 价格下跌 -> 买入
                        
                        # 分治模式检查：基准线之上禁止买入
                        # 注意：curr_index > 0 表示在基准线之下
                        if deployment_mode == 'PARTITIONED' and curr_index > 0:
                            self.log(f"任务({id})分治模式限制：基准线之上不执行层级买入 (当前 {curr_index})", "DEBUG")
                            last_layer_index = curr_index
                            continue

                        if trade_direction not in [0, 1]: # 0:双向 1:只买 2:只卖
                            # self.log(f"任务({id})触发买入信号但方向限制，跳过")
                            last_layer_index = curr_index
                            continue
                            
                        # 安全检查
                        if not check_trade_safety('buy', current_price, curr_index):
                             time.sleep(1)
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
                        total_pos = pos.get('total', 0)
                        
                        allow_buy = True
                        
                        # Max Hold Check
                        if max_hold_type == 0: # 任意满足
                             if (max_hold > 0 and total_pos + trade_vol > max_hold) or \
                                (max_hold_amount > 0 and (total_pos + trade_vol) * current_price > max_hold_amount):
                                 allow_buy = False
                                 self.log(f"任务({id})超过最大持仓限制(任意)", "WARNING")
                        elif max_hold_type == 1: # 按量
                             if max_hold > 0 and total_pos + trade_vol > max_hold:
                                 allow_buy = False
                                 self.log(f"任务({id})超过最大持仓量 {max_hold}", "WARNING")
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
                        else: # 兼容旧逻辑
                             # 检查最大持仓
                             current_hold_amount = total_pos * current_price
                             new_amount = trade_vol * current_price
                             if (max_hold > 0 and total_pos + trade_vol > max_hold) or \
                                (max_hold_amount > 0 and current_hold_amount + new_amount > max_hold_amount):
                                 allow_buy = False
                                 self.log(f"任务({id})达到最大持仓限制", "WARNING")
                        
                        if allow_buy:
                            reason = f"任务: {name}({id})\n原因: 下跌触发"
                            res = self.trader.buy(stock_code, current_price, trade_vol, reason=reason)
                            if res:
                                self.log(f"任务({id})买入委托已发送：{res}")
                                self._save_trade_record("buy", current_price, trade_vol, f"Grid Buy {curr_index}")
                                self._update_task_position(stock_code)
                                update_trade_state(current_price, curr_index)
                            # 买入失败时
                            elif allow_repeat_trade:
                                # 如果允许重复交易，不更新 last_layer_index，允许下次重试
                                pass
                            else:
                                # 否则跳过该层级
                                last_layer_index = curr_index
                        else:
                            if not allow_repeat_trade:
                                last_layer_index = curr_index
            
            except Exception as e:
                self.log(f"任务({id})循环错误：{e}", "ERROR")
                import traceback
                traceback.print_exc()
            
            time.sleep(monitor_interval)

    def _get_layer_index(self, price, base_price):
        """计算层级索引"""
        if price <= 0 or base_price <= 0 or self.log_layer_base == 0: return 0
        return int(math.log(price / base_price) / self.log_layer_base)

    def _stop_profit_sell(self, stock_code, price):
        pos = self.trader.get_position(stock_code)
        avail = pos.get('available_quantity', 0)
        if avail > 0:
            name = self.data.get('name', 'Unknown')
            reason = f"任务: {name}({self.data.get('id')})\n原因: 触发止盈"
            res = self.trader.sell(stock_code, price, avail, reason=reason)
            self._save_trade_record("sell", price, avail, "Stop Profit")

    def _stop_loss_sell(self, stock_code, price):
        pos = self.trader.get_position(stock_code)
        avail = pos.get('available_quantity', 0)
        if avail > 0:
            name = self.data.get('name', 'Unknown')
            reason = f"任务: {name}({self.data.get('id')})\n原因: 触发止损"
            res = self.trader.sell(stock_code, price, avail, reason=reason)
            self._save_trade_record("sell", price, avail, "Stop Loss")

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
        """
        检查当前是否为交易时间（周一到周五 9:25-11:30 或 13:00-15:00）
        """
        # 如果是回测模式或调试模式，可能需要忽略此检查
        now = datetime.datetime.now()
        
        # 1. 检查周末
        if now.weekday() > 4: # 0-4 is Mon-Fri, 5-6 is Sat-Sun
            return False
            
        # 2. 检查时间段，转换为分钟数方便比较
        current_minute = now.hour * 60 + now.minute
        
        # 9:15 = 9*60 + 15 = 555
        # 9:25 = 9*60 + 25 = 565
        # 11:30 = 11*60 + 30 = 690
        # 13:00 = 13*60 = 780
        # 15:00 = 15*60 = 900

        # 交易时间（9:25-11:30）或（13:00-15:00）
        if (565 <= current_minute <= 690) or (780 <= current_minute <= 900):
            return True
            
        # 集合竞价（9:15-9:25）
        if 555 <= current_minute < 565:
            return False

        # 收盘后（15:00）
        if current_minute > 900:
            return False
            
        # 其他时间 (盘前、午休)
        return False
