"""GitHub 仓库 Secrets 写入（转换自 Node.js 版 utils/githubSecrets.js）。

依赖 gh CLI，通过环境变量 PAT 或 GH_TOKEN 认证。
"""

import os
import subprocess


def has_secret_write_token() -> bool:
    """是否配置了可写 Secrets 的 token。"""
    return bool(os.environ.get("PAT") or os.environ.get("GH_TOKEN"))


def set_repo_secret(name: str, value: str) -> None:
    """调用 gh CLI 将值写入仓库 Secret。

    Raises:
        RuntimeError: GITHUB_REPOSITORY 或 PAT/GH_TOKEN 未配置。
        subprocess.CalledProcessError: gh 命令执行失败。
    """
    repository = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GH_TOKEN") or os.environ.get("PAT")

    if not repository:
        raise RuntimeError("GITHUB_REPOSITORY 未配置")
    if not token:
        raise RuntimeError("PAT/GH_TOKEN 未配置")

    env = {**os.environ, "GH_TOKEN": token}
    subprocess.run(
        ["gh", "secret", "set", name, "--repo", repository],
        input=value,
        text=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
