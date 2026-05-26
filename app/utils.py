"""
utils.py — 通用工具函数
集中管理魔法数字、路径处理、翻译等公共功能
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional
import re

# ══════════════════════════════════════════════════════
# 项目目录（动态计算）
# ══════════════════════════════════════════════════════
def get_distribution_dir() -> str:
    """Return the folder containing the executable and optional portable tools."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resource_path(relative_path: str) -> str:
    """Return a path to an application asset in source and bundled modes."""
    base_dir = getattr(sys, "_MEIPASS", get_distribution_dir())
    return os.path.join(base_dir, relative_path)


def get_bundled_runtime_executable(tool: str) -> str:
    """Return a portable runtime executable shipped beside the application."""
    runtimes = os.path.join(get_distribution_dir(), "runtimes")
    candidates = {
        "python": [os.path.join(runtimes, "python", "python.exe")],
        "node": [os.path.join(runtimes, "node", "node.exe")],
        "npm": [os.path.join(runtimes, "node", "npm.cmd")],
        "git": [
            os.path.join(runtimes, "git", "cmd", "git.exe"),
            os.path.join(runtimes, "git", "bin", "git.exe"),
        ],
    }.get(tool, [])
    return next((path for path in candidates if os.path.isfile(path)), "")


def activate_bundled_runtimes() -> dict:
    """Prefer portable Git, Python and Node tools distributed with the app."""
    runtimes = os.path.join(get_distribution_dir(), "runtimes")
    paths = [
        os.path.join(runtimes, "git", "cmd"),
        os.path.join(runtimes, "git", "bin"),
        os.path.join(runtimes, "node"),
        os.path.join(runtimes, "python"),
        os.path.join(runtimes, "python", "Scripts"),
    ]
    existing = [path for path in paths if os.path.isdir(path)]
    current = [part for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    os.environ["PATH"] = os.pathsep.join(existing + [part for part in current if part not in existing])

    python_exe = get_bundled_runtime_executable("python")
    if python_exe:
        os.environ["GITHUB_HUB_PYTHON"] = python_exe
    return {
        "python": python_exe,
        "node": get_bundled_runtime_executable("node"),
        "npm": get_bundled_runtime_executable("npm"),
        "git": get_bundled_runtime_executable("git"),
    }


def get_base_dir() -> str:
    """Return the persistent application data directory."""
    override = os.environ.get("GITHUB_HUB_DATA_DIR", "").strip()
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    if getattr(sys, "frozen", False):
        local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        base_dir = os.path.join(local_appdata, "GitHub Hub")
        os.makedirs(base_dir, exist_ok=True)
        return base_dir
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_default_python_executable() -> str:
    """Return an interpreter that can execute managed Python projects."""
    if not getattr(sys, "frozen", False):
        return sys.executable

    bundled_exe = os.path.realpath(sys.executable)
    candidates = [
        get_bundled_runtime_executable("python"),
        os.environ.get("GITHUB_HUB_PYTHON", "").strip(),
        shutil.which("python"),
        shutil.which("python3"),
    ]
    for candidate in candidates:
        if not candidate or os.path.realpath(candidate) == bundled_exe:
            continue
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return candidate
    return ""

def get_projects_dir(base_dir: str = None) -> str:
    """获取项目存储目录"""
    if base_dir is None:
        base_dir = get_base_dir()
    return os.path.join(base_dir, "projects")

def get_shared_dir(base_dir: str = None) -> str:
    """获取共享包目录"""
    if base_dir is None:
        base_dir = get_base_dir()
    return os.path.join(base_dir, "shared_packages")

def get_pip_cache_dir(base_dir: str = None) -> str:
    """获取 pip 缓存目录"""
    if base_dir is None:
        base_dir = get_base_dir()
    return os.path.join(base_dir, "pip_cache")

def get_logs_dir(base_dir: str = None) -> str:
    """获取日志目录"""
    if base_dir is None:
        base_dir = get_base_dir()
    return os.path.join(base_dir, "logs")

# ══════════════════════════════════════════════════════
# 配置路径
# ══════════════════════════════════════════════════════
def get_config_path(base_dir: str = None) -> str:
    """获取配置文件路径"""
    if base_dir is None:
        base_dir = get_base_dir()
    return os.path.join(base_dir, "config.json")

# ══════════════════════════════════════════════════════
# 翻译规则引擎
# ══════════════════════════════════════════════════════
class TranslationEngine:
    """增强版翻译引擎（规则 + 机器翻译）"""

    # 精确匹配翻译词典
    EXACT_TRANSLATIONS = {
        "open-source": "开源",
        "open source": "开源",
        "framework": "框架",
        "library": "库",
        "tool": "工具",
        "tools": "工具",
        "machine learning": "机器学习",
        "deep learning": "深度学习",
        "web": "网络",
        "interactive": "交互式",
        "educational": "教育",
        "programming": "编程",
        "books": "书籍",
        "assistant": "助手",
        "roadmap": "路线图",
        "guide": "指南",
        "kernel": "内核",
        "algorithms": "算法",
        "api": "接口",
        "cli": "命令行工具",
        "database": "数据库",
        "server": "服务器",
        "client": "客户端",
        "desktop": "桌面应用",
        "mobile": "移动端",
        "frontend": "前端",
        "backend": "后端",
        "full-stack": "全栈",
        "DevOps": "运维开发",
        "cloud": "云",
        "container": "容器",
        "kubernetes": "K8s",
        "docker": "容器化",
        "microservice": "微服务",
        "distributed": "分布式",
        "real-time": "实时",
        "cross-platform": "跨平台",
        "lightweight": "轻量级",
        "high-performance": "高性能",
        "easy to use": "易于使用",
        "easy-to-use": "易于使用",
        "production-ready": "生产就绪",
        "battle-tested": "经过实战检验",
        "extensible": "可扩展",
        "configurable": "可配置",
        "modular": "模块化",
        "self-hosted": "自托管",
        "selfhosted": "自托管",
        "monitoring": "监控",
        "analytics": "分析",
        "visualization": "可视化",
        "dashboard": "仪表盘",
        "automation": "自动化",
        "script": "脚本",
        "plugin": "插件",
        "extension": "扩展",
        "template": "模板",
        "boilerplate": "样板代码",
    }

    # 正则替换规则（用于词形变化）
    PATTERN_TRANSLATIONS = [
        # 开源相关
        (r'\bopen[\s-]?source\b', '开源'),
        (r'\bopensource\b', '开源'),
        # 机器学习相关
        (r'\bmachine[\s-]?learning\b', '机器学习'),
        (r'\bdeep[\s-]?learning\b', '深度学习'),
        (r'\bneural[\s-]?network\b', '神经网络'),
        (r'\bllm\b', '大语言模型'),
        (r'\bgpt\b', 'GPT'),
        (r'\btransformer\b', 'Transformer'),
        # Web 相关
        (r'\bweb[\s-]?app\b', 'Web应用'),
        (r'\bapi\b', 'API'),
        (r'\brest[\s-]?api\b', 'REST接口'),
        (r'\bfrontend\b', '前端'),
        (r'\bback-end\b', '后端'),
        (r'\bback end\b', '后端'),
        # 开发工具
        (r'\bcli\b', '命令行工具'),
        (r'\bgui\b', '图形界面'),
        (r'\bsdk\b', '开发包'),
        (r'\bide\b', 'IDE'),
        # 项目类型
        (r'\bchatbot\b', '聊天机器人'),
        (r'\bbot\b', '机器人'),
        (r'\bagent\b', '智能体'),
        # 特性词
        (r'\beasy[\s-]?to[\s-]?use\b', '易于使用'),
        (r'\bcross[\s-]?platform\b', '跨平台'),
        (r'\bhigh[\s-]?performance\b', '高性能'),
        (r'\bproduction[\s-]?ready\b', '生产就绪'),
    ]

    @classmethod
    def translate(cls, text: str) -> str:
        """翻译文本"""
        if not text:
            return ""

        result = text

        # 1. 精确匹配替换
        for en, cn in cls.EXACT_TRANSLATIONS.items():
            result = re.sub(r'\b' + re.escape(en) + r'\b', cn, result, flags=re.IGNORECASE)

        # 2. 正则模式替换
        for pattern, replacement in cls.PATTERN_TRANSLATIONS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        # 3. 清理多余的空格
        result = re.sub(r'\s+', ' ', result)

        return result.strip()

    @classmethod
    def translate_description(cls, desc: str, max_length: int = 100) -> str:
        """翻译项目描述（带长度限制）"""
        if not desc:
            return ""

        translated = cls.translate(desc)

        # 截断处理
        if len(translated) > max_length:
            # 在空格处截断
            truncated = translated[:max_length]
            last_space = truncated.rfind(' ')
            if last_space > max_length * 0.7:  # 如果在70%位置内有空格
                truncated = truncated[:last_space]
            translated = truncated + "..."

        return translated


# ══════════════════════════════════════════════════════
# GitHub API 配置常量
# ══════════════════════════════════════════════════════
class GitHubAPIConfig:
    """GitHub API 配置"""
    # API 限流配置
    UNAUTH_RATE_LIMIT = 60        # 未认证每小时请求数
    AUTH_RATE_LIMIT = 5000         # 认证每小时请求数

    # 请求超时（秒）
    REQUEST_TIMEOUT = 15

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 2                # 基础重试延迟（秒）
    RETRY_BACKOFF = 2             # 指数退避因子

    # 缓存配置
    TRENDING_CACHE_DURATION = 600  # 热门项目缓存时间（秒）
    SEARCH_CACHE_DURATION = 300   # 搜索结果缓存时间（秒）


# ══════════════════════════════════════════════════════
# 热门项目时间范围配置
# ══════════════════════════════════════════════════════
TRENDING_CONFIG = {
    "daily": {"days": 3, "min_stars": 10},
    "weekly": {"days": 7, "min_stars": 50},
    "monthly": {"days": 30, "min_stars": 100},
}


# ══════════════════════════════════════════════════════
# 日志工具
# ══════════════════════════════════════════════════════
import logging
import json
from datetime import datetime

def setup_logger(name: str, log_dir: str = None) -> logging.Logger:
    """设置日志记录器"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # 文件处理器
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, f"{name}_{datetime.now():%Y%m%d}.log")
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

    return logger


# ══════════════════════════════════════════════════════
# 安全工具
# ══════════════════════════════════════════════════════
def sanitize_path(path: str) -> str:
    """清理路径，防止路径遍历攻击"""
    if not path:
        return ""

    # 移除潜在的路径遍历字符序列
    path = path.replace('..', '')
    path = path.replace('//', '/')

    # 确保路径是绝对路径
    if not os.path.isabs(path):
        return os.path.abspath(path)

    return path


def escape_shell_arg(arg: str) -> str:
    """转义 shell 参数（防止命令注入）"""
    if not arg:
        return ""

    # Windows 特殊处理
    if os.name == 'nt':
        if '"' in arg:
            arg = arg.replace('"', '\\"')
        return f'"{arg}"'
    else:
        # Unix 系统
        return "'" + arg.replace("'", "'\\''") + "'"


# ══════════════════════════════════════════════════════
# 字符串工具
# ══════════════════════════════════════════════════════
def format_stars(stars: int) -> str:
    """格式化星星数量"""
    if stars >= 1_000_000:
        return f"{stars / 1_000_000:.1f}M"
    elif stars >= 1_000:
        return f"{stars / 1_000:.1f}k"
    else:
        return str(stars)


def truncate_text(text: str, max_length: int, ellipsis: str = "...") -> str:
    """截断文本并在末尾添加省略号"""
    if not text or len(text) <= max_length:
        return text

    truncated = text[:max_length - len(ellipsis)]
    last_space = truncated.rfind(' ')

    if last_space > max_length * 0.6:
        truncated = truncated[:last_space]

    return truncated + ellipsis


print("utils.py loaded - common utilities available")
