"""首次登录流程：扫码 / 手机号验证码。

直连酷狗登录网关（接口定义见 kugou_api.py），返回格式与 USERINFO 一致：
[{"userid": ..., "token": "..."}]。
"""

import base64
import os
import pprint
import subprocess
import sys
import time
from pathlib import Path

import kugou_api
from color_out import print_green, print_magenta, print_red, print_yellow
from safe_log import summarize_response

QR_POLL_INTERVAL_SECONDS = 5
QR_POLL_MAX_TIMES = 25
QR_IMAGE_FILE = Path(__file__).resolve().parent / "login_qrcode.png"


def _prompt(message: str, default: str = "") -> str:
    """交互输入；非交互环境（如 Actions）返回默认值。"""
    try:
        return input(message).strip()
    except EOFError:
        return default


def _open_image(path: Path) -> None:
    """用系统默认图片查看器打开二维码，失败时忽略。"""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError:
        pass


def _show_qrcode_image(qrcode_img: str) -> None:
    """展示二维码：本地保存并打开图片；GitHub Actions 中打印 data URI。

    qrcode_img 形如 "data:image/png;base64,xxxx"。
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print_magenta("请将下方内容按顺序拼接成完整链接，在浏览器打开后使用酷狗 APP 扫码")
        chunk_size = 1000
        for i in range(0, len(qrcode_img), chunk_size):
            print(qrcode_img[i:i + chunk_size])
        return

    base64_data = qrcode_img.partition(",")[2] or qrcode_img
    QR_IMAGE_FILE.write_bytes(base64.b64decode(base64_data))
    print_green(f"二维码已保存: {QR_IMAGE_FILE}")
    _open_image(QR_IMAGE_FILE)
    print_magenta("请使用酷狗 APP 扫描二维码并确认登录")


def qrcode_login(count: int = 1) -> list:
    """扫码登录 count 个账号，返回 [{"userid", "token"}] 列表。"""
    userinfo = []
    for _ in range(count):
        result = kugou_api.qr_key()
        if result.get("status") != 1:
            print_red("响应内容")
            pprint.pprint(summarize_response(result))
            raise RuntimeError("请求出错")

        _show_qrcode_image(result["data"]["qrcode_img"])
        print_magenta("正在等待，请扫描二维码并确定登录")

        key = result["data"]["qrcode"]
        for attempt in range(QR_POLL_MAX_TIMES):
            res = kugou_api.qr_check(key)
            status = ((res.get("data") or {}).get("status"))

            if status == 4:
                print_green("登录成功！")
                userinfo.append({
                    "userid": res["data"]["userid"],
                    "token": res["data"]["token"],
                })
                break
            if status == 0:
                print_yellow("二维码已过期")
                break
            if status not in (1, 2):  # 1 未扫描 / 2 未确认，静默等待
                print_red("请求出错")
                pprint.pprint(summarize_response(res))
            if attempt == QR_POLL_MAX_TIMES - 1:
                print_red("等待超时\n")
                break
            time.sleep(QR_POLL_INTERVAL_SECONDS)

    return userinfo


def phone_login() -> list:
    """手机号验证码登录，返回 [{"userid", "token"}] 列表。

    手机号/验证码优先读取环境变量 PHONE/CODE（用于 Actions），
    未设置时交互输入。
    """
    phone = os.environ.get("PHONE") or _prompt("请输入手机号: ")
    if not phone:
        raise RuntimeError("未输入手机号")

    print("开始发送验证码")
    result = kugou_api.captcha_sent(phone)
    if result.get("status") != 1:
        print_red("响应内容")
        pprint.pprint(summarize_response(result))
        raise RuntimeError("验证码发送失败！请检查手机号")
    print_green("验证码发送成功")

    code = os.environ.get("CODE") or _prompt("请输入验证码: ")
    if not code:
        raise RuntimeError("未输入验证码")

    result = kugou_api.login_cellphone(phone, code)
    if result.get("status") == 1:
        print_green("登录成功！")
        return [{
            "userid": result["data"]["userid"],
            "token": result["data"]["token"],
        }]
    if result.get("error_code") == 34175:
        raise RuntimeError("暂不支持多账号绑定手机登录")

    print_red("响应内容")
    pprint.pprint(summarize_response(result))
    raise RuntimeError("登录失败！请检查验证码")


def login_interactive() -> list:
    """引导用户选择登录方式并完成登录。"""
    print_yellow("未检测到账号信息（环境变量 USERINFO 与本地 userinfo.json 均为空）")
    choice = _prompt("请选择登录方式: 1 扫码登录（推荐） / 2 手机号验证码登录  [1]: ", "1")
    if choice == "2":
        return phone_login()
    return qrcode_login()
