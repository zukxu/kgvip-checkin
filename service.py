"""本地 api 服务管理与请求发送（转换自 Node.js 版 utils/utils.js）。

Node.js 版通过 `npm run apiService` 在本地 127.0.0.1:3000 启动
KuGouMusicApi 服务，本模块负责该子进程的生命周期与 HTTP 请求。
"""

import shutil
import socket
import subprocess
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent
API_HOST = "127.0.0.1"
API_PORT = 3000
API_BASE_URL = f"http://{API_HOST}:{API_PORT}"
REQUEST_TIMEOUT_SECONDS = 30
SERVICE_READY_TIMEOUT_SECONDS = 30


def timestamp_ms() -> int:
    """当前毫秒级时间戳（对应 JS 的 Date.now()）。"""
    return int(time.time() * 1000)


def delay(ms: float) -> None:
    """毫秒级等待。"""
    time.sleep(ms / 1000)


def start_service() -> subprocess.Popen:
    """启动本地 api 服务子进程（npm run apiService）。

    Raises:
        RuntimeError: 缺少 api 服务文件，或未找到 npm。
    """
    if not (PROJECT_ROOT / "package.json").is_file() or not (PROJECT_ROOT / "api").is_dir():
        raise RuntimeError(
            "缺少 api 服务文件（package.json / api/ 目录），"
            "请按 docs/操作文档.md「3.1 首次准备」完成配置"
        )
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("未找到 npm，请先安装 Node.js")

    return subprocess.Popen(
        [npm, "run", "apiService"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_service_ready(timeout_seconds: float = SERVICE_READY_TIMEOUT_SECONDS) -> None:
    """轮询等待 api 服务端口就绪（比固定延时更可靠）。

    Raises:
        RuntimeError: 超时未就绪。
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            with socket.create_connection((API_HOST, API_PORT), timeout=1):
                return
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"api 服务启动超时（{API_BASE_URL} 无法访问）。"
                    "请手动验证：cd api 后执行 npm run start；"
                    "若提示缺少依赖，先执行 npm ci"
                ) from None
            time.sleep(0.5)


def close_api(api: subprocess.Popen) -> None:
    """关闭本地 api 服务子进程。"""
    api.kill()
    api.wait()


def send(path: str, method: str, headers: dict) -> object:
    """请求本地 api 服务并返回解析后的 JSON。

    Raises:
        requests.RequestException: 请求失败或超时。
        ValueError: 响应不是合法 JSON。
    """
    response = requests.request(
        method,
        API_BASE_URL + path,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return response.json()
