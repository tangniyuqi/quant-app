# -*- coding: utf-8 -*-
import time
import json
import httpx
import threading
from datetime import datetime
from ..base import BaseStrategy

class EventStrategy(BaseStrategy):
    def __init__(self, data, log_callback=None):
        super().__init__(data, log_callback)
        self._init_config()
        self.last_news_id = 0
        self.running = False

    def _init_config(self):
        config = self.data.get('task', {}).get('config', {})
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except Exception as e:
                self.log(f"配置解析失败: {e}", "WARNING")
                config = {}

        server = self.data.get('account', {}).get('server', {})
        self.token = self.data.get('token')
        self.backend_url = self.data.get('backend_url')

        # AI Config
        self.ai_model = server.get('ai_model', 'deepseek-chat')
        self.ai_key = server.get('ai_key', '')
        self.ai_url = server.get('ai_url', '')

        # Keywords
        self.target_keywords = config.get('targetKeywords', [])
        self.trigger_keywords = config.get('triggerKeywords', [])
        self.excluded_keywords = config.get('excludedKeywords', [])
       
        # Notification
        self.webhook_url = server.get('webhook_url', '')
        self.notify_analysis = bool(config.get('notifyAnalysis', True))
        self.notify_trade = bool(config.get('notifyTrade', True))
        
        # Deep Thinking
        self.enable_deep_thinking = bool(config.get('enableDeepThinking', False))
        self.confidence_threshold = float(config.get('confidenceThreshold', 0.7))
        
        # Trading Config
        self.enable_real_trade = bool(config.get('enableRealTrade', False))
        self.trade_direction = int(config.get('tradeDirection', 0))
        
        # Risk Control & Trade Mode
        self.trade_mode = config.get('tradeMode', 'ratio') # quantity, amount, ratio
        self.quantity = int(config.get('quantity', 100))
        self.amount = float(config.get('amount', 10000))
        self.ratio = float(config.get('ratio', 5))
        self.ratio = self.ratio / 100.0

        # 风控配置 (涨跌幅限制)
        self.max_buy_rise = config.get('maxBuyRise') # 买入涨幅上限(%)
        if self.max_buy_rise is not None:
             self.max_buy_rise = float(self.max_buy_rise)
             
        self.min_sell_fall = config.get('minSellFall') # 卖出跌幅下限(%)
        if self.min_sell_fall is not None:
             self.min_sell_fall = float(self.min_sell_fall)

        # News Source Config
        self.monitor_interval = float(config.get('monitorInterval', 60))
        self.validity_period = config.get('validityPeriod', '')
        
    def run(self):
        id = self.data.get('id', 0)
        name = self.data.get('name', 'Unknown')
        self.log(f"任务({id})：初始化已完成。")
        
        if not self.ai_key:
            self.log(f"任务({id})：未配置大模型AI Key", "ERROR")
            return

        self.last_news_id = self.fetch_latest_news_id()
        self.log(f"任务({id})：策略启动完成，开始监控快讯和AI分析...")

        while self.running:
            try:
                # 0. 检查有效期
                if self.validity_period:
                    try:
                        end_date = datetime.strptime(self.validity_period, "%Y-%m-%d").date()
                        if datetime.now().date() > end_date:
                            self.log(f"任务({id})：已过有效期({self.validity_period})，策略停止。", "INFO")
                            self.running = False
                            break
                    except Exception as e:
                        self.log(f"有效期格式解析失败: {e}", "WARNING")
                        self.validity_period = None

                # 1. 获取快讯快报
                news_list = self.fetch_news(self.last_news_id)
                
                for news in news_list:
                    self.last_news_id = max(self.last_news_id, news.get('id', 0))
                    content = news.get('content', '')
                    
                    # 2. 关键词过滤
                    if self.contains_keywords(content):
                        self.log(f"任务({id})：推送快讯-{content[:50]}...")
                            
                        # 3. AI分析
                        analysis_result = self.analyze_news_with_ai(content)
                        if analysis_result:
                            self.log(f"AI分析结果：{json.dumps(analysis_result, ensure_ascii=False)}")
                            
                            if self.notify_analysis:
                                self.send_trade_notification(content, analysis_result)
                            
                            # 4. 生成并执行交易信号
                            self.process_signal(analysis_result)
                            
                # 智能等待，支持快速停止
                end_time = time.time() + self.monitor_interval
                while self.running and time.time() < end_time:
                    # 每次休眠不超过1秒，以便及时响应停止信号
                    sleep_duration = min(1.0, end_time - time.time())
                    if sleep_duration <= 0:
                        break
                    time.sleep(sleep_duration)
                
            except Exception as e:
                self.log(f"任务({id})：策略运行异常：{e}", "ERROR")
                time.sleep(10)

    def _fetch_news_list(self, page_size=20, last_id=None):
        """
        通用的快讯获取方法
        """
        try:
            params = {
                'pageSize': page_size
            }
            if last_id:
                params['last_id'] = last_id

            headers = {
                'x-token': self.token,
                'Content-Type': 'application/json'
            }

            url = f'{self.backend_url}/quant/news/getNewsList'
            resp = httpx.get(url, params=params, headers=headers, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    if 'data' in data:
                        inner_data = data['data']
                        if isinstance(inner_data, dict) and 'list' in inner_data:
                            return inner_data['list']
            else:
                self.log(f"获取快讯失败: {resp.status_code}", "WARNING")
        except Exception as e:
            self.log(f"获取快讯异常: {e}", "WARNING")
        
        return []

    def fetch_latest_news_id(self):
        """
        获取最新的一条快讯ID
        """
        news_list = self._fetch_news_list(page_size=1)
        if news_list and len(news_list) > 0:
            return news_list[0].get('id', 0)
        return 0

    def fetch_news(self, last_id):
        """
        获取大于last_id的快讯数据
        """
        # 增加 pageSize 以防止遗漏，默认获取最新的20条
        # 后端API通常按时间倒序排列，我们取回后需要筛选 > last_id 的部分
        raw_list = self._fetch_news_list(page_size=20, last_id=last_id)
        
        # 过滤掉已处理的快讯 (id <= last_id)
        new_items = [item for item in raw_list if item.get('id', 0) > last_id]
        
        # 按ID升序排列，确保按时间顺序处理，且方便last_news_id正确更新
        new_items.sort(key=lambda x: x.get('id', 0))
        
        return new_items

    def contains_keywords(self, content):
        # 如果都没有配置，直接返回False（避免无过滤全通过）
        if not self.target_keywords and not self.trigger_keywords:
            return False

        # 转为小写进行匹配，忽略大小写差异
        content_lower = content.lower()

        # 0. 检查排除关键词 (如果有配置，必须都不包含)
        if self.excluded_keywords and any(k.lower() in content_lower for k in self.excluded_keywords):
            return False

        # 1. 检查标的关键词 (如果配置了，必须满足其一)
        if self.target_keywords and not any(k.lower() in content_lower for k in self.target_keywords):
            return False

        # 2. 检查触发关键词 (如果配置了，必须满足其一)
        if self.trigger_keywords and not any(k.lower() in content_lower for k in self.trigger_keywords):
            return False

        return True

    def _normalize_ai_content(self, value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        parts.append(text)
                        continue
                    content = item.get("content")
                    if isinstance(content, str) and content:
                        parts.append(content)
            return "".join(parts)
        try:
            return str(value)
        except Exception:
            return ""

    def _parse_ai_json(self, value):
        if isinstance(value, dict):
            return value

        text = self._normalize_ai_content(value)
        if not isinstance(text, str):
            return None
        text = text.strip()
        if not text:
            return None

        candidates = [text]

        if "```" in text:
            segment = None
            if "```json" in text:
                segment = text.split("```json", 1)[1]
            else:
                segment = text.split("```", 1)[1]
            segment = segment.split("```", 1)[0].strip()
            if segment:
                candidates.append(segment)

        obj_start = text.find("{")
        obj_end = text.rfind("}")
        if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
            candidates.append(text[obj_start:obj_end + 1].strip())

        arr_start = text.find("[")
        arr_end = text.rfind("]")
        if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
            candidates.append(text[arr_start:arr_end + 1].strip())

        for s in candidates:
            try:
                return json.loads(s)
            except Exception:
                continue

        return None

    def analyze_news_with_ai(self, content):
        """
        调用AI接口进行分析
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.ai_key}"
        }
        
        # 检查是否为支持 json_object 的模型 (DeepSeek, GPT, Qwen, Gemini, Minimax, GLM/Zhipu, Doubao)
        # 常见标识: deepseek, gpt-4, gpt-3.5, qwen, gemini, minimax, abab, glm, doubao
        model_lower = self.ai_model.lower()
        supports_json_mode = any(k in model_lower for k in ["deepseek", "gpt", "qwen", "gemini", "minimax", "abab", "glm", "doubao"])
        
        deep_thinking_instruction = ""
        if self.enable_deep_thinking:
            deep_thinking_instruction = "\n请进行深度思考，全面分析市场背景、潜在影响链条以及市场情绪，给出详尽的分析理由。"
        
        # DeepSeek, GPT, Qwen, Gemini, Minimax, GLM, Doubao 等通用模型
        # 使用 Prompt 工程 + JSON Mode (如果支持)
        prompt = f"""请分析以下财经快讯内容，判断是否对相关标的或行业构成重大利好或利空，并生成交易信号。{deep_thinking_instruction}

快讯内容：{content}

关注标的关键词：{', '.join(self.target_keywords)}
关注触发关键词：{', '.join(self.trigger_keywords)}

请务必返回合法的JSON格式结果（不要包含Markdown代码块标记），包含以下字段：
- related_stock: 相关股票代码（如 600519，如果没有明确个股则留空）
- signal: 信号类型 (buy/sell/none)
- reason: 分析理由
- confidence: 置信度 (0-1)
"""
        
        payload = {
            "model": self.ai_model,
            "messages": [
                {"role": "system", "content": "你是一个专业的量化交易助手，擅长从快讯中分析交易机会。你必须只返回纯JSON字符串，不要包含任何其他内容。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }

        # 如果模型支持 json_object 模式，则开启以增加稳定性
        if supports_json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        try:
            self.log(f"正在调用AI({self.ai_model})进行分析...")
            # 增加超时时间到60秒，并添加重试机制
            timeout = 300 if self.enable_deep_thinking else 180
            retry_count = 3
            for i in range(retry_count):
                try:
                    resp = httpx.post(self.ai_url, json=payload, headers=headers, timeout=timeout)
                    if resp.status_code == 200:
                        break
                    else:
                        self.log(f"AI API调用失败(尝试 {i+1}/{retry_count}): {resp.status_code} {resp.text}", "WARNING")
                except httpx.TimeoutException:
                    self.log(f"AI API连接超时(尝试 {i+1}/{retry_count})", "WARNING")
                except httpx.HTTPError as e:
                    self.log(f"AI API请求异常(尝试 {i+1}/{retry_count}): {e}", "WARNING")
                
                if i < retry_count - 1:
                    time.sleep(2) # 重试前等待
            else:
                # 循环正常结束意味着没有break，即全部失败
                self.log("AI API调用最终失败", "ERROR")
                return None

            if resp.status_code == 200:
                try:
                    result = resp.json()
                except Exception as e:
                    self.log(f"解析AI响应失败: {e}\n响应内容: {resp.text}", "ERROR")
                    return None

                choices = result.get("choices") if isinstance(result, dict) else None
                if not choices or not isinstance(choices, list) or not choices[0]:
                    self.log(f"AI响应格式异常: {result}", "ERROR")
                    return None

                message = choices[0].get("message") if isinstance(choices[0], dict) else None
                if not message or not isinstance(message, dict):
                    self.log(f"AI响应message格式异常: {result}", "ERROR")
                    return None

                ai_content = message.get("content")
                parsed = self._parse_ai_json(ai_content)
                if parsed is not None:
                    return parsed

                ai_text = self._normalize_ai_content(ai_content)
                self.log(f"解析AI响应JSON失败\n响应内容: {ai_text}", "ERROR")
            else:
                self.log(f"AI API调用失败: {resp.status_code} {resp.text}", "ERROR")
        except Exception as e:
            self.log(f"AI分析异常: {e}", "ERROR")
            
        return None

    def process_signal(self, analysis):
        signal = analysis.get('signal')
        stock_code = analysis.get('related_stock')
        reason = analysis.get('reason')
        try:
            confidence = float(analysis.get('confidence', 0))
        except (ValueError, TypeError):
            confidence = 0.0
        
        if signal not in ['buy', 'sell'] or not stock_code:
            return

        # 交易方向过滤: 0=中性, 1=只买, 2=只卖
        if self.trade_direction == 1 and signal == 'sell':
            self.log(f"当前策略为【多头只买】，忽略卖出信号: {stock_code}", "INFO")
            return
        if self.trade_direction == 2 and signal == 'buy':
            self.log(f"当前策略为【空头只卖】，忽略买入信号: {stock_code}", "INFO")
            return

        if confidence < self.confidence_threshold: # 置信度阈值
            self.log(f"信号置信度不足 ({confidence} < {self.confidence_threshold})，忽略。", "INFO")
            return
            
        # 风险控制与下单量计算
        quantity = self.calculate_order_quantity(stock_code, signal)
        if quantity <= 0:
            self.log("计算下单数量为0，忽略交易。", "WARNING")
            return
            
        # 获取当前价格作为参考（市价单或限价单）
        quote = self.trader.get_stock_quote(stock_code)
        price = quote.get('price', 0)
        pre_close = quote.get('pre_close', 0)
        
        # 风控检查：涨跌幅限制
        if pre_close > 0:
            pct_change = (price - pre_close) / pre_close * 100
            
            # 买入风控：涨幅过高不追
            if signal == 'buy' and self.max_buy_rise is not None:
                if pct_change > self.max_buy_rise:
                    self.log(f"当前涨幅 {pct_change:.2f}% 超过设定上限 {self.max_buy_rise}%，触发【防追高】风控，停止买入。", "WARNING")
                    if self.notify_trade:
                        self.send_trade_notification(
                            f"股票：{stock_code}\n当前涨幅：{pct_change:.2f}%\n限制阈值：{self.max_buy_rise}%\n动作：放弃买入", 
                            analysis,
                            title="🛡️ 触发风控拦截",
                            content_label="风控详情"
                        )
                    return

            # 卖出风控：跌幅过深不卖
            if signal == 'sell' and self.min_sell_fall is not None:
                # 注意：min_sell_fall 通常是负数，例如 -9.0
                if pct_change < self.min_sell_fall:
                    self.log(f"当前跌幅 {pct_change:.2f}% 低于设定下限 {self.min_sell_fall}%，触发【防低吸/防割肉】风控，停止卖出。", "WARNING")
                    if self.notify_trade:
                        self.send_trade_notification(
                            f"股票：{stock_code}\n当前涨幅：{pct_change:.2f}%\n限制阈值：{self.min_sell_fall}%\n动作：放弃卖出", 
                            analysis,
                            title="🛡️ 触发风控拦截",
                            content_label="风控详情"
                        )
                    return

        if price <= 0:
            self.log(f"无法获取股票 {stock_code} 当前价格，跳过。", "ERROR")
            return

        # 执行交易
        success = False
        res = None
        
        if signal == 'buy':
            res = self._safe_buy(stock_code, price, quantity, reason)
            if res:
                success = True
        elif signal == 'sell':
            res = self._safe_sell(stock_code, price, quantity, reason)
            if res:
                success = True
                
        # 通知与日志
        if success:
            if self.notify_trade:
                trade_info = f"股票：{stock_code}\n方向：{'买入' if signal == 'buy' else '卖出 (清仓)'}\n数量：{quantity}\n理由：{reason}"
                
                # 区分模拟和实盘的标题
                title = "✅ 实盘交易执行成功" if self.enable_real_trade else "📢 模拟交易信号触发"
                
                self.send_trade_notification(
                    trade_info, 
                    analysis,
                    title=title,
                    content_label="执行详情"
                )
        else:
            if self.notify_trade:
                trade_info = f"股票：{stock_code}\n方向：{'买入' if signal == 'buy' else '卖出 (清仓)'}\n请检查日志。"
                self.send_trade_notification(
                    trade_info, 
                    analysis,
                    title="❌ 交易执行失败",
                    content_label="错误信息"
                )

    def calculate_order_quantity(self, stock_code, direction):
        """
        计算下单数量，根据 trade_mode 进行不同逻辑处理
        """
        balance = self.trader.get_balance()
        try:
            available_cash = float(balance.get('available_balance', 0) or 0)
        except Exception:
            available_cash = 0.0
        try:
            total_asset = float(balance.get('total_asset', 0) or 0)
        except Exception:
            total_asset = 0.0
        
        quote = self.trader.get_stock_quote(stock_code)
        try:
            price = float(quote.get('price', 0) or 0)
        except Exception:
            price = 0.0
        if price <= 0:
            return 0
        
        quantity = 0
        
        if direction == 'buy':
            target_amount = 0
            
            if self.trade_mode == 'quantity':
                # 按股数
                quantity = self.quantity
                # 资金检查
                if quantity * price > available_cash:
                    quantity = int(available_cash / price / 100) * 100
                    
            elif self.trade_mode == 'ratio':
                asset_base = total_asset if total_asset > 0 else available_cash
                target_amount = min(available_cash, asset_base * self.ratio)
                quantity = int(target_amount / price / 100) * 100
                    
            else: # amount or default
                # 按金额
                target_amount = min(available_cash, self.amount)
                quantity = int(target_amount / price / 100) * 100

        elif direction == 'sell':
            # 获取当前持仓
            position = self.trader.get_position(stock_code)
            try:
                available = int(position.get('available_quantity', 0) or 0) if position else 0
            except Exception:
                available = 0
            
            # 卖出逻辑：根据策略规则，卖出信号触发清仓操作 (忽略 tradeMode 配置)
            # 即使未来支持部分卖出，当前版本明确为风险规避清仓
            quantity = available
            
        return max(0, int(quantity))

    def _safe_buy(self, stock_code, price, quantity, reason):
        """
        安全买入：处理模拟/实盘，并在成功后更新数据
        """
        if not self.enable_real_trade:
            self.log(f"【模拟交易】触发买入：{stock_code}, 价格 {price}, 数量 {quantity}\n原因: {reason}", "WARNING")
            return {"id": "sim_buy", "status": "simulated"}
        
        res = self.trader.buy(stock_code, price, quantity, reason=reason)
        if res:
            self._save_trade_record("buy", stock_code, price, quantity, reason)
            self._update_task_position(stock_code)
        return res

    def _safe_sell(self, stock_code, price, quantity, reason):
        """
        安全卖出：处理模拟/实盘，并在成功后更新数据
        """
        if not self.enable_real_trade:
            self.log(f"【模拟交易】触发卖出：{stock_code}, 价格 {price}, 数量 {quantity}\n原因: {reason}", "WARNING")
            return {"id": "sim_sell", "status": "simulated"}
            
        res = self.trader.sell(stock_code, price, quantity, reason=reason)
        if res:
            self._save_trade_record("sell", stock_code, price, quantity, reason)
            self._update_task_position(stock_code)
        return res

    def _update_task_position(self, stock_code):
        try:
            position = self.trader.get_position(stock_code)
            
            # EventStrategy 可能涉及多个标的，这里更新当前标的的持仓到任务信息中
            # 注意：如果后端接口只支持全量更新 positions，这里可能需要先获取旧的合并，或者后端支持 merge
            # 假设后端直接覆盖 positions，那么对于 EventStrategy 这种多标的，可能需要维护一个内部状态
            # 但为了简单起见，我们先按 Grid 的方式只上报当前标的，或者全量获取（如果 trader 支持）
            # 由于 EventStrategy 可以在多个股票上操作，这里只上报当前操作的股票持仓作为 task 的 positions 列表的一个元素
            # 这可能会覆盖之前的。但通常 EventStrategy 并不像 Grid 那样强绑定一个持仓。
            # 这里的目的是让前端能看到当前持仓。
            
            data = {
                "id": self.data.get('id'),
                "positions": [position] if position else [], 
            }
            
            self._update_trade_task(data)
        except Exception as e:
            self.log(f"更新持仓数据失败: {e}", "WARNING")

    def _update_trade_task(self, data):
        if not self.backend_url or not self.token:
            return

        url = f"{self.backend_url}/quant/tradeTask/updateTradeTask"
            
        headers = {
            "x-token": self.token,
            "Content-Type": "application/json"
        }
        
        try:
            httpx.put(url, json=data, headers=headers, timeout=5)
            # 通知前端刷新交易任务
            # self.log("TRADE_TASK_UPDATE_TRIGGER") # 避免日志刷屏，可选
        except Exception:
            pass

    def _save_trade_record(self, action, stock_code, price, quantity, reason="event_trade"):
        if not self.backend_url or not self.token:
            return

        url = f"{self.backend_url}/quant/tradeRecord/createTradeRecord"
        account = self.data.get('account', {})
        
        # 尝试获取股票名称
        stock_name = stock_code
        try:
             # 尝试从 trader 缓存或持仓中获取 name
             pos = self.trader.get_position(stock_code)
             if pos and pos.get('stock_name'):
                 stock_name = pos.get('stock_name')
        except:
            pass

        data = {
            "member_id": account.get('member_id'),
            "account_id": account.get('id'),
            "task_id": self.data.get('id'),
            "symbol": stock_code,
            "name": stock_name,
            "price": float(price),
            "quantity": float(quantity),
            "amount": float(price) * float(quantity),
            "action": action, 
            "reason": reason,
            "traded_at": time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
        }
        
        headers = {
            "x-token": self.token,
            "Content-Type": "application/json"
        }
        
        try:
            httpx.post(url, json=data, headers=headers, timeout=5)
            # 通知前端刷新交易记录
            # self.log("TRADE_RECORD_UPDATE_TRIGGER")
        except Exception:
            pass

    def send_trade_notification(self, content, analysis, title="📢 财经快讯AI分析报告", content_label="快讯内容"):
        """
        发送飞书通知
        """
        if not self.webhook_url:
            return

        try:
            # 颜色判断
            color = "grey"
            if analysis.get('signal') == 'buy':
                color = "red"
            elif analysis.get('signal') == 'sell':
                color = "green"

            card = {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": color
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "content": f"**{content_label}**：\n{content}",
                            "tag": "lark_md"
                        }
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "div",
                        "fields": [
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**相关标的**：\n{analysis.get('related_stock', '无')}"
                                }
                            },
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**交易信号**：\n{analysis.get('signal', 'none')}"
                                }
                            },
                            {
                                "is_short": True,
                                "text": {
                                    "tag": "lark_md",
                                    "content": f"**置信度**：\n{analysis.get('confidence', 0)}"
                                }
                            }
                        ]
                    },
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**分析理由**：\n{analysis.get('reason', '')}"
                        }
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}"
                            }
                        ]
                    }
                ]
            }

            payload = {
                "msg_type": "interactive",
                "card": card
            }

            resp = httpx.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code != 200:
                self.log(f"飞书通知发送失败: {resp.text}", "WARNING")
                
        except Exception as e:
            self.log(f"飞书通知发送异常: {e}", "WARNING")
