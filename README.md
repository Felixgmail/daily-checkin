# Daily Checkin

每日自动签到框架,跑在 GitHub Actions 上,完全免费、不占用本地资源。

## 特性

- 🔌 **插件式** —— 每个站点一个 Python 文件,自动发现自动执行
- 🕗 **反风控调度** —— 启动延迟 0-40 分钟随机 + 同站账号 3-15 分钟间隔 + 顺序随机
- 📩 **多通道通知** —— Server酱 / Bark / Telegram,按需配置
- 🔒 **凭据安全** —— 所有 Cookie/Token 走 GitHub Secrets,不进代码不进日志
- 🧱 **容错** —— 单个站点失败不影响其他站点,未配置凭据的自动跳过

## 项目结构

```
daily-checkin/
├── main.py                    # 入口: 发现任务 → 执行 → 汇总 → 通知
├── checkins/                  # 签到任务目录(新增站点放这里)
│   ├── base.py                # 任务基类 CheckinTask
│   ├── _newapi.py             # New API 通用基类(供 makelove/jiuuij 等站点复用)
│   ├── self_check.py          # 自检任务(验证框架,可删)
│   ├── makelove_cloud.py      # newapi.makelove.cloud
│   ├── aichuyel_cn.py         # ai.chuyel.cn
│   ├── jiuuij_de5_net.py      # jiuuij.de5.net
│   └── dialoguedui.py         # token.dialoguedui.com (小怼Code)
├── notify/                    # 通知模块
│   └── __init__.py
├── .github/workflows/
│   └── checkin.yml            # GitHub Actions 配置
├── requirements.txt
└── README.md
```

## 配置 Secrets

到 GitHub 仓库 → **Settings → Secrets and variables → Actions → New repository secret** 添加:

### 站点凭据(按需)

| Secret 名 | 说明 |
|---|---|
| `MAKELOVE_<账号名>_TOKEN` | newapi.makelove.cloud 该账号的 Access Token |
| `MAKELOVE_<账号名>_USER_ID` | newapi.makelove.cloud 该账号的 user id |
| `AICHUYEL_<账号名>_TOKEN` | ai.chuyel.cn 该账号的 Access Token |
| `AICHUYEL_<账号名>_USER_ID` | ai.chuyel.cn 该账号的 user id |
| `JIUUIJDE5_<账号名>_TOKEN` | jiuuij.de5.net 该账号的 Access Token |
| `JIUUIJDE5_<账号名>_USER_ID` | jiuuij.de5.net 该账号的 user id |
| `DIALOGUEDUI_<账号名>_REFRESH_TOKEN` | token.dialoguedui.com 的 refresh_token(详见下方专节) |
| `GH_PAT` | 有本仓库 Secrets 读写权限的 PAT(仅 dialoguedui 回写轮转 token 用) |

**多账号**: 每个账号一对 Secret,`<账号名>` 全大写(字母+数字+下划线)。例如:
- makelove 账号 a6732413: `MAKELOVE_A6732413_TOKEN` + `MAKELOVE_A6732413_USER_ID`

加新账号时除了加 Secret,还要在 `.github/workflows/checkin.yml` 的 env 块下加一对 `${{ secrets.XXX }}` 引用(GitHub Actions 不会自动注入所有 Secret,必须显式声明)。

> 💡 接入新的 New API 站点(只要响应头有 `X-New-Api-Version` 或 meta `generator=new-api`),
> 在 `checkins/` 下抄一份 `makelove_cloud.py`,改 `site_label`/`base_url`/`env_prefix` 三个参数即可。

### token.dialoguedui.com(小怼Code)—— 特殊:Turnstile + refresh_token 轮转

这个站登录有 **Cloudflare Turnstile 人机验证**,脚本无法自动登录,所以**不能用账号密码**。
它的鉴权是 JWT access_token(24h 过期),只能靠 **refresh_token** 续期(`/api/v1/auth/refresh`,不过 Turnstile)。
签到接口是独立站点 `POST /checkin/api/checkin`(带 `Authorization: Bearer <access_token>`)。

**关键:refresh_token 一次性轮转** —— 用一次就换新的、旧的立即失效。所以需要两个东西:

1. **`DIALOGUEDUI_<账号名>_REFRESH_TOKEN`**:首次的 refresh_token。获取方法:
   浏览器登录 `https://token.dialoguedui.com` → F12 → Console 执行
   `localStorage.getItem('refresh_token')`,把输出(`rt_` 开头那串)填进 Secret。
2. **`GH_PAT`**:一个有本仓库 **Secrets 读写权限**的 fine-grained PAT
   (权限:`Secrets: Read and write` + `Metadata: Read`)。
   workflow 跑完会用它把轮转出的新 refresh_token 自动写回 Secret(否则次日链条断裂)。

> `DIALOGUEDUI_<账号名>_ACCESS_TOKEN` / `_ACCESS_EXP` 这两个 Secret **不用手动配**,
> 由脚本自动维护(用于 access_token 未过期时直接签到、跳过 refresh,减少 rt 轮转)。

**轮转加固**(让长期跑更稳):
- 存量 access_token 没过期就直接签到,**不消费 refresh_token**(正常一天最多轮转一次)。
- 拿到新 rt 立即落盘 `rotated_tokens.env`(在签到之前),签到失败也不丢 rt。
- workflow 回写带读回校验 + 重试;回写失败会让该 step 标红。
- refresh 返回 401(rt 彻底失效,如多端登录互相挤掉)→ 签到结果会标注链断,
  此时按上面方法**重新登录取一次 refresh_token** 更新 Secret 即可(1 分钟操作)。

### 通知通道(任选其一或多个,不配则不推送)

| Secret 名 | 说明 |
|---|---|
| `SERVERCHAN_KEY` | Server酱 SendKey ([申请](https://sct.ftqq.com/)) |
| `BARK_KEY` | Bark 设备 key |
| `BARK_SERVER` | Bark 自建服务器(可选,默认 `https://api.day.app`) |
| `TG_BOT_TOKEN` | Telegram Bot Token |
| `TG_CHAT_ID` | Telegram Chat ID |

## 手动触发

到 **Actions → Daily Checkin → Run workflow** 即可立即跑一次,用来验证 Secrets 配得对不对。

## 修改定时

`.github/workflows/checkin.yml` 里的 cron 是 **UTC 时间**:

```yaml
- cron: '0 0 * * *'   # UTC 0:00 = 北京 8:00 唤醒
```

> ⚠️ GitHub Actions 的定时任务在高峰期可能延迟几分钟到几十分钟,这是平台限制,不是 bug。

## 反风控调度策略

为了避免被站点识别为"批量签到机器人":

1. **启动随机延迟 0-40 分钟** —— cron 在 8:00 唤醒,实际开跑在 8:00-8:40 之间随机
2. **同一站点账号串行 + 间隔 3-15 分钟随机** —— 例如 makelove 三个账号不会同时打,每两个之间等 3-15 分钟
3. **同站账号顺序随机** —— 每天先签谁后签谁不固定
4. **不同站点并行** —— makelove / jiuuij 等互不阻塞,各自按各自节奏走;同一账号在不同站点是同时签到的,因为风控只在同站内生效

参数定义在 `main.py` 顶部的 `STARTUP_DELAY_MAX` / `SAMEMSITE_GAP_MIN` / `SAMEMSITE_GAP_MAX`。

**手动触发(workflow_dispatch)和本地直接跑会跳过启动延迟**,方便快速验证。
本地测试时设环境变量 `CHECKIN_FAST=1` 可跳过所有间隔(立即跑完)。

**预算估算**(GitHub Actions 私有仓库免费 2000 分钟/月):
- 站点并行,所以 job 时长 ≈ 启动延迟(0-40 分) + max(各站串行耗时) + 收尾,与账号总数关系不大
- 当前最大单站是 makelove 的 3 账号 → 最坏 ~30 分钟同站间隔,加启动延迟 job 上限约 70 分钟
- 多账号实际平均每天 ~40 分钟,每月 ~1200 分钟,远在 2000 分钟额度内

## 添加新的签到站点

1. 在 `checkins/` 下新建 `xxx.py`
2. 定义一个继承 `CheckinTask` 的类:

```python
from checkins.base import CheckinTask, CheckinResult

class MySiteTask(CheckinTask):
    name = "我的站点"
    required_env = ["MYSITE_TOKEN"]  # 需要的环境变量

    def check_in(self) -> CheckinResult:
        token = self.env["MYSITE_TOKEN"]
        # ... 发请求 ...
        return CheckinResult(self.name, success=True, message="签到成功 +10 积分")
```

3. 在 `.github/workflows/checkin.yml` 的 `env:` 块下加一行:
   ```yaml
   MYSITE_TOKEN: ${{ secrets.MYSITE_TOKEN }}
   ```
4. 到 GitHub 仓库添加对应的 Secret
5. 提交推送即可

## 本地测试

```bash
pip install -r requirements.txt
python main.py

# 测试单站点单账号(其他未配置的会自动跳过)
MAKELOVE_A6732413_TOKEN='xxx' MAKELOVE_A6732413_USER_ID='952' python main.py
```

## 凭据维护

**New API 站点(makelove / uu6 等)的 Access Token 是长效的,不会过期**,只在以下情况需要更新:
1. 你在网站个人设置里**手动重置了 token**
2. 站点管理员升级或重置了 token(极少发生)

判断 token 是否失效: workflow 跑出来报错 `Access Token 已失效或被重置` 时,重新登录浏览器
GET `/api/user/token` 拿新值,然后 `gh secret set <NAME> --repo Felixgmail/daily-checkin --body '新token'`
即可,无需重新部署或改代码。

## 常见问题

**Q: cron 不准时?**
A: GitHub Actions 的免费 cron 高峰期可能延迟,这是平台行为。如果非要准时,改成自己的服务器跑或加更细的 cron。

**Q: 仓库要不要保持 active?**
A: GitHub Actions 在仓库 60 天无任何提交时会自动停掉定时任务,需要 push 一个 commit 来唤醒。可以加个每月自动提交的 workflow 续命,但通常你手动改点东西就够了。

## 公开仓库安全加固

本仓库 **可以安全公开**:所有凭据都在 GitHub Actions Secrets 里,不进代码、不进日志、不进 git 历史(`.gitignore` 已拦轮转落盘文件)。
公开后他人无法读取你的 Secrets,但可以发起 PR 触发 workflow,所以必须把 Actions 入口收紧,防止有人借 workflow 在你的仓库里执行任意命令(尤其是 dialoguedui 回写那步带 `GH_PAT`)。

公开前 **必须** 在仓库 **Settings** 里设置:

1. **Settings → Actions → General → Workflow permissions**:
   - 设为 **Read repository contents and packages permissions**(默认只读),或至少不要给 **Read and write**。
   - 关闭 **Allow GitHub Actions to create and approve pull requests**。

2. **Settings → Actions → General → Fork pull request workflows**:
   选 **Run workflows from fork pull requests** = **Require approval for all external contributors**,
   外部 PR 的 workflow 不会自动跑,需你审批 —— 这一步是关键,能挡住 PR 投毒触发 `GH_PAT`。

3. **Settings → Branches → Branch protection rules → `main`**:
   - **Require a pull request before merging** + **Require approvals**(至少 1)
   - **Require status checks to pass** 勾上
   - 限制 **Restrict who can push to matching branches**,防止他人直接 push workflow 改动。

4. **`GH_PAT` 改用 fine-grained PAT**(若还没):
   - 限定只授权本仓库
   - 权限:`Secrets: Read and write` + `Metadata: Read`,不勾 `Contents: write` 等多余权限。
   - 定期轮换。

5. 还可加 `.github/workflows` 的 **CODEOWNERS**(`.github/CODEOWNERS`),对 workflow 改动强制 review:
   ```
   /.github/workflows/  @你的用户名
   ```

> 确认历史无敏感泄露:仓库历史已扫描,无硬编码令牌。只要 Secrets 不被有写权限者泄露,公开安全。


---

## 附:已接入站点的接口侦察记录

留作以后维护/调试时参考。

### New API 通用基类 (`checkins/_newapi.py`)
所有基于 [New API](https://github.com/QuantumNous/new-api) (含 One API 衍生)的站点共用同一套接口:
- 鉴权: `Authorization: Bearer <access_token>` + `New-Api-User: <id>` (Bearer 前缀可省)
- 签到: `POST /api/user/checkin`
  - 成功: `{"success":true,"data":{"checkin_date":"...","quota_awarded":...}}`
  - 已签: `{"success":false,"message":"今日已签到"}`
- 用户信息: `GET /api/user/self` → `data.quota`,余额 ≈ `quota / 500000` USD
- 获取 access token: 浏览器登录 → `/console/personal` 找 Access Token; 或登录后 GET `/api/user/token`
- 识别方法: 响应头有 `X-New-Api-Version`,或 HTML meta 有 `generator=new-api`

### newapi.makelove.cloud (`checkins/makelove_cloud.py`)
版本 `v1.0.0-rc.6-makelove.1`。
- **⚠️ IP 风控两层**(其他 New API 站点不一定有):
  1. `/api/user/login` 在 GitHub Actions 的 Azure ASN(AS8075) 上直接拒登("用户名或密码错误,或用户已被封禁",即使密码对)
  2. session cookie 绑定登录 IP, 跨 IP 复用 cookie 返回 401 "无权进行此操作"
- **Access Token 不受此风控影响**(token 鉴权不绑 IP),所以本框架统一用 token

