"""
此模块用于增强 easytrader.grid_strategies.Copy 类的验证码处理能力
需要安装 tesseract 并设置系统环境变量，然后 pip install pytesseract

使用方法：
    import client_patch # 在初始化 et 的 Client 之前导入
    user.grid_strategy = grid_strategies.Copy
"""
import os
import tempfile
from typing import TYPE_CHECKING
from easytrader.log import logger
import pywinauto.keyboard
import pywinauto.clipboard
from easytrader.utils.captcha import captcha_recognize
from easytrader.grid_strategies import Copy

if TYPE_CHECKING:
    from easytrader import clienttrader

def _try_captcha_input(top_win, trader, captcha_path: str = None) -> bool:
    """尝试识别并输入验证码，返回是否成功"""
    if captcha_path is None:
        captcha_path = os.path.join(tempfile.gettempdir(), "easytrader_captcha.png")
    
    try:
        top_win.window(control_id=0x965, class_name="Static").capture_as_image().save(captcha_path)
        captcha_num = "".join(captcha_recognize(captcha_path).split())
        
        if len(captcha_num) != 4:
            logger.warning(f"验证码长度错误: {captcha_num}")
            return False
        
        logger.info(f"识别验证码: {captcha_num}")
        editor = top_win.window(control_id=0x964, class_name="Edit")
        editor.select()
        editor.type_keys(captcha_num + "{ENTER}", with_spaces=True)
        trader.wait(0.5)
        
        try:
            return not trader.app.top_window().window(class_name="Static", title_re="验证码").exists(timeout=0.5)
        except Exception as e:
            logger.warning(f"检查验证码窗口状态异常: {e}")
            return False
    except Exception as e:
        logger.error(f"验证码处理异常: {e}")
        return False


def _handle_captcha(trader, timeout: float = 1.0) -> int:
    """
    处理验证码对话框
    返回: 0: 无验证码 1: 验证码已处理 -1: 处理失败
    """
    top_win = trader.app.top_window()
    if not top_win.window(class_name="Static", title_re="验证码").exists(timeout=timeout):
        return 0
    
    for attempt in range(5):
        if _try_captcha_input(top_win, trader):
            logger.info("验证码验证成功")
            return 1
        
        if attempt < 4:
            try:
                top_win.window(control_id=0x965, class_name="Static").click()
            except Exception as e:
                logger.error(f"刷新验证码失败: {e}")
                break
    
    logger.error("验证码处理失败")
    try:
        top_win.Button2.click()
    except:
        pass
    return -1


def _get_clipboard_with_retry(trader, max_retry: int = 5) -> str:
    """带重试机制的剪贴板数据获取"""
    for i in range(max_retry):
        try:
            data = pywinauto.clipboard.GetData()
            if data:
                return data
        except Exception as e:
            if i < max_retry - 1:
                trader.wait(0.1)
            else:
                logger.error(f"获取剪贴板失败: {e}")
    return ""


def _copy_get_clipboard_data_with_captcha(self: Copy) -> str:
    """增强版剪贴板数据获取，支持验证码处理"""
    # 每次都检查是否有验证码窗口，使用短超时 (0.2s)
    captcha_status = _handle_captcha(self._trader, timeout=0.2)
    
    if captcha_status == -1:
        # 验证码存在但处理失败
        return ""
    
    if captcha_status == 1:
        # 验证码已处理，之前的复制操作可能被中断或失效，需要重新触发复制
        try:
            # 发送 Ctrl+A, Ctrl+C
            self._trader.app.top_window().type_keys("^a^c")
            self._trader.wait(0.1)
        except Exception as e:
            logger.error(f"重新触发复制失败: {e}")

    # 获取剪贴板内容
    data = _get_clipboard_with_retry(self._trader)
    
    # 如果数据为空，可能是在复制过程中验证码弹出来了（极其罕见，但为了健壮性）
    if not data:
        # 再检查一次，稍微长一点的超时
        if _handle_captcha(self._trader, timeout=1.0) == 1:
            # 如果处理了验证码，递归尝试一次
            try:
                self._trader.app.top_window().type_keys("^a^c")
                self._trader.wait(0.1)
                return _get_clipboard_with_retry(self._trader)
            except:
                pass
                
    return data


def _patch_copy_strategy():
    """应用补丁"""
    # 移除 _need_captcha_reg 的依赖，因为它已被弃用
    if hasattr(Copy, '_need_captcha_reg'):
        delattr(Copy, '_need_captcha_reg')

    if not hasattr(Copy, '_get_clipboard_data_original'):
        Copy._get_clipboard_data_original = Copy._get_clipboard_data
        Copy._get_clipboard_data = _copy_get_clipboard_data_with_captcha
        logger.info("已应用 Copy 策略验证码补丁")


_patch_copy_strategy()
