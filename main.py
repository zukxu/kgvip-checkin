"""酷狗概念版 VIP 自动签到主流程。

智能签到：自动检测登录状态——优先读取环境变量 USERINFO（GitHub Actions），
其次读取本地 userinfo.json，两者均无时引导扫码或手机号验证码登录；
登录完成后立即签到。每天签到时调用续期接口刷新 token（未到期返回原值），
发生变化时回写本地文件与 GitHub Secret。
接口定义与加密/签名详见 kugou_api.py（直连酷狗官方网关，无本地服务依赖）。
"""

import argparse
import json
import os
import pprint
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import kugou_api
from color_out import print_blue, print_green, print_magenta, print_red, print_yellow
from github_secrets import has_secret_write_token, set_repo_secret
from login import login_interactive, phone_login, qrcode_login
from safe_log import mask_display_name, mask_identifier, sanitize_for_log, should_print_sensitive_value, summarize_response

USERINFO_FILE = Path(__file__).resolve().parent / "userinfo.json"

AD_CLAIM_ROUNDS = 8
AD_CLAIM_INTERVAL_SECONDS = 30


def now_utc8() -> datetime:
    """GitHub 服务器时间比国内慢 8 小时，统一换算为东八区。"""
    return datetime.now(timezone.utc) + timedelta(hours=8)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="酷狗概念版 VIP 自动签到（未登录时自动引导登录）")
    login_group = parser.add_mutually_exclusive_group()
    login_group.add_argument("--qrcode", action="store_true", help="强制扫码登录后签到")
    login_group.add_argument("--login", action="store_true", help="手机号验证码登录后签到")
    parser.add_argument("--count", type=int, default=1, metavar="N", help="扫码登录的账号数量（默认 1）")
    return parser.parse_args()


def load_userinfo() -> list | None:
    """加载账号信息：环境变量 USERINFO 优先（Actions 用），其次本地 userinfo.json。"""
    raw = os.environ.get("USERINFO")
    if raw:
        return json.loads(raw)
    if USERINFO_FILE.exists():
        return json.loads(USERINFO_FILE.read_text(encoding="utf-8"))
    return None


def save_userinfo(userinfo: list) -> None:
    """保存账号信息：写入本地 userinfo.json；配置了 PAT 时同步 GitHub Secret。"""
    userinfo_json = json.dumps(userinfo, ensure_ascii=False)
    USERINFO_FILE.write_text(userinfo_json, encoding="utf-8")
    print_green("账号信息已保存到 userinfo.json")

    if not has_secret_write_token():
        print_yellow("PAT/GH_TOKEN 未配置，无法同步 GitHub Secret（未刷新的 token 约两个月后过期）")
        if should_print_sensitive_value():
            print_yellow("已按显式配置输出 USERINFO；注意日志包含 token，请用完后删除 Actions 日志")
            print_blue(userinfo_json)
        else:
            print_yellow("为避免泄露 token，默认不在日志输出 USERINFO")
            print_yellow("如必须手动复制，请设置环境变量 ALLOW_PRINT_USERINFO=是 后重新运行")
        return

    try:
        set_repo_secret("USERINFO", userinfo_json)
        print_green("secret <USERINFO> 更改成功")
    except Exception as error:
        print_red("自动写入 secret <USERINFO> 出错")
        pprint.pprint(sanitize_for_log({"message": str(error)}))
        print_yellow("本地 userinfo.json 已保存，本地签到不受影响")


def merge_user(userinfo: list, credentials: dict) -> None:
    """合并登录账号：userid 已存在时仅更新 token，否则追加。"""
    for existing in userinfo:
        if existing.get("userid") == credentials["userid"]:
            print_yellow(f"userid: {mask_identifier(credentials['userid'])} 此账号已存在, 仅更新登录信息")
            existing["token"] = credentials["token"]
            return
    userinfo.append(credentials)


def fetch_user_detail(user: dict, error_msg: dict) -> str:
    """获取账号详情并返回脱敏昵称；账号无效时记录异常并返回空字符串。"""
    detail = kugou_api.user_detail(user)
    nickname = ((detail or {}).get("data") or {}).get("nickname")
    if nickname is not None:
        return mask_display_name(nickname)

    safe_user_id = mask_identifier(user["userid"])
    message = f"token过期或账号不存在, userid: {safe_user_id}"
    print_red(message)
    error_msg[safe_user_id] = {"msg": message, "data": summarize_response(detail)}
    return ""


def refresh_token(user: dict, safe_nickname: str) -> bool:
    """调用续期接口刷新 token；返回 token 是否发生变化。

    /login/token 为幂等的 token 重登录，未到期时服务端返回原 token。
    """
    result = kugou_api.login_token(user)
    if result.get("status") == 1:
        new_token = (result.get("data") or {}).get("token")
        if new_token and new_token != user["token"]:
            print_yellow(f"账号 {safe_nickname} 需要刷新token")
            user["token"] = new_token
            return True
    return False


def listen_song(user: dict, safe_nickname: str, error_msg: dict) -> None:
    """听歌领取 VIP。"""
    print_yellow("开始听歌领取VIP...")
    listen = kugou_api.youth_listen_song(user)

    if listen.get("status") == 1:
        print_green("听歌领取成功")
    elif listen.get("error_code") == 130012:
        print_green("今日已领取")
    else:
        error_msg[f"{safe_nickname} listen"] = summarize_response(listen)
        print_red("听歌领取失败")


def claim_vip_by_ad(user: dict, safe_nickname: str, error_msg: dict) -> None:
    """看广告领取 VIP，每日最多 8 次，两次之间等待 30 秒。"""
    print_yellow("开始领取VIP...")
    for round_no in range(1, AD_CLAIM_ROUNDS + 1):
        ad = kugou_api.youth_vip(user)

        if ad.get("status") == 1:
            print_green(f"第{round_no}次领取成功")
            if round_no != AD_CLAIM_ROUNDS:
                time.sleep(AD_CLAIM_INTERVAL_SECONDS)
        elif ad.get("error_code") == 30002:
            print_green("今天次数已用光")
            break
        else:
            print_red(f"第{round_no}次领取失败")
            error_msg[f"{safe_nickname} ad"] = summarize_response(ad)
            break


def show_vip_detail(user: dict, date: str, safe_nickname: str, error_msg: dict) -> None:
    """查询并打印 VIP 到期时间。"""
    vip_detail = kugou_api.user_vip_detail(user)

    if vip_detail.get("status") == 1:
        end_time = vip_detail["data"]["busi_vip"][0]["vip_end_time"]
        print_blue(f"今天是：{date}")
        print_blue(f"VIP到期时间：{end_time}\n")
    else:
        print_red("获取失败\n")
        error_msg[f"{safe_nickname} vip_details"] = summarize_response(vip_detail)


def run_login(args: argparse.Namespace, userinfo: list) -> None:
    """引导登录并把账号合并进 userinfo。"""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        raise RuntimeError(
            "Actions 环境未配置账号信息（Secret USERINFO 为空）。"
            "请先在本地运行 python main.py 完成登录，"
            "再将本地 userinfo.json 的内容添加为仓库 Secret USERINFO"
        )

    if args.qrcode:
        credentials_list = qrcode_login(args.count)
    elif args.login:
        credentials_list = phone_login()
    else:
        credentials_list = login_interactive()

    for credentials in credentials_list:
        merge_user(userinfo, credentials)
    if not userinfo:
        raise RuntimeError("登录未完成，无账号信息")
    save_userinfo(userinfo)


def main() -> None:
    args = parse_args()
    userinfo = load_userinfo() or []

    # 首次运行或显式指定登录参数时，先登录再签到
    if args.qrcode or args.login or not userinfo:
        run_login(args, userinfo)

    today = now_utc8()
    date = today.strftime("%Y-%m-%d")

    error_msg: dict = {}
    need_refresh = False

    for user in userinfo:
        safe_nickname = fetch_user_detail(user, error_msg)
        if not safe_nickname:
            continue
        print_magenta(f"账号 {safe_nickname} 开始领取VIP...")

        if refresh_token(user, safe_nickname):
            need_refresh = True

        listen_song(user, safe_nickname, error_msg)
        claim_vip_by_ad(user, safe_nickname, error_msg)
        show_vip_detail(user, date, safe_nickname, error_msg)

    # 每日续期：token 已就地更新，有变化时回写本地文件与 Secret
    if need_refresh:
        save_userinfo(userinfo)

    if error_msg:
        print_red("异常信息如下:")
        pprint.pprint(sanitize_for_log(error_msg))
        raise RuntimeError("领取异常")


if __name__ == "__main__":
    main()
