"""彩色终端输出工具（转换自 Node.js 版 utils/colorOut.js）。"""

RESET = "\x1b[0m"


def _print(color: str, msg: object) -> None:
    print(f"{color}{msg}{RESET}")


def print_red(msg: object) -> None:
    """红色输出，用于错误信息。"""
    _print("\x1b[31m", msg)


def print_green(msg: object) -> None:
    """绿色输出，用于成功信息。"""
    _print("\x1b[32m", msg)


def print_yellow(msg: object) -> None:
    """黄色输出，用于提示信息。"""
    _print("\x1b[33m", msg)


def print_blue(msg: object) -> None:
    """蓝色输出，用于常规信息。"""
    _print("\x1b[34m", msg)


def print_magenta(msg: object) -> None:
    """品红色输出，用于账号信息。"""
    _print("\x1b[35m", msg)
