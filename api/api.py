#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
Author: Tang Ming
Date: 2025-12-12 17:01:39
LastEditTime: 2025-12-18 20:28:48
Description: 业务层API，供前端JS调用
usage: 在Javascript中调用window.pywebview.api.<methodname>(<parameters>)
'''

from api.storage import Storage
from api.system import System
from api.quant import QuantAPI


class API(System, Storage, QuantAPI):
    '''业务层API，供前端JS调用'''

    def setWindow(self, window):
        '''获取窗口实例'''
        System._window = window
