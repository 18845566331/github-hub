"""
workers.py — 后台工作线程
使用 QRunnable + QThreadPool 执行耗时操作，通过信号回调主线程
"""
from PySide6.QtCore import QRunnable, QObject, Signal, Slot


class WorkerSignals(QObject):
    """工作线程信号集合"""
    started = Signal()
    finished = Signal()
    error = Signal(str)          # 错误消息
    progress = Signal(str)       # 进度消息（日志行）
    result = Signal(object)      # 返回结果


def _emit_if_alive(signal, *args):
    try:
        signal.emit(*args)
    except RuntimeError:
        pass


class Worker(QRunnable):
    """通用后台任务执行器"""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        _emit_if_alive(self.signals.started)
        try:
            result = self.fn(*self.args, **self.kwargs)
            _emit_if_alive(self.signals.result, result)
        except Exception as e:
            _emit_if_alive(self.signals.error, str(e))
        finally:
            _emit_if_alive(self.signals.finished)


class ProgressWorker(QRunnable):
    """支持进度回调的后台任务执行器"""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        _emit_if_alive(self.signals.started)
        try:
            # 将 progress_callback 注入到 kwargs
            result = self.fn(
                *self.args,
                progress_callback=lambda message: _emit_if_alive(self.signals.progress, message),
                **self.kwargs
            )
            _emit_if_alive(self.signals.result, result)
        except Exception as e:
            _emit_if_alive(self.signals.error, str(e))
        finally:
            _emit_if_alive(self.signals.finished)
