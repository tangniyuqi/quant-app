#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Author: Tang Ming
Date: 2025-12-01 09:20:45
LastEditTime: 2025-12-15 21:27:30
Description: 生成客户端主程序
'''
import os
import argparse
import mimetypes
import logging
import webview
from api.api import API
from pyapp.config.config import Config
from pyapp.db.db import DB

# 关闭 pywebview 的日志
logger = logging.getLogger('pywebview')
logger.setLevel(logging.ERROR)  # 仅保留错误级日志

cfg = Config()    # 配置
db = DB()    # 数据库类
api = API()    # 本地接口

cfg.init()


def on_shown():
    # print('程序启动')
    db.init()    # 初始化数据库


def on_loaded():
    # print('DOM加载完毕')
    pass


def on_closing():
    # print('程序关闭')
    pass


def WebViewApp(ifDev=False, ifCef=False):

    # 是否为开发环境
    Config.devEnv = ifDev

    # 视图层页面URL
    if Config.devEnv:
        # 开发环境
        MAIN_DIR = f'http://localhost:{Config.devPort}/'
        template = os.path.join(MAIN_DIR, "#/quant")    # 设置页面，指向本地
    else:
        # 生产环境
        # MAIN_DIR = os.path.join(".", "web")
        # template = os.path.join(MAIN_DIR, "index.html")    # 设置页面，指向本地
        MAIN_DIR = f'https://go.noooya.com/'
        template = os.path.join(MAIN_DIR, "#/quant")    # 设置页面，指向远程

        # 修复某些情况下，打包后软件打开白屏的问题
        mimetypes.add_type('application/javascript', '.js')

    # 系统分辨率
    screens = webview.screens
    screens = screens[0]
    width = screens.width
    height = screens.height
    # 程序窗口大小
    initWidth = int(width * 2 / 2)
    initHeight = int(height * 4 / 4)
    minWidth = int(initWidth / 2)
    minHeight = int(initHeight / 2)

    # 创建窗口
    window = webview.create_window(title=Config.appName, url=template, js_api=api, width=initWidth, height=initHeight, min_size=(minWidth, minHeight))

    # 获取窗口实例
    api.setWindow(window)

    # 绑定事件
    window.events.shown += on_shown
    window.events.loaded += on_loaded
    window.events.closing += on_closing

    # CEF模式
    guiCEF = 'cef' if ifCef else None

    # 启动窗口
    webview.start(debug=Config.devEnv, http_server=True, gui=guiCEF)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--dev", action="store_true", dest="if_dev", help="if_dev")
    parser.add_argument("-c", "--cef", action="store_true", dest="if_cef", help="if_cef")
    args = parser.parse_args()

    ifDev = args.if_dev    # 是否开启开发环境
    ifCef = args.if_cef    # 是否开启cef模式

    WebViewApp(ifDev, ifCef)
