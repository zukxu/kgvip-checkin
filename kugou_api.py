"""酷狗 API 纯 Python 客户端。

移植自 KuGouMusicApi（Node.js, MIT License, Copyright (c) 2023 MakcRe）的
util 加密/签名/请求层与本项目所需的 9 个接口模块，去除本地 Express 服务，
直接请求酷狗官方网关。

章节目录：
  1. 常量配置     —— appid、盐值、RSA 公钥、网关地址
  2. 加密工具     —— MD5 / AES-256-CBC / RSA(无填充)
  3. 签名算法     —— android / web signature、signParamsKey
  4. 请求引擎     —— create_request()：注入默认参数 → 签名 → 发送
  5. 接口定义     —— 登录（扫码/手机号）、token 续期、签到、VIP 查询

说明：仅实现标准版（platform 非 lite）参数，与原 Node 服务
api/.env 中 platform='' 的运行模式一致。
"""

import json
import random
import time
from hashlib import md5

import requests
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA

# ════════════════════════ 1. 常量配置 ════════════════════════

APPID = 1005            # 标准版 appid（lite 版为 3116，未使用）
SRC_APPID = 2919        # 登录类接口的 srcappid
CLIENTVER = 20489       # 标准版客户端版本号（lite 版为 11436）
DEFAULT_UA = "Android15-1070-11083-46-0-DiscoveryDRADProtocol-wifi"

GATEWAY = "https://gateway.kugou.com"          # 默认网关
LOGIN_HTTP_BASE = "http://login.user.kugou.com"  # 登录网关（http）
LOGIN_HTTPS_BASE = "https://login-user.kugou.com"  # 二维码登录网关（https）
VIP_BASE = "https://kugouvip.kugou.com"        # VIP 查询网关

# android signature 盐值（标准版）
SIGNATURE_ANDROID_SALT = "OIlwieks28dk2k092lksi2UIkp"
# web signature 盐值
SIGNATURE_WEB_SALT = "NVPh5oo715z5DIWAeQlhMDsWXXQV4hwt"
# signParamsKey 盐值（标准版）
SIGN_PARAMS_KEY_SALT = "OIlwieks28dk2k092lksi2UIkp"

# /login/token 接口固定的 AES key/iv（标准版）
LOGIN_TOKEN_AES_KEY = "90b8382a1bb4ccdcf063102053fd75b8"
LOGIN_TOKEN_AES_IV = "f063102053fd75b8"

# RSA 公钥（标准版，用于加密 AES 随机 key）
PUBLIC_RSA_KEY = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDIAG7QOELSYoIJvTFJhMpe1s/gbjDJX51HBNnEl5HXqTW6lQ7LC8jr9fWZTwusknp+sVGzwd40MwP6U5yDE27M/X1+UR4tvOGOqp94TJtQ1EPnWGWXngpeIW5GxoQGao1rmYWAu6oi1z9XkChrsUdC6DJE5E221wf/4WLFxwAtRQIDAQAB\n"
    "-----END PUBLIC KEY-----"
)

REQUEST_TIMEOUT_SECONDS = 30


# ════════════════════════ 2. 加密工具 ════════════════════════

def _dumps(obj) -> str:
    """紧凑 JSON 序列化（与 JS JSON.stringify 一致，无空格、不转义中文）。

    签名与请求体必须使用同一种序列化，否则服务端校验失败。
    """
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def crypto_md5(data) -> str:
    """MD5 摘要，十六进制小写；dict 自动紧凑序列化。"""
    if isinstance(data, (dict, list)):
        data = _dumps(data)
    return md5(data.encode("utf-8")).hexdigest()


def _random_string(length: int = 16) -> str:
    """随机字符串（数字 + 大写字母）。"""
    charset = "1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(random.choices(charset, k=length))


def _pkcs7_pad(data: bytes) -> bytes:
    pad_len = 16 - len(data) % 16
    return data + bytes([pad_len]) * pad_len


def _pkcs7_unpad(data: bytes) -> bytes:
    return data[: -data[-1]]


def aes_encrypt(data, key: str = "", iv: str = ""):
    """AES-256-CBC 加密，返回密文 hex。

    - 同时提供 key/iv：直接使用，返回 hex 字符串；
    - 只提供 key 或都不提供：生成随机 key，实际密钥为 md5(key) 前 32 位，
      iv 取其末 16 位；返回 (密文 hex, 随机 key)。
    """
    plaintext = _dumps(data).encode("utf-8") if isinstance(data, (dict, list)) else str(data).encode("utf-8")

    if key and iv:
        cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
        return cipher.encrypt(_pkcs7_pad(plaintext)).hex()

    temp_key = key or _random_string(16).lower()
    real_key = crypto_md5(temp_key)[:32]
    real_iv = real_key[-16:]
    cipher = AES.new(real_key.encode("utf-8"), AES.MODE_CBC, real_iv.encode("utf-8"))
    ciphertext = cipher.encrypt(_pkcs7_pad(plaintext)).hex()
    return ciphertext, temp_key


def aes_decrypt(data_hex: str, key: str, iv: str = ""):
    """AES-256-CBC 解密 hex 密文；key 未配 iv 时按 md5 规则推导。返回 dict 或 str。"""
    if not iv:
        key = crypto_md5(key)[:32]
        iv = key[-16:]
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
    plain = _pkcs7_unpad(cipher.decrypt(bytes.fromhex(data_hex))).decode("utf-8")
    try:
        return json.loads(plain)
    except json.JSONDecodeError:
        return plain


def rsa_encrypt(data) -> str:
    """RSA 无填充加密（NO PADDING，明文左对齐零填充到 128 字节），返回 hex。

    用于加密 AES 随机 key，服务端以对应私钥解密。
    """
    plaintext = _dumps(data).encode("utf-8") if isinstance(data, (dict, list)) else str(data).encode("utf-8")
    padded = plaintext + b"\x00" * (128 - len(plaintext))

    key = RSA.import_key(PUBLIC_RSA_KEY)
    ciphertext_int = pow(int.from_bytes(padded, "big"), key.e, key.n)
    return ciphertext_int.to_bytes(key.size_in_bytes(), "big").hex()


# ════════════════════════ 3. 签名算法 ════════════════════════

def signature_android(params: dict, data: str = "") -> str:
    """android signature：key=value 按 key 排序拼接，加盐 + 请求体。"""
    pairs = sorted(f"{k}={_dumps(v) if isinstance(v, (dict, list)) else v}" for k, v in params.items())
    return crypto_md5(f"{SIGNATURE_ANDROID_SALT}{''.join(pairs)}{data}{SIGNATURE_ANDROID_SALT}")


def signature_web(params: dict) -> str:
    """web signature：key=value 按 key 排序拼接，前后加盐。"""
    pairs = sorted(f"{k}={v}" for k, v in params.items())
    return crypto_md5(f"{SIGNATURE_WEB_SALT}{''.join(pairs)}{SIGNATURE_WEB_SALT}")


def sign_params_key(data) -> str:
    """手机号登录的 key 字段签名：md5(appid + 盐 + clientver + data)。"""
    return crypto_md5(f"{APPID}{SIGN_PARAMS_KEY_SALT}{CLIENTVER}{data}")


# ════════════════════════ 4. 请求引擎 ════════════════════════

def create_request(
    method: str,
    url: str,
    params: dict = None,
    data: dict = None,
    headers: dict = None,
    base_url: str = GATEWAY,
    encrypt_type: str = "android",
    cookie: dict = None,
) -> dict:
    """请求引擎：注入默认参数 → 计算 signature → 发送 HTTP 请求。

    - 默认参数：dfid/mid/uuid/appid/clientver/userid/clienttime（有 token 时附加）
    - signature 参与 URL 查询参数，data（请求体）参与 android 签名
    - 返回解析后的 JSON body；网络/HTTP 异常返回 {"status": 0, "msg": ...}

    Args:
        method: GET / POST
        url: 接口路径（不含网关）
        params: 业务查询参数（与默认参数合并后签名）
        data: 请求体（POST），以紧凑 JSON 发送
        headers: 自定义请求头（如 x-router）
        base_url: 网关地址
        encrypt_type: 签名方式 android / web
        cookie: 身份信息 {"token", "userid", ...}
    """
    cookie = cookie or {}
    dfid = cookie.get("dfid") or "-"
    mid = f"{crypto_md5(dfid)}{crypto_md5(dfid)[:7]}"
    uuid = crypto_md5(f"{dfid}{mid}")
    clienttime = int(time.time())

    default_params = {
        "dfid": dfid,
        "mid": mid,
        "uuid": uuid,
        "appid": APPID,
        "clientver": CLIENTVER,
        "userid": cookie.get("userid") or 0,
        "clienttime": clienttime,
    }
    if cookie.get("token"):
        default_params["token"] = cookie["token"]

    merged_params = {**default_params, **(params or {})}
    body_str = _dumps(data) if isinstance(data, (dict, list)) else (data or "")

    if encrypt_type == "web":
        merged_params["signature"] = signature_web(merged_params)
    else:
        merged_params["signature"] = signature_android(merged_params, body_str)

    request_headers = {
        "User-Agent": DEFAULT_UA,
        "dfid": dfid,
        "clienttime": str(clienttime),
        "mid": mid,
    }
    if headers:
        request_headers.update(headers)

    try:
        response = requests.request(
            method.upper(),
            base_url + url,
            params=merged_params,
            data=body_str.encode("utf-8") if body_str else None,
            headers=request_headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        return {"status": 0, "msg": str(error)}

    if response.status_code != 200:
        return {"status": 0, "msg": response.text[:200], "httpStatus": response.status_code}

    try:
        return response.json()
    except ValueError:
        return {"status": 0, "msg": response.text[:200], "httpStatus": response.status_code}


# ════════════════════════ 5. 接口定义 ════════════════════════
# 以下 9 个接口覆盖登录 / token 续期 / 签到 / VIP 查询全部流程。


# —— 登录：二维码 ──────────────────────────────────────────────

def qr_key() -> dict:
    """获取扫码登录二维码。

    返回 data.qrcode（二维码 key）与 data.qrcode_img（data:image/png;base64 图片）。
    """
    return create_request(
        "GET",
        "/v2/qrcode",
        params={
            "appid": 1001,
            "type": 1,
            "plat": 4,
            "qrcode_txt": f"https://h5.kugou.com/apps/loginQRCode/html/index.html?appid={APPID}&",
            "srcappid": SRC_APPID,
        },
        base_url=LOGIN_HTTPS_BASE,
        encrypt_type="web",
    )


def qr_check(key: str) -> dict:
    """轮询二维码扫码状态。

    返回 data.status：0 过期 / 1 未扫码 / 2 已扫码待确认 /
    4 登录成功（此时 data 内含 token 与 userid）。
    """
    return create_request(
        "GET",
        "/v2/get_userinfo_qrcode",
        params={"plat": 4, "appid": APPID, "srcappid": SRC_APPID, "qrcode": key},
        base_url=LOGIN_HTTPS_BASE,
        encrypt_type="web",
    )


# —— 登录：手机号验证码 ────────────────────────────────────────

def captcha_sent(mobile: str) -> dict:
    """发送短信验证码。"""
    return create_request(
        "POST",
        "/v7/send_mobile_code",
        data={"businessid": 5, "mobile": str(mobile), "plat": 3},
        base_url=LOGIN_HTTP_BASE,
    )


def login_cellphone(mobile: str, code: str, userid=None) -> dict:
    """手机号 + 验证码登录。

    请求体中 mobile 为脱敏值，真实手机号与验证码经 AES 加密放在 params，
    AES 随机 key 经 RSA 加密放在 pk。status=1 时 data 内含 token/userid。
    """
    clienttime_ms = int(time.time() * 1000)
    encrypted, temp_key = aes_encrypt({"mobile": str(mobile), "code": str(code)})
    masked_mobile = f"{str(mobile)[:2]}*****{str(mobile)[10:11]}"

    data_map = {
        "plat": 1,
        "support_multi": 1,
        "t1": 0,
        "t2": 0,
        "clienttime_ms": clienttime_ms,
        "mobile": masked_mobile,
        "key": sign_params_key(clienttime_ms),
        "t3": "MCwwLDAsMCwwLDAsMCwwLDA=",
        "params": encrypted,
        "pk": rsa_encrypt({"clienttime_ms": clienttime_ms, "key": temp_key}).upper(),
    }
    if userid is not None:
        data_map["userid"] = userid

    result = create_request(
        "POST",
        "/v7/login_by_verifycode",
        data=data_map,
        headers={"x-router": "login.user.kugou.com"},
    )
    _merge_secu_params(result, temp_key)
    return result


# —— token 续期 ───────────────────────────────────────────────

def login_token(cookie: dict) -> dict:
    """用现有 token 重新登录（续期），幂等：未到期时返回原 token。

    p3 为 AES 加密的 {clienttime, token}（固定 key/iv）；
    params 为加密的空对象，其随机 key 经 RSA 加密放在 pk；
    status=1 时 data 内含新 token。
    """
    clienttime_ms = int(time.time() * 1000)
    p3 = aes_encrypt(
        {"clienttime": int(clienttime_ms / 1000), "token": cookie.get("token") or ""},
        key=LOGIN_TOKEN_AES_KEY,
        iv=LOGIN_TOKEN_AES_IV,
    )
    encrypted_params, temp_key = aes_encrypt({})

    result = create_request(
        "POST",
        "/v5/login_by_token",
        data={
            "dfid": cookie.get("dfid") or "-",
            "p3": p3,
            "plat": 1,
            "t1": 0,
            "t2": 0,
            "t3": "MCwwLDAsMCwwLDAsMCwwLDA=",
            "pk": rsa_encrypt({"clienttime_ms": clienttime_ms, "key": temp_key}).upper(),
            "params": encrypted_params,
            "userid": cookie.get("userid") or "0",
            "clienttime_ms": clienttime_ms,
        },
        base_url=LOGIN_HTTP_BASE,
        headers={"x-router": "login.user.kugou.com"},
    )
    _merge_secu_params(result, temp_key)
    return result


def _merge_secu_params(result: dict, temp_key: str) -> None:
    """解密登录响应中的 secu_params（内含 token），合并进 data。"""
    if result.get("status") != 1:
        return
    data = result.get("data") or {}
    secu_params = data.get("secu_params")
    if secu_params:
        decrypted = aes_decrypt(secu_params, temp_key)
        if isinstance(decrypted, dict):
            data.update(decrypted)


# —— 签到 ─────────────────────────────────────────────────────

def user_detail(cookie: dict) -> dict:
    """获取账号详情（昵称等），同时用于校验 token 是否有效。"""
    clienttime = int(time.time())
    pk = rsa_encrypt({"token": cookie.get("token") or "", "clienttime": clienttime}).upper()

    return create_request(
        "POST",
        "/v3/get_my_info",
        params={"plat": 1},
        data={
            "visit_time": clienttime,
            "usertype": 1,
            "p": pk,
            "userid": int(cookie.get("userid") or 0),
        },
        headers={"x-router": "usercenter.kugou.com"},
    )


def youth_listen_song(cookie: dict, mixsongid: int = 666075191) -> dict:
    """上报听歌记录领取 VIP（每日 1 次，+24 小时）。

    error_code=130012 表示今日已领取。
    """
    return create_request(
        "POST",
        "/youth/v2/report/listen_song",
        params={"clientver": 10566},
        data={"mixsongid": mixsongid},
        cookie=cookie,
        headers={
            "User-Agent": "Android13-1070-10566-201-0-ReportPlaySongToServerProtocol-wifi",
            "content-type": "application/json; charset=utf-8",
        },
    )


def youth_vip(cookie: dict) -> dict:
    """上报看完 30 秒广告领取 VIP（每日 8 次，每次 +3 小时）。

    error_code=30002 表示今日次数已用完。
    """
    now_ms = int(time.time() * 1000)
    return create_request(
        "POST",
        "/youth/v1/ad/play_report",
        data={
            "ad_id": 12307537187,
            "play_end": now_ms,
            "play_start": now_ms - 30000,
        },
        cookie=cookie,
    )


# —— VIP 查询 ─────────────────────────────────────────────────

def user_vip_detail(cookie: dict) -> dict:
    """查询概念版 VIP 详情，data.busi_vip[0].vip_end_time 为到期时间。"""
    return create_request(
        "GET",
        "/v1/get_union_vip",
        params={"busi_type": "concept"},
        base_url=VIP_BASE,
        cookie=cookie,
    )
