


# 酷狗概念版 VIP 自动签到（Python 版）

看了GitHub上存在一个 Node.js 版本的 [kgcheckin](https://github.com/develop202/kgcheckin) 最近他更新后流程一直报错，就想着自己重构为 Python 版本

去掉 Express 中间层，直接通过 httpx 异步请求酷狗 API。

## 功能

- 每日自动签到（听歌领 VIP + 看广告领 VIP）
- 手机号验证码登录
- 二维码扫码登录
- Token 自动刷新（周日）
- VIP 到期时间查询
- 多账号支持

## 项目结构

```
kgcheckin-py/
├── kugou/                  # 核心库
│   ├── config.py           # 常量配置
│   ├── crypto.py           # AES/RSA/MD5/SHA1 加密
│   ├── signature.py        # 签名算法
│   ├── request.py          # httpx 请求引擎
│   └── api.py              # 10个 API 接口
├── main.py                 # 主入口（智能签到：自动检测登录状态，一键完成登录+签到）
├── login.py                # 二维码登录流程
├── github_secrets.py       # GitHub Secrets 读写
├── safe_log.py             # 敏感信息脱敏
├── requirements.txt        # Python 依赖
├── tests/
│   └── test_phase1.py      # 单元测试
└── .github/workflows/
    ├── main.yml             # 每日签到
    ├── login.yml            # 登录（手机号/二维码）
    └── keepalive.yml        # 仓库保活
```

## 使用方式

### GitHub Actions（推荐，全自动）

只需一次手动登录，之后每天自动签到。

**1. Fork 本仓库**

**2. 创建 PAT（Personal Access Token）**

访问 https://github.com/settings/personal-access-tokens/new 创建 token：
- **Repository access**：只选当前 fork 的仓库
- **Permissions**：`Secrets` → 读写
![01pat生成.png](images/01pat%E7%94%9F%E6%88%90.png)

生成后复制 token 值。

**3. 设置 Secret**

在仓库 `Settings → Secrets and variables → Actions` 中新增：

| Secret | 值 |
|--------|-----|
| `PAT` | 上一步生成的 token |

![02变量设置.png](images/02%E5%8F%98%E9%87%8F%E8%AE%BE%E7%BD%AE.png)
**4. 首次登录**

进入 Actions 标签页 → 选择「登录账号」→ `Run workflow`：

- 选择 `qrcode`（推荐）：运行后在日志中看到二维码，用酷狗 APP 扫码确认
- 或选择 `phone`：填入手机号和短信验证码完成登录

登录成功后 USERINFO 自动写入 Secrets，无需手动操作。

**5. 完成**

之后每天北京时间 01:10 自动签到，Token 每周日自动刷新。

### 本地运行

```bash
pip install -r requirements.txt

# 一键签到（首次自动引导登录，默认二维码）
python main.py

# 指定登录方式 + 签到
# 二维码登录后签到
python main.py --qrcode
# 手机号登录后签到
python main.py --login
```

## 本地开发

### 环境搭建

```bash
# 克隆项目
git clone https://github.com/<your-username>/kgcheckin-py.git
cd kgcheckin-py

# 创建虚拟环境（推荐用 uv，也可以用标准 venv）
uv venv .venv --python 3.11
source .venv/bin/activate

# 安装依赖
uv pip install -r requirements.txt
# 开发测试额外安装
uv pip install pytest
```

### 项目架构

```
请求流程：
main.py / login.py
    │
    ▼
kugou/api.py          ← API 接口层：定义每个接口的参数、加密方式、URL
    │
    ▼
kugou/request.py      ← 请求引擎：注入默认参数、签名、发送 HTTP 请求
    │                    使用 httpx.AsyncClient 异步请求
    ▼
kugou/signature.py    ← 签名算法：android / web / register 三种签名
    │
    ▼
kugou/crypto.py       ← 加密工具：AES-256-CBC / RSA / MD5 / SHA1
    │
    ▼
kugou/config.py       ← 常量配置：APPID、密钥、salt值、网关地址
```

每个 API 接口本质上就是：**组装参数 → 选择加密方式 → 调用 `create_request()` 发送请求**。

### 新增 API 接口

以新增"获取歌单详情"接口为例：

**第 1 步：确定接口参数**

在原项目 `api/module/` 目录找到对应的 JS 文件（如 `playlist_detail.js`），或通过抓包获取接口信息：
- URL 路径：`/v3/get_playlist_detail`
- 请求方法：GET 或 POST
- 需要的参数：`playlistid` 等
- 加密类型：`android` / `web` / `register`

**第 2 步：在 `kugou/api.py` 中添加函数**

```python
# ── 11. playlist_detail — 歌单详情 ──────────────────
async def playlist_detail(cookie: dict, playlistid: int) -> ApiResponse:
    """获取歌单详情"""
    return await create_request({
        "url": "/v3/get_playlist_detail",
        "method": "get",
        "params": {"playlistid": playlistid},
        "encryptType": "android",   # 签名方式
        "cookie": cookie,
    })
```

**第 3 步：`create_request()` 的 options 参数说明**

| 参数 | 类型 | 说明 |
|------|------|------|
| `url` | str | API 路径，如 `/v3/get_my_info` |
| `method` | str | `"get"` 或 `"post"` |
| `baseURL` | str | 可选，默认 `gateway.kugou.com`；登录接口用 `LOGIN_HTTP_BASE` |
| `params` | dict | URL 查询参数，会自动合并 dfid/mid/uuid/appid 等默认参数 |
| `data` | dict/str | POST 请求体（dict 自动 JSON 序列化） |
| `encryptType` | str | 签名方式：`"android"`（默认）/ `"web"` / `"register"` |
| `cookie` | dict | 用户身份 `{token, userid, dfid}`，登录接口可不传 |
| `headers` | dict | 自定义请求头，如 `{"x-router": "xxx.kugou.com"}` |
| `clearDefaultParams` | bool | 为 True 时不自动注入默认参数（默认 False） |
| `notSignature` | bool | 为 True 时跳过签名（默认 False） |

**第 4 步（可选）：如果接口需要加密参数**

部分接口（如登录类）需要对 data 做 AES 加密 + RSA 加密 key：

```python
from kugou.crypto import crypto_aes_encrypt, crypto_rsa_encrypt

async def my_encrypted_api(cookie: dict):
    # AES 加密业务参数，随机 key
    encrypt = crypto_aes_encrypt({"param1": "value1"})
    # RSA 加密随机 key
    pk = crypto_rsa_encrypt({"key": encrypt["key"]}).upper()

    return await create_request({
        "url": "/v1/some_api",
        "method": "post",
        "data": {"params": encrypt["str"], "pk": pk},
        "encryptType": "android",
        "cookie": cookie,
    })
```

**第 5 步（可选）：如果接口需要新常量**

在 `kugou/config.py` 中添加新的网关地址、盐值或密钥：

```python
# config.py 底部新增
MY_API_BASE = "https://some-new-gateway.kugou.com"
```

**第 6 步：编写测试**

在 `tests/` 下添加测试用例：

```python
import asyncio
from kugou.api import playlist_detail

def test_playlist_detail():
    async def _run():
        resp = await playlist_detail(
            cookie={"token": "fake", "userid": "0", "dfid": "-"},
            playlistid=12345,
        )
        assert resp.status in (200, 502)  # 200 成功或 502 业务错误（假 token）
    asyncio.run(_run())
```

### 开发注意事项

- **`create_request()` 会自动注入签名**：默认注入 `dfid/mid/uuid/appid/clientver/clienttime/token/userid`，不需要手动传
- **`encryptType` 决定签名算法**：大部分接口用 `"android"`，二维码类用 `"web"`
- **API 返回 `ApiResponse` 对象**：`resp.status`（HTTP 层）、`resp.body`（JSON body）、`resp.cookie`（Set-Cookie 列表）
- **`data=null` 防护**：酷狗 API 可能返回 `"data": null`，用 `(body.get("data") or {}).get(...)` 而非 `body.get("data", {}).get(...)`
- **概念版/标准版切换**：设置环境变量 `export platform=lite` 可切换为概念版参数

## 免责声明

> **重要声明**
>
> 1. 本项目仅供学习使用，请尊重版权，请勿利用此项目从事商业行为及非法用途!
> 2. 使用本项目的过程中可能会产生版权数据。对于这些版权数据，本项目不拥有它们的所有权。为了避免侵权，使用者务必在 24 小时内清除使用本项目的过程中所产生的版权数据。
> 3. 由于使用本项目产生的包括由于本协议或由于使用或无法使用本项目而引起的任何性质的任何直接、间接、特殊、偶然或结果性损害（包括但不限于因商誉损失、停工、计算机故障或故障引起的损害赔偿，或任何及所有其他商业损害或损失）由使用者负责。
> 4. **禁止在违反当地法律法规的情况下使用本项目。** 对于使用者在明知或不知当地法律法规不允许的情况下使用本项目所造成的任何违法违规行为由使用者承担，本项目不承担由此造成的任何直接、间接、特殊、偶然或结果性责任。
> 5. 音乐平台不易，请尊重版权，支持正版。
> 6. 本项目仅用于对技术可行性的探索及研究，不接受任何商业（包括但不限于广告等）合作及捐赠。
> 7. 如果官方音乐平台觉得本项目不妥，可联系本项目更改或移除。

## 开源协议

本项目的核心加密逻辑和 API 接口源自以下开源项目，均采用 **MIT License** 发布：

- [MakcRe/KuGouMusicApi](https://github.com/MakcRe/KuGouMusicApi) — MIT License, Copyright (c) 2023 MakcRe

根据 MIT 协议要求，上述版权声明和许可声明已包含在本项目中。

本项目（Python 重构版）同样采用 **MIT License** 发布。

## 致谢

- 感谢 [@MakcRe](https://github.com/MakcRe) 提供 KuGouMusicApi 源代码（加密算法、签名机制、API 接口）
- 感谢 [@develop202](https://github.com/develop202/kgcheckin) Node.js 版本提供思路