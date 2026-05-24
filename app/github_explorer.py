"""
github_explorer.py — GitHub 项目探索模块
提供热门项目、中文搜索、分类浏览功能
支持 API 限流处理、指数退避重试、缓存机制
"""
import os
import json
import time
import re
import logging
import urllib.parse
from typing import Optional, List, Dict, Callable, Tuple
from dataclasses import dataclass, field
from datetime import date, timedelta

from .utils import (
    TranslationEngine, GitHubAPIConfig, TRENDING_CONFIG,
    get_base_dir, get_config_path, setup_logger
)

NL = chr(10)

# ══════════════════════════════════════════════════════
# 日志记录器
# ══════════════════════════════════════════════════════
logger = setup_logger("github_explorer", os.path.join(get_base_dir(), "logs"))


# ── 语言分类 ──────────────────────────────────────────────
CATEGORIES = {
    "全部": {"label": "全部项目", "languages": []},
    "AI/机器学习": {"label": "AI/机器学习", "languages": ["Python", "Jupyter Notebook", "C++"]},
    "Web 前端": {"label": "Web 前端", "languages": ["JavaScript", "TypeScript", "HTML", "CSS", "Svelte", "Vue", "Solid"]},
    "Web 后端": {"label": "Web 后端", "languages": ["Python", "Go", "Rust", "Java", "C#", "Ruby", "PHP", "Kotlin"]},
    "系统工具": {"label": "系统工具", "languages": ["Rust", "C", "C++", "Go", "Zig"]},
    "数据科学": {"label": "数据科学", "languages": ["Python", "R", "Jupyter Notebook", "Julia"]},
    "移动开发": {"label": "移动开发", "languages": ["Kotlin", "Swift", "Dart", "Java"]},
    "DevOps/云原生": {"label": "DevOps/云原生", "languages": ["Go", "Python", "Rust", "HCL", "Shell"]},
    "游戏开发": {"label": "游戏开发", "languages": ["C++", "C#", "Lua", "Rust", "Python"]},
    "区块链": {"label": "区块链", "languages": ["Solidity", "Rust", "Go", "Python", "TypeScript"]},
    "其他": {"label": "其他", "languages": ["Shell", "PowerShell", "Lua", "Perl", "Haskell", "Scala", "Elixir", "Zig", "Nim"]},
}

# 手动维护的语言→分类映射（处理多分类语言如 Python 取其最相关的分类）
LANGUAGE_CATEGORY_MAP = {
    "python": "AI/机器学习",
    "jupyter notebook": "数据科学",
    "c++": "系统工具",
    "javascript": "Web 前端",
    "typescript": "Web 前端",
    "html": "Web 前端",
    "css": "Web 前端",
    "svelte": "Web 前端",
    "vue": "Web 前端",
    "solid": "Web 前端",
    "go": "Web 后端",
    "rust": "系统工具",
    "java": "Web 后端",
    "c#": "Web 后端",
    "ruby": "Web 后端",
    "php": "Web 后端",
    "kotlin": "移动开发",
    "swift": "移动开发",
    "dart": "移动开发",
    "r": "数据科学",
    "julia": "数据科学",
    "shell": "DevOps/云原生",
    "hcl": "DevOps/云原生",
    "lua": "游戏开发",
    "solidity": "区块链",
    "c": "系统工具",
    "zig": "系统工具",
    "nim": "其他",
    "perl": "其他",
    "haskell": "其他",
    "scala": "其他",
    "elixir": "其他",
    "powershell": "其他",
}


def get_category_for_language(lang: str) -> str:
    """根据语言返回分类名称"""
    if not lang:
        return "其他"
    return LANGUAGE_CATEGORY_MAP.get(lang.lower(), "其他")


# ── 数据模型 ──────────────────────────────────────────────

@dataclass
class TrendingProject:
    """热门项目数据模型"""
    name: str = ""
    full_name: str = ""
    description: str = ""
    url: str = ""
    stars: int = 0
    forks: int = 0
    language: str = ""
    language_color: str = ""
    today_stars: int = 0
    owner: str = ""
    owner_avatar: str = ""
    topics: List[str] = field(default_factory=list)
    category: str = ""


@dataclass
class SearchResult:
    """搜索结果数据模型"""
    total_count: int = 0
    items: List[TrendingProject] = field(default_factory=list)
    page: int = 1
    has_more: bool = False


# ── API 限流处理 ───────────────────────────────────────────

class RateLimitHandler:
    """GitHub API 限流处理器"""

    def __init__(self):
        self._remaining: int = GitHubAPIConfig.UNAUTH_RATE_LIMIT
        self._reset_time: float = 0
        self._retry_after: int = 60

    def update_from_headers(self, headers: dict):
        """从响应头更新限流信息"""
        # GitHub API v3 响应头
        self._remaining = int(headers.get("X-RateLimit-Remaining", GitHubAPIConfig.UNAUTH_RATE_LIMIT))
        reset_timestamp = int(headers.get("X-RateLimit-Reset", 0))
        if reset_timestamp > 0:
            self._reset_time = reset_timestamp

    def get_retry_delay(self) -> int:
        """计算需要等待的秒数"""
        if self._remaining <= 0:
            current_time = time.time()
            if self._reset_time > current_time:
                return int(self._reset_time - current_time) + 1
        return 0

    def should_retry(self) -> bool:
        """是否应该等待重试"""
        return self._remaining <= 0


# 全局限流处理器实例
_rate_limit_handler = RateLimitHandler()


# ── HTTP 请求封装（带重试机制）─────────────────────────────

def _make_github_request(
    url: str,
    headers: dict,
    progress_callback: Callable = None,
    max_retries: int = None
) -> Tuple[dict, bool]:
    """
    发送 GitHub API 请求，支持指数退避重试

    Returns:
        (data, success) - 返回数据和是否成功
    """
    import urllib.request
    import urllib.error

    if max_retries is None:
        max_retries = GitHubAPIConfig.MAX_RETRIES

    last_error = None

    for attempt in range(max_retries):
        try:
            # 检查是否需要等待限流
            retry_delay = _rate_limit_handler.get_retry_delay()
            if retry_delay > 0:
                wait_msg = f"[WARN] API 限流中，等待 {retry_delay} 秒..."
                if progress_callback:
                    progress_callback(wait_msg)
                logger.warning(wait_msg)
                time.sleep(retry_delay)

            # 发送请求
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(
                req,
                timeout=GitHubAPIConfig.REQUEST_TIMEOUT
            ) as resp:
                # 更新限流信息
                _rate_limit_handler.update_from_headers(resp.headers)

                data = json.loads(resp.read().decode("utf-8"))
                return data, True

        except urllib.error.HTTPError as e:
            last_error = e
            error_msg = f"[ERROR] HTTP {e.code}: {e.reason}"

            # 处理 403 限流
            if e.code == 403:
                # 尝试从响应头获取限流信息
                if hasattr(e, 'headers'):
                    _rate_limit_handler.update_from_headers(e.headers)

                # 检查是否是 "rate limit exceeded"
                try:
                    error_body = json.loads(e.read().decode("utf-8"))
                    if "rate limit" in error_body.get("message", "").lower():
                        retry_delay = _rate_limit_handler.get_retry_delay()
                        if retry_delay > 0:
                            if progress_callback:
                                progress_callback(f"[WARN] API 限流已触发，等待 {retry_delay} 秒后重试...")
                            time.sleep(retry_delay)
                            continue
                except:
                    pass

                # 其他 403 错误，指数退避
                delay = GitHubAPIConfig.RETRY_DELAY * (GitHubAPIConfig.RETRY_BACKOFF ** attempt)
                if progress_callback:
                    progress_callback(f"[WARN] 请求失败，{delay:.1f} 秒后重试... (尝试 {attempt + 1}/{max_retries})")
                time.sleep(delay)

            # 处理 422 无效请求
            elif e.code == 422:
                if progress_callback:
                    progress_callback("[ERROR] 无效的搜索请求，请检查参数")
                return {}, False

            # 处理 502/503 服务端错误
            elif e.code in (502, 503, 504):
                delay = GitHubAPIConfig.RETRY_DELAY * (GitHubAPIConfig.RETRY_BACKOFF ** attempt)
                if progress_callback:
                    progress_callback(f"[WARN] 服务器错误 ({e.code})，{delay:.1f} 秒后重试...")
                time.sleep(delay)

            else:
                if progress_callback:
                    progress_callback(f"[ERROR] HTTP 错误: {e.code} {e.reason}")
                return {}, False

        except urllib.error.URLError as e:
            last_error = e
            delay = GitHubAPIConfig.RETRY_DELAY * (GitHubAPIConfig.RETRY_BACKOFF ** attempt)
            if progress_callback:
                progress_callback(f"[WARN] 网络错误: {e.reason}，{delay:.1f} 秒后重试...")
            time.sleep(delay)

        except Exception as e:
            last_error = e
            if progress_callback:
                progress_callback(f"[ERROR] 请求异常: {e}")
            logger.exception("GitHub API 请求失败")
            break

    # 所有重试都失败
    if last_error:
        if progress_callback:
            progress_callback(f"[ERROR] 请求失败，已尝试 {max_retries} 次: {last_error}")
        logger.error(f"GitHub API 请求失败，已尝试 {max_retries} 次: {last_error}")

    return {}, False


# ── 热门项目抓取 ───────────────────────────────────────────

TRENDING_URL = "https://api.github.com/search/repositories"


def _build_github_headers(token: str = "") -> dict:
    """构建 GitHub API 请求头"""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GitHubHub/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_cache_key(since: str, language: str) -> str:
    """获取缓存键"""
    return f"trend_{since}_{language}"


def fetch_trending(
    since: str = "daily",
    language: str = "",
    token: str = "",
    progress_callback: Callable = None
) -> List[TrendingProject]:
    """
    获取热门项目列表

    Args:
        since: 时间范围 ("daily", "weekly", "monthly")
        language: 编程语言过滤
        token: GitHub Token
        progress_callback: 进度回调函数

    Returns:
        TrendingProject 列表
    """
    # 检查缓存
    cache_key = _get_cache_key(since, language)
    now = time.time()

    # 使用模块级缓存
    if not hasattr(fetch_trending, "_cache"):
        fetch_trending._cache = {}

    if cache_key in fetch_trending._cache:
        cached = fetch_trending._cache[cache_key]
        if now - cached["timestamp"] < GitHubAPIConfig.TRENDING_CACHE_DURATION:
            if progress_callback:
                progress_callback("[INFO] 使用缓存数据")
            return cached["data"]

    # 显示加载状态
    if progress_callback:
        progress_callback("[INFO] 正在获取热门项目...")

    # 获取配置
    config = TRENDING_CONFIG.get(since, TRENDING_CONFIG["weekly"])
    day_offset = config["days"]
    star_min = config["min_stars"]

    # 构建查询
    today = date.today()
    pushed = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d")

    q_parts = [f"pushed:>{pushed}", f"stars:>{star_min}"]
    if language:
        q_parts.append(f"language:{language}")

    params = urllib.parse.urlencode({
        "q": " ".join(q_parts),
        "sort": "stars",
        "order": "desc",
        "per_page": 30
    })
    url = f"{TRENDING_URL}?{params}"
    headers = _build_github_headers(token)

    # 发送请求
    data, success = _make_github_request(url, headers, progress_callback)

    if not success or not data:
        # 尝试返回缓存数据（即使过期）
        if cache_key in fetch_trending._cache:
            if progress_callback:
                progress_callback("[INFO] 使用过期缓存数据")
            return fetch_trending._cache[cache_key]["data"]
        return []

    # 解析结果
    results = _parse_search_results(data)

    # 如果结果太少，尝试扩大搜索范围
    if len(results) < 5:
        if progress_callback:
            progress_callback("[INFO] 结果较少，扩大搜索范围...")

        wider = (today - timedelta(days=day_offset * 2)).strftime("%Y-%m-%d")
        ws = max(5, star_min // 2)
        q2 = [f"pushed:>{wider}", f"stars:>{ws}"]
        if language:
            q2.append(f"language:{language}")

        p2 = urllib.parse.urlencode({
            "q": " ".join(q2),
            "sort": "stars",
            "order": "desc",
            "per_page": 30
        })
        u2 = f"{TRENDING_URL}?{p2}"

        data2, _ = _make_github_request(u2, headers, progress_callback)
        if data2 and len(data2.get("items", [])) > len(results):
            results = _parse_search_results(data2)

    # 更新缓存
    fetch_trending._cache[cache_key] = {
        "data": results,
        "timestamp": now
    }

    if progress_callback:
        progress_callback(f"[SUCCESS] 获取到 {len(results)} 个项目")

    return results


def search_repos(
    query: str,
    language: str = "",
    sort: str = "stars",
    order: str = "desc",
    page: int = 1,
    per_page: int = 20,
    token: str = "",
    progress_callback: Callable = None,
) -> SearchResult:
    """
    搜索 GitHub 仓库

    Args:
        query: 搜索关键词（支持中文）
        language: 语言过滤
        sort: stars / forks / updated
        order: desc / asc
        page: 页码
        per_page: 每页数量
        token: GitHub token
        progress_callback: 进度回调

    Returns:
        SearchResult
    """
    if not query.strip():
        return SearchResult()

    if progress_callback:
        progress_callback(f"[INFO] 正在搜索: {query}")

    # 构建查询
    q_parts = [query]
    if language:
        q_parts.append(f"language:{language}")

    params = urllib.parse.urlencode({
        "q": " ".join(q_parts),
        "sort": sort,
        "order": order,
        "page": page,
        "per_page": per_page,
    })
    url = f"{TRENDING_URL}?{params}"

    headers = _build_github_headers(token)

    # 发送请求
    data, success = _make_github_request(url, headers, progress_callback)

    if not success or not data:
        if progress_callback:
            progress_callback(f"[ERROR] 搜索失败")
        return SearchResult()

    # 解析结果
    total = data.get("total_count", 0)
    items = []
    for item in data.get("items", []):
        proj = _parse_single_result(item)
        items.append(proj)

    has_more = (page * per_page) < total

    if progress_callback:
        progress_callback(f"[SUCCESS] 找到 {total} 个结果")

    return SearchResult(total_count=total, items=items, page=page, has_more=has_more)


def fetch_by_category(
    category: str,
    sort: str = "stars",
    page: int = 1,
    per_page: int = 30,
    token: str = "",
    progress_callback: Callable = None,
) -> SearchResult:
    """按分类浏览项目"""
    if category == "全部" or category not in CATEGORIES:
        # 获取全局热门
        return search_repos("stars:>100", "", sort, "desc", page, per_page, token, progress_callback)

    cat_info = CATEGORIES[category]
    languages = cat_info["languages"]
    if not languages:
        return SearchResult()

    # 用该分类的第一个主要语言搜索
    primary_lang = languages[0]
    if progress_callback:
        progress_callback(f"[INFO] 浏览分类 {category} (语言: {primary_lang})")

    return search_repos(
        query="stars:>20",
        language=primary_lang,
        sort=sort,
        order="desc",
        page=page,
        per_page=per_page,
        token=token,
        progress_callback=progress_callback,
    )


# ── 获取语言颜色 ───────────────────────────────────────────

LANGUAGE_COLORS = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#2b7489",
    "C++": "#f34b7d",
    "C": "#555555",
    "Java": "#b07219",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "C#": "#178600",
    "Ruby": "#701516",
    "Shell": "#89e051",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Jupyter Notebook": "#DA5B0B",
    "Kotlin": "#A97BFF",
    "Swift": "#F05138",
    "Dart": "#00B4AB",
    "PHP": "#4F5D95",
    "Lua": "#000080",
    "Scala": "#c22d40",
    "Elixir": "#4e2a8e",
    "Haskell": "#5e5086",
    "Solidity": "#AA6746",
    "Zig": "#ec915c",
    "Nim": "#37775b",
    "PowerShell": "#012456",
    "Vue": "#41b883",
    "Svelte": "#ff3e00",
}


def get_language_color(lang: str) -> str:
    """获取语言对应的颜色"""
    return LANGUAGE_COLORS.get(lang, "#6e7681")


def translate_description(desc: str, max_length: int = 100) -> str:
    """
    翻译项目描述（使用增强版翻译引擎）

    Args:
        desc: 原始描述
        max_length: 最大长度

    Returns:
        翻译后的描述
    """
    return TranslationEngine.translate_description(desc, max_length)


# ── 内部辅助函数 ───────────────────────────────────────────

def _parse_single_result(item: dict) -> TrendingProject:
    """解析单个搜索结果为 TrendingProject"""
    owner_info = item.get("owner") or {}

    return TrendingProject(
        name=item.get("name", ""),
        full_name=item.get("full_name", ""),
        description=item.get("description", "") or "",
        url=item.get("html_url", ""),
        stars=item.get("stargazers_count", 0),
        forks=item.get("forks_count", 0),
        language=item.get("language", "") or "",
        language_color="",
        today_stars=0,
        owner=owner_info.get("login", ""),
        owner_avatar=owner_info.get("avatar_url", ""),
        topics=item.get("topics", []),
        category=get_category_for_language(item.get("language", "") or ""),
    )


def _parse_search_results(data: dict) -> List[TrendingProject]:
    """解析搜索结果数据"""
    results = []
    for item in data.get("items", []):
        proj = _parse_single_result(item)
        results.append(proj)
    return results


print("GitHub Explorer module loaded (optimized with rate limiting & retry)")
