# -*- coding: utf-8 -*-
import time
import json
import httpx
from ..base import BaseStrategy

class NewsStrategy(BaseStrategy):
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

        self.token = self.data.get('token')
        self.backend_url = self.data.get('backend_url')

        # Keywords
        self.industry_keywords = config.get('industryKeywords', [])
        self.event_keywords = config.get('eventKeywords', [])
       
        # News Source Config
        self.monitor_interval = int(config.get('monitorInterval', 60))
        
        # Notification
        self.enable_feishu = config.get('enableFeishu', False)
        self.feishu_webhook = config.get('feishuWebhook', '')
        
        self.enable_dingtalk = config.get('enableDingTalk', False)
        self.dingtalk_webhook = config.get('dingTalkWebhook', '')
        
        self.enable_wechat = config.get('enableWeChat', False)
        self.wechat_webhook = config.get('weChatWebhook', '')

    def run(self):
        id = self.data.get('id', 0)
        name = self.data.get('name', 'Unknown')
        self.log(f"正在启动事件驱动AI策略任务({id})：{name}...")
        
        self.last_news_id = self.fetch_latest_news_id()
        self.log(f"策略启动完成，开始监控财经快讯...")

        while self.running:
            try:
                # 1. 获取快讯快报
                news_list = self.fetch_news(self.last_news_id)
                
                for news in news_list:
                    self.last_news_id = max(self.last_news_id, news.get('id', 0))
                    content = news.get('content', '')
                    
                    # 2. 关键词过滤
                    if self.contains_keywords(content):
                        self.log(f"发现关注快讯：{content[:50]}...")
                            
                        # 3. 推送消息
                        self.send_notifications(content)
                            
                time.sleep(self.monitor_interval)
                
            except Exception as e:
                self.log(f"策略运行异常：{e}", "ERROR")
                time.sleep(10)

    def fetch_latest_news_id(self):
        """
        获取最新的一条快讯ID，带重试机制
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                params = {'pageSize': 1}
                headers = {
                    'x-token': self.token,
                    'Content-Type': 'application/json'
                }
                url = f'{self.backend_url}/quant/news/getNewsList'
                resp = httpx.get(url, params=params, headers=headers, timeout=10)

                if resp.status_code == 200:
                    data = resp.json()
                    # 简化数据解析逻辑
                    news_list = data.get('data', {}).get('list', [])
                    
                    if news_list and len(news_list) > 0:
                        latest_news = news_list[0]
                        return latest_news.get('id', 0)
                else:
                    self.log(f"获取最新快讯ID失败({attempt+1}/{max_retries}): {resp.status_code}", "WARNING")
                    
            except Exception as e:
                self.log(f"获取最新快讯ID异常({attempt+1}/{max_retries}): {e}", "WARNING")
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                time.sleep(2)
        
        return 0

    def fetch_news(self, last_id):
        """
        获取大于last_id的快讯数据，带重试机制
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                params = {'pageSize': 1, 'last_id': last_id}
                headers = {
                    'x-token': self.token,
                    'Content-Type': 'application/json'
                }
                url = f'{self.backend_url}/quant/news/getNewsList'
                resp = httpx.get(url, params=params, headers=headers, timeout=10)

                if resp.status_code == 200:
                    data = resp.json()
                    # 简化数据解析逻辑
                    news_list = data.get('data', {}).get('list', [])
                    return news_list
                else:
                    self.log(f"获取快讯失败({attempt+1}/{max_retries}): {resp.status_code}", "WARNING")
                    
            except Exception as e:
                self.log(f"获取快讯异常({attempt+1}/{max_retries}): {e}", "WARNING")
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                time.sleep(2)
        
        return []

    def contains_keywords(self, content):
        # 如果都没有配置，直接返回False（避免无过滤全通过）
        if not self.industry_keywords and not self.event_keywords:
            return False

        # 转为小写进行匹配，忽略大小写差异
        content_lower = content.lower()

        # 1. 检查行业关键词 (如果配置了，必须满足其一)
        if self.industry_keywords and not any(k.lower() in content_lower for k in self.industry_keywords):
            return False
        
        # 2. 检查事件关键词 (如果配置了，必须满足其一)
        if self.event_keywords and not any(k.lower() in content_lower for k in self.event_keywords):
            return False
            
        # 如果配置的条件都通过了
        return True

    def send_notifications(self, content):
        """
        发送多渠道通知
        """
        if self.enable_feishu and self.feishu_webhook:
            self.send_feishu(content)
            
        if self.enable_dingtalk and self.dingtalk_webhook:
            self.send_dingtalk(content)
            
        if self.enable_wechat and self.wechat_webhook:
            self.send_wechat(content)

    def send_feishu(self, content):
        """发送飞书通知"""
        try:
            headers = {"Content-Type": "application/json"}
            payload = {
                "msg_type": "text",
                "content": {
                    "text": f"【财经快讯】\n{content}"
                }
            }
            httpx.post(self.feishu_webhook, json=payload, headers=headers, timeout=5)
        except Exception as e:
            self.log(f"飞书通知发送失败: {e}", "WARNING")

    def send_dingtalk(self, content):
        """发送钉钉通知"""
        try:
            headers = {"Content-Type": "application/json"}
            payload = {
                "msgtype": "text",
                "text": {
                    "content": f"【财经快讯】\n{content}"
                }
            }
            httpx.post(self.dingtalk_webhook, json=payload, headers=headers, timeout=5)
        except Exception as e:
            self.log(f"钉钉通知发送失败: {e}", "WARNING")

    def send_wechat(self, content):
        """发送企业微信通知"""
        try:
            headers = {"Content-Type": "application/json"}
            payload = {
                "msgtype": "text",
                "text": {
                    "content": f"【财经快讯】\n{content}"
                }
            }
            httpx.post(self.wechat_webhook, json=payload, headers=headers, timeout=5)
        except Exception as e:
            self.log(f"企业微信通知发送失败: {e}", "WARNING")
