"""core.api.error_collector — 模型接口报错收集模块

    收集 Agnes 文本/图片/视频模型 API 调用失败时的报错信息，
    包含 prompt、错误类型、错误详情等，存储在工作目录下的 error_logs/ 中。

    使用方式：
        from core.api.error_collector import collect_error, collect_error_from_exception

        # 方式一：手动构造
        collect_error(model_type="image", api_method="generate_single_image",
                      prompt="一只猫", error_type="ConnectionError",
                      error_message="Connection timed out", retry_count=3)

        # 方式二：从异常对象收集
        collect_error_from_exception("chat", "chat", exc, prompt="你好")
"""

import json
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_WORKSPACE_ROOT: Optional[Path] = None


def set_workspace_root(path: str) -> None:
    """设置错误日志存储的根目录（通常为激活的工作空间路径）。

    应在服务启动时调用一次。如果不设置，则回退到 server.py 所在目录。
    """
    global _WORKSPACE_ROOT
    _WORKSPACE_ROOT = Path(path).resolve()
    logger.info(f"[ErrorCollector] Workspace root set to {_WORKSPACE_ROOT}")


def _get_workspace_root() -> Path:
    """获取存储根目录。

    优先级：
    1. set_workspace_root() 显式设置
    2. 自动检测 server.py 所在目录
    """
    global _WORKSPACE_ROOT
    if _WORKSPACE_ROOT is not None:
        return _WORKSPACE_ROOT
    current = Path(os.getcwd()).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "server.py").exists():
            _WORKSPACE_ROOT = parent
            break
    if _WORKSPACE_ROOT is None:
        _WORKSPACE_ROOT = current
    return _WORKSPACE_ROOT


def _get_log_dir() -> Path:
    """获取 error_logs 目录路径，不存在则创建。"""
    log_dir = _get_workspace_root() / "error_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def collect_error(
    model_type: str,
    api_method: str,
    prompt: str = "",
    system_prompt: str = "",
    error_type: str = "",
    error_message: str = "",
    status_code: Optional[int] = None,
    response_body: str = "",
    retry_count: int = 0,
    extra: Optional[dict] = None,
) -> Optional[str]:
    """收集一次 API 调用错误并写入 error_logs/ 目录。

    返回保存的文件路径，如果收集过程自身出错则返回 None（不影响主流程）。

    Args:
        model_type: 模型类型，如 "chat", "image", "video"。
        api_method: 调用的方法名，如 "chat", "generate_single_image", "submit_video"。
        prompt: 发送给模型的 prompt（超长自动截断至 5000 字符）。
        system_prompt: system 提示词（仅 chat 类，截断至 2000 字符）。
        error_type: 错误类型名称，如 "ConnectionError", "HTTPError", "RuntimeError"。
        error_message: 错误消息原文。
        status_code: HTTP 状态码（如有）。
        response_body: 响应体原文（截断至 5000 字符）。
        retry_count: 失败前已尝试的重试次数。
        extra: 额外结构化信息（如 video_id, mode 等）。
    """
    try:
        log_dir = _get_log_dir()
        now = datetime.now()
        filename = (
            now.strftime("%Y-%m-%d_%H-%M-%S-%f")
            + f"_{model_type}_{api_method}.json"
        )
        filepath = log_dir / filename

        # 限制字段长度，避免日志文件过大
        error_data = {
            "timestamp": now.isoformat(),
            "model_type": model_type,
            "api_method": api_method,
            "prompt": prompt[:5000] if prompt else "",
            "system_prompt": system_prompt[:2000] if system_prompt else "",
            "error_type": error_type,
            "error_message": error_message[:3000] if error_message else "",
            "status_code": status_code,
            "response_body": response_body[:5000] if response_body else "",
            "retry_count": retry_count,
        }
        if extra:
            error_data["extra"] = extra

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(error_data, f, ensure_ascii=False, indent=2)

        logger.info(f"[ErrorCollector] Error saved → {filepath}")
        return str(filepath)

    except Exception as e:
        logger.error(f"[ErrorCollector] Failed to collect error: {e}")
        return None


def collect_error_from_exception(
    model_type: str,
    api_method: str,
    exc: Exception,
    prompt: str = "",
    system_prompt: str = "",
    status_code: Optional[int] = None,
    response_body: str = "",
    retry_count: int = 0,
    extra: Optional[dict] = None,
) -> Optional[str]:
    """便捷包装：从异常对象自动提取 error_type 和 error_message。"""
    return collect_error(
        model_type=model_type,
        api_method=api_method,
        prompt=prompt,
        system_prompt=system_prompt,
        error_type=type(exc).__name__,
        error_message=str(exc),
        status_code=status_code,
        response_body=response_body,
        retry_count=retry_count,
        extra=extra,
    )
