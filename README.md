# Daily Checkin

每日自动签到框架,跑在 GitHub Actions 上,完全免费、不占用本地资源。

## 特性

- 🔌 **插件式** —— 每个站点一个 Python 文件,自动发现自动执行
- 🕗 **定时触发** —— GitHub Actions cron 每天北京时间 8:07 自动跑
- 📩 **多通道通知** —— Server酱 / Bark / Telegram,按需配置
- 🔒 **凭据安全** —— 所有 Cookie/Token 走 GitHub Secrets,不进代码不进日志
- 🧱 **容错** —— 单个站点失败不影响其他站点,未配置凭据的自动跳过

## 项目结构

```
daily-checkin/
├── main.py                    # 入口: 发现任务 → 执行 → 汇总 → 通知
├── checkins/                  # 签到任务目录(新增站点放这里)
│   ├── base.py                # 任务基类 CheckinTask
│   ├── self_check.py          # 自检任务(验证框架,可删)
│   └── v2ex.py                # V2EX 签到示例
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
| `V2EX_COOKIE` | V2EX 登录后浏览器中的整段 Cookie |
| `MAKELOVE_USERNAME` | newapi.makelove.cloud 用户名 |
| `MAKELOVE_PASSWORD` | newapi.makelove.cloud 密码 |

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
- cron: '7 0 * * *'   # 北京时间 8:07
```

> ⚠️ GitHub Actions 的定时任务在高峰期可能延迟几分钟到几十分钟,这是平台限制,不是 bug。

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

# 选填环境变量来测试单个签到
export V2EX_COOKIE="..."

python main.py
```

## 常见问题

**Q: cron 不准时?**
A: GitHub Actions 的免费 cron 高峰期可能延迟,这是平台行为。如果非要准时,改成自己的服务器跑或加更细的 cron。

**Q: V2EX 签到提示 Cookie 失效?**
A: V2EX 的 cookie 有效期长但不是永久,失效后重新登录浏览器,F12 复制 Cookie 整段更新到 Secrets。

**Q: 仓库要不要保持 active?**
A: GitHub Actions 在仓库 60 天无任何提交时会自动停掉定时任务,需要 push 一个 commit 来唤醒。可以加个每月自动提交的 workflow 续命,但通常你手动改点东西就够了。

---

## 附:已接入站点的接口侦察记录

留作以后维护/调试时参考。

### V2EX (`checkins/v2ex.py`)
- 鉴权: 浏览器 Cookie
- 流程: `GET /mission/daily` 提取 `once` token → `GET /mission/daily/redeem?once=xxx`
- 已签判断: 页面包含 `每日登录奖励已领取`
- Cookie 失效特征: 找不到 once 正则

### newapi.makelove.cloud (`checkins/makelove_cloud.py`)
基于 [New API](https://github.com/QuantumNous/new-api) 衍生版 `v1.0.0-rc.6-makelove.1`。
- 登录: `POST /api/user/login {"username","password"}` → 设置 session Cookie,响应 `data.id` 是用户 id
- 鉴权: **session Cookie + `New-Api-User: <id>` header** 双因子。少任一都会返回 `Unauthorized, New-Api-User header not provided`
- 签到: `POST /api/user/checkin`
  - 成功: `{"success":true,"message":"...","data":{...}}`
  - 已签: `{"success":false,"message":"今日已签到"}`
- 用户信息: `GET /api/user/self` → `data.quota`,余额 ≈ `quota / 500000` USD
