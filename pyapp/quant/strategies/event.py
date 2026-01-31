# -*- coding: utf-8 -*-
import time
import json
import httpx
import threading
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
        self.ai_url = server.get('ai_url', 'https://api.deepseek.com/v1/chat/completions')

        # Keywords
        self.industry_keywords = config.get('industryKeywords', [])
        self.event_keywords = config.get('eventKeywords', [])
       
        # News Source Config
        self.monitor_interval = int(config.get('monitorInterval', 60))
        
        # Risk Control
        self.max_single_order_amount = float(config.get('maxSingleOrderAmount', 100000))
        self.max_position_ratio = float(config.get('maxPositionRatio', 0.5))
        
        # Notification
        self.webhook_url = server.get('webhook_url', '')
        self.notify_analysis = config.get('notifyAnalysis', True)
        self.notify_trade = config.get('notifyTrade', True)
        
        # Deep Thinking
        self.enable_deep_thinking = config.get('enableDeepThinking', False)
        
        # Trading Config
        self.enable_real_trade = config.get('enableRealTrade', False)

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
                                self.send_notification(content, analysis_result)
                            
                            # 4. 生成并执行交易信号
                            self.process_signal(analysis_result)
                            
                time.sleep(self.monitor_interval)
                
            except Exception as e:
                self.log(f"任务({id})：策略运行异常：{e}", "ERROR")
                time.sleep(10)

    def fetch_latest_news_id(self):
        """
        获取最新的一条快讯ID
        """
        try:
            params = {
                'pageSize': 1
            }

            headers = {
                'x-token': self.token,
                'Content-Type': 'application/json'
            }

            url = f'{self.backend_url}/quant/news/getNewsList'
            resp = httpx.get(url, params=params, headers=headers, timeout=10)


            if resp.status_code == 200:
                data = resp.json()
                news_list = []
                
                if isinstance(data, dict):
                    if 'data' in data:
                        inner_data = data['data']
                        if isinstance(inner_data, dict) and 'list' in inner_data:
                            news_list = inner_data['list']
                
                if news_list and len(news_list) > 0:
                    latest_news = news_list[0]
                    return latest_news.get('id', 0)
            else:
                self.log(f"获取最新快讯ID失败: {resp.status_code}", "WARNING")
        except Exception as e:
            self.log(f"获取最新快讯ID异常: {e}", "WARNING")
        
        return 0

    def fetch_news(self, last_id):
        """
        获取大于last_id的快讯数据
        """
        try:
            params = {
                'pageSize': 1,
                'last_id': last_id
            }

            headers = {
                'x-token': self.token,
                'Content-Type': 'application/json'
            }

            url = f'{self.backend_url}/quant/news/getNewsList?pageSize=1'
            resp = httpx.get(url, params=params, headers=headers, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                news_list = []
                
                if isinstance(data, dict):
                    if 'data' in data:
                        inner_data = data['data']
                        if isinstance(inner_data, dict) and 'list' in inner_data:
                            news_list = inner_data['list']

                return news_list
            else:
                self.log(f"获取快讯失败: {resp.status_code}", "WARNING")
        except Exception as e:
            self.log(f"获取快讯异常: {e}", "WARNING")
        
        return []

    def contains_keywords(self, content):
        # 如果都没有配置，直接返回False（避免无过滤全通过）
        if not self.industry_keywords and not self.event_keywords:
            return False

        # 1. 检查行业关键词 (如果配置了)
        if self.industry_keywords:
            has_industry = False
            for k in self.industry_keywords:
                if k in content:
                    has_industry = True
                    break
            if not has_industry:
                return False
        
        # 2. 检查事件关键词 (如果配置了)
        if self.event_keywords:
            has_event = False
            for k in self.event_keywords:
                if k in content:
                    has_event = True
                    break
            if not has_event:
                return False
            
        # 如果配置的关键词都满足了 (或者某一种没配置直接跳过了)
        return True

    def analyze_news_with_ai(self, content):
        """
        调用AI接口进行分析
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.ai_key}"
        }
        
        is_doubao = "doubao" in self.ai_model
        
        deep_thinking_instruction = ""
        if self.enable_deep_thinking:
            deep_thinking_instruction = "\n请进行深度思考，全面分析市场背景、潜在影响链条以及市场情绪，给出详尽的分析理由。"
        
        if is_doubao:
            # 豆包模型使用结构化输出，提示词不需要强调JSON格式
            prompt = f"""
            请分析以下财经快讯内容，判断是否对相关行业或个股构成重大利好或利空，并生成交易信号。{deep_thinking_instruction}
            
            快讯内容：{content}
            
            关注行业关键词：{', '.join(self.industry_keywords)}
            关注事件关键词：{', '.join(self.event_keywords)}
            """
            
            system_prompt = "你是一个专业的量化交易助手，擅长从快讯中分析交易机会。"
            
            json_schema = {
                "type": "object",
                "properties": {
                    "related_stock": {
                        "type": "string",
                        "description": "相关股票代码（如 600519，如果没有明确个股则留空）"
                    },
                    "signal": {
                        "type": "string",
                        "enum": ["buy", "sell", "none"],
                        "description": "信号类型"
                    },
                    "reason": {
                        "type": "string",
                        "description": "分析理由"
                    },
                    "confidence": {
                        "type": "number",
                        "description": "置信度 (0-1)"
                    }
                },
                "required": ["related_stock", "signal", "reason", "confidence"],
                "additionalProperties": False
            }
            
            payload = {
                "model": self.ai_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "quant_analysis",
                        "schema": json_schema,
                        "strict": True
                    }
                },
                "temperature": 0.1
            }
        else:
            # DeepSeek等其他模型继续使用Prompt工程方式
            prompt = f"""
            请分析以下财经快讯内容，判断是否对相关行业或个股构成重大利好或利空，并生成交易信号。{deep_thinking_instruction}
            
            快讯内容：{content}
            
            关注行业关键词：{', '.join(self.industry_keywords)}
            关注事件关键词：{', '.join(self.event_keywords)}
            
            请返回JSON格式结果，包含以下字段：
            - related_stock: 相关股票代码（如 600519，如果没有明确个股则留空）
            - signal: 信号类型 (buy/sell/none)
            - reason: 分析理由
            - confidence: 置信度 (0-1)
            """
            
            payload = {
                "model": self.ai_model,
                "messages": [
                    {"role": "system", "content": "你是一个专业的量化交易助手，擅长从快讯中分析交易机会。请只返回JSON格式的回答。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1
            }
        
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
                result = resp.json()
                # 解析AI返回的内容
                ai_content = result['choices'][0]['message']['content']
                
                # 如果是结构化输出，内容本身就是JSON字符串
                if is_doubao:
                    try:
                        return json.loads(ai_content)
                    except Exception as e:
                        self.log(f"解析结构化输出失败: {e}\n响应内容: {ai_content}", "ERROR")
                        return None
                
                # 尝试提取JSON (兼容普通模式)
                try:
                    # 简单的JSON提取逻辑，防止AI返回Markdown代码块
                    json_str = ai_content
                    if "```json" in ai_content:
                        json_str = ai_content.split("```json")[1].split("```")[0]
                    elif "```" in ai_content:
                        json_str = ai_content.split("```")[1].split("```")[0]
                    
                    return json.loads(json_str.strip())
                except Exception as e:
                    self.log(f"解析AI响应JSON失败: {e}\n响应内容: {ai_content}", "ERROR")
            else:
                self.log(f"AI API调用失败: {resp.status_code} {resp.text}", "ERROR")
        except Exception as e:
            self.log(f"AI分析异常: {e}", "ERROR")
            
        return None

    def process_signal(self, analysis):
        signal = analysis.get('signal')
        stock_code = analysis.get('related_stock')
        reason = analysis.get('reason')
        confidence = analysis.get('confidence', 0)
        
        if signal not in ['buy', 'sell'] or not stock_code:
            return

        if confidence < 0.7: # 置信度阈值
            self.log(f"信号置信度不足 ({confidence})，忽略。", "INFO")
            return
            
        # 风险控制与下单量计算
        quantity = self.calculate_order_quantity(stock_code, signal)
        if quantity <= 0:
            self.log("计算下单数量为0，忽略交易。", "WARNING")
            return
            
        # 获取当前价格作为参考（市价单或限价单）
        quote = self.trader.get_stock_quote(stock_code)
        price = quote.get('price', 0)
        if price <= 0:
            self.log(f"无法获取股票 {stock_code} 当前价格，跳过。", "ERROR")
            return

        # 执行交易
        success = False
        msg = ""
        
        if not self.enable_real_trade:
             self.log(f"模拟交易信号：{signal} {stock_code} 数量：{quantity} 参考价：{price} 理由：{reason}", "INFO")
             # 模拟交易也发送通知，但注明是模拟
             if self.notify_trade:
                 self.send_trade_notification(f"【模拟交易信号】\n股票：{stock_code}\n方向：{signal}\n数量：{quantity}\n理由：{reason}", analysis)
             return

        if signal == 'buy':
            self.log(f"执行买入：{stock_code} 数量：{quantity} 参考价：{price}")
            res = self.trader.buy(stock_code, price, quantity, reason=reason)
            if res:
                success = True
                msg = f"买入指令已发送：{stock_code} {quantity}股"
        elif signal == 'sell':
            self.log(f"执行卖出：{stock_code} 数量：{quantity} 参考价：{price}")
            res = self.trader.sell(stock_code, price, quantity, reason=reason)
            if res:
                success = True
                msg = f"卖出指令已发送：{stock_code} {quantity}股"
                
        # 通知与日志
        if success:
            if self.notify_trade:
                self.send_trade_notification(f"【实盘交易执行成功】\n股票：{stock_code}\n方向：{signal}\n数量：{quantity}\n理由：{reason}", analysis)
        else:
            if self.notify_trade:
                self.send_trade_notification(f"【实盘交易执行失败】\n股票：{stock_code}\n方向：{signal}\n请检查日志。", analysis)

    def calculate_order_quantity(self, stock_code, direction):
        """
        计算下单数量，包含风险控制
        """
        balance = self.trader.get_balance()
        available_cash = balance.get('available_balance', 0)
        total_asset = balance.get('total_asset', 0)
        
        quote = self.trader.get_stock_quote(stock_code)
        price = quote.get('price', 0)
        if price <= 0: return 0
        
        quantity = 0
        
        if direction == 'buy':
            # 1. 单笔金额限制
            amount_by_limit = self.max_single_order_amount
            
            # 2. 总仓位限制 (简化计算，假设当前买入后不超过比例)
            # 当前持仓市值 + 拟买入金额 <= 总资产 * max_ratio
            # 注意：这里的total_asset包含了现金。
            # 实际上应该是：当前已用资金 + 拟买入 <= 总资产 * max_ratio
            # 粗略估算：可用资金足够，且不超过单笔限额
            
            target_amount = min(available_cash, amount_by_limit)
            
            # 仓位限制检查
            # if (total_asset - available_cash + target_amount) / total_asset > self.max_position_ratio:
            #     target_amount = total_asset * self.max_position_ratio - (total_asset - available_cash)
            
            if target_amount <= 0: return 0
            
            quantity = int(target_amount / price / 100) * 100 # 向下取整到100股
            
        elif direction == 'sell':
            # 获取当前持仓
            position = self.trader.get_position(stock_code)
            available = position.get('available_quantity', 0)
            
            # 卖出逻辑：假设全部卖出或按比例，这里简单处理为卖出可用的一半或者全部，暂定全部
            quantity = available
            
        return quantity

    def send_notification(self, content):
        if not self.webhook_url:
            return
            
        try:
            headers = {"Content-Type": "application/json"}
            payload = {
                "msg_type": "text",
                "content": {
                    "text": f"【EventAI】\n{content}"
                }
            }
            httpx.post(self.webhook_url, json=payload, headers=headers, timeout=5)
        except Exception as e:
            self.log(f"通知发送失败: {e}", "WARNING")

    def send_trade_notification(self, content, analysis):
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
                        "content": "📢 财经快讯AI分析报告"
                    },
                    "template": color
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "content": f"**快讯内容**：\n{content}",
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
