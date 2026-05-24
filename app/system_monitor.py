"""
system_monitor.py — 硬件资源实时监控
包含后台监控线程和精美的仪表盘 Widget
"""
import sys
import psutil
import subprocess
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

class HardwarePoller(QThread):
    """后台硬件轮询线程"""
    stats_updated = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def run(self):
        while self._running:
            stats = {}
            # 1. CPU
            stats["cpu"] = psutil.cpu_percent(interval=1)
            # 2. RAM
            mem = psutil.virtual_memory()
            stats["ram_percent"] = mem.percent
            stats["ram_used"] = mem.used / (1024**3)
            stats["ram_total"] = mem.total / (1024**3)

            # 3. GPU (通过 nvidia-smi)
            try:
                # --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits
                si = None
                if sys.platform == "win32":
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                output = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                    startupinfo=si, text=True, encoding="utf-8", errors="ignore"
                ).strip().split('\n')

                if output and output[0]:
                    parts = [p.strip() for p in output[0].split(',')]
                    if len(parts) == 3:
                        stats["gpu"] = float(parts[0])
                        stats["vram_used"] = float(parts[1]) / 1024  # 转为 GB
                        stats["vram_total"] = float(parts[2]) / 1024
                        stats["vram_percent"] = (stats["vram_used"] / stats["vram_total"]) * 100
                        stats["has_gpu"] = True
            except Exception:
                stats["has_gpu"] = False

            if self._running:
                self.stats_updated.emit(stats)

            # 休眠 1.5 秒
            self.msleep(1500)

    def stop(self):
        self._running = False
        self.wait()


class MinimalProgressBar(QProgressBar):
    def __init__(self, color="#3fb950"):
        super().__init__()
        self.setTextVisible(False)
        self.setFixedHeight(6)
        self.setStyleSheet(f"""
            QProgressBar {{
                background-color: #21262d;
                border-radius: 3px;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 3px;
            }}
        """)


class SystemMonitorWidget(QWidget):
    """主界面顶部仪表盘"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet("background: transparent; color: #8b949e;")
        self._setup_ui()

        self._poller = HardwarePoller()
        self._poller.stats_updated.connect(self._on_stats_updated)
        self._poller.start()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(20)

        # CPU
        self.cpu_layout = QVBoxLayout()
        self.cpu_layout.setSpacing(2)
        self.cpu_label = QLabel("CPU: --%")
        self.cpu_label.setFont(QFont("Consolas", 9))
        self.cpu_bar = MinimalProgressBar("#58a6ff")
        self.cpu_layout.addWidget(self.cpu_label)
        self.cpu_layout.addWidget(self.cpu_bar)
        layout.addLayout(self.cpu_layout)

        # RAM
        self.ram_layout = QVBoxLayout()
        self.ram_layout.setSpacing(2)
        self.ram_label = QLabel("RAM: --/-- GB")
        self.ram_label.setFont(QFont("Consolas", 9))
        self.ram_bar = MinimalProgressBar("#3fb950")
        self.ram_layout.addWidget(self.ram_label)
        self.ram_layout.addWidget(self.ram_bar)
        layout.addLayout(self.ram_layout)

        # GPU
        self.gpu_layout = QVBoxLayout()
        self.gpu_layout.setSpacing(2)
        self.gpu_label = QLabel("GPU VRAM: --/-- GB")
        self.gpu_label.setFont(QFont("Consolas", 9))
        self.gpu_bar = MinimalProgressBar("#f85149")
        self.gpu_layout.addWidget(self.gpu_label)
        self.gpu_layout.addWidget(self.gpu_bar)
        layout.addLayout(self.gpu_layout)

    def _on_stats_updated(self, stats: dict):
        # CPU
        cpu_p = stats.get("cpu", 0)
        self.cpu_label.setText(f"CPU: {cpu_p:.1f}%")
        self.cpu_bar.setValue(int(cpu_p))

        # RAM
        ram_p = stats.get("ram_percent", 0)
        ru = stats.get("ram_used", 0)
        rt = stats.get("ram_total", 0)
        self.ram_label.setText(f"RAM: {ru:.1f}/{rt:.1f} GB")
        self.ram_bar.setValue(int(ram_p))

        # GPU
        if stats.get("has_gpu"):
            vu = stats.get("vram_used", 0)
            vt = stats.get("vram_total", 0)
            vp = stats.get("vram_percent", 0)
            self.gpu_label.setText(f"VRAM: {vu:.1f}/{vt:.1f} GB")
            self.gpu_bar.setValue(int(vp))
            
            # 变色预警
            if vp > 90:
                self.gpu_bar.setStyleSheet(self.gpu_bar.styleSheet().replace("#f85149", "#ff7b72").replace("#3fb950", "#ff7b72"))
            else:
                self.gpu_bar.setStyleSheet(self.gpu_bar.styleSheet().replace("#ff7b72", "#a371f7").replace("#3fb950", "#a371f7"))
        else:
            self.gpu_label.setText("GPU: 无法检测 (无N卡)")
            self.gpu_bar.setValue(0)

    def stop(self):
        self._poller.stop()
