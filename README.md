# 酷狗概念版 VIP 自动签到（Python 版）

由 Node.js 版 [kgcheckin](https://github.com/develop202/kgcheckin) 重构而来的 Python 版本：每日自动「听歌 + 看广告」领取青春 VIP（每日累计上限 48 小时），token 每日自动续期。

## 功能

- 毺日自动签到（听歌领 VIP + 看广告领 VIP × 8）
- 首次运行扫码 / 手机号验证码登录，免手动配置
- Token 每日自动续期，变更时回写本地与 GitHub Secret
- VIP 到期时间查询、多账号支持
- 日志全程脱敏（昵称、userid、token、手机号）

## 快速开始

```bash
pip install -r requirements.txt
python main.py              # 智能签到：未登录自动引导登录，已登录直接签到
python main.py --qrcode     # 强制扫码登录（--count N 一次登多个）
python main.py --login      # 手机号验证码登录
```

前置条件与详细说明见 [docs/操作文档.md](docs/操作文档.md)。

## GitHub Actions（推荐，全自动）

1. Fork / 使用本仓库
2. 创建 PAT：访问 https://github.com/settings/personal-access-tokens/new
   - **Repository access**：只选本仓库
   - **Permissions**：`Secrets` → 读写
3. 仓库 `Settings → Secrets and variables → Actions` 添加 Secret `PAT` = 上一步的 token
4. Actions 页面 → `main` → `Run workflow` 手动跑一次：日志中拼接二维码链接扫码登录，`USERINFO` 自动写入
5. 之后每天北京时间 01:10 自动签到 + 续期

## 项目结构

```
main.py             # 主入口：登录检测、签到流程、每日 token 续期
login.py            # 扫码 / 手机号验证码登录
service.py          # 本地 api 服务管理（启动/等待/请求）
safe_log.py         # 日志脱敏
github_secrets.py   # GitHub Secret 写入（gh CLI）
color_out.py        # 彩色输出
api/                # KuGouMusicApi 精简版（仅保留本项目所需 9 个接口）
docs/操作文档.md     # 完整操作文档与 FAQ
```

## 免责声明

> 1. 本项目仅供学习使用，请尊重版权，请勿利用此项目从事商业行为及非法用途!
> 2. 使用本项目的过程中可能会产生版权数据。对于这些版权数据，本项目不拥有它们的所有权。为了避免侵权，使用者务必在 24 小时内清除使用本项目的过程中所产生的版权数据。
> 3. 由于使用本项目产生的包括由于本协议或由于使用或无法使用本项目而引起的任何性质的任何直接、间接、特殊、偶然或结果性损害（包括但不限于因商誉损失、停工、计算机故障或故障引起的损害赔偿，或任何及所有其他商业损害或损失）由使用者负责。
> 4. **禁止在违反当地法律法规的情况下使用本项目。** 对于使用者在明知或不知当地法律法规不允许的情况下，使用本项目所造成的任何违法违规行为由使用者承担，本项目不承担由此产生的任何直接、间接、特殊、偶然或结果性责任。
> 5. 音乐平台不易，请尊重版权，支持正版。
> 6. 本项目仅用于对技术可行性的探索及研究，不接受任何商业（包括但不限于广告等）合作及捐赠。
> 7. 如果官方音乐平台觉得本项目不妥，可联系本项目更改或移除。

## 开源协议

本项目的核心加密逻辑和 API 接口源自以下开源项目，均采用 **MIT License** 发布：

- [MakcRe/KuGouMusicApi](https://github.com/MakcRe/KuGouMusicApi) — MIT License, Copyright (c) 2023 MakcRe
- [develop202/kgcheckin](https://github.com/develop202/kgcheckin) — 签到流程设计

根据 MIT 协议要求，上述版权声明和许可声明已包含在本项目中。本项目同样采用 **MIT License** 发布。

## 致谢

- 感谢 [@MakcRe](https://github.com/MakcRe) 提供 KuGouMusicApi 源代码（加密算法、签名机制、API 接口）
- 感谢 [@develop202](https://github.com/develop202/kgcheckin) Node.js 版本提供思路
