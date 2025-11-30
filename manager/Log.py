# 公共日志模块
# 提供统一的日志回调机制，避免各模块重复定义

# 全局日志回调函数
_LogFunc = None


def SetLogFunc(Func):
    """设置日志函数（由 MainWindow 调用）"""
    global _LogFunc
    _LogFunc = Func


def Log(Msg: str):
    """输出日志"""
    if _LogFunc:
        _LogFunc(Msg)
    else:
        print(Msg)
