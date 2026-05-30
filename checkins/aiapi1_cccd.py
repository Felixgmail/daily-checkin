"""aiapi1.cc.cd (ai api) 签到 (标准 New API),支持多账号。

接口与 makelove/52mx 等完全一致(都是 New API):
   Authorization: Bearer <access_token> + New-Api-User: <user_id> 鉴权,
   POST /api/user/checkin 签到。turnstile_check=false,无人机验证。
   走 Cloudflare,但 access token 鉴权不受登录 IP 风控影响。

多账号配置:
   每个账号一对 Secret: AIAPI1_<账号名>_TOKEN + AIAPI1_<账号名>_USER_ID
   <账号名> 全大写(字母/数字)。例如:
     AIAPI1_A6732413_TOKEN   ↔  AIAPI1_A6732413_USER_ID
     AIAPI1_LIYANGFENG_TOKEN ↔  AIAPI1_LIYANGFENG_USER_ID

获取 access token:
   账号密码登录 → 带 New-Api-User 头 GET /api/user/token 拿 data 字段;
   user_id 取登录响应 data.id。
"""
from checkins._newapi import build_tasks_for_site

tasks = build_tasks_for_site(
    site_label="aiapi1.cc.cd",
    base_url="https://aiapi1.cc.cd",
    env_prefix="AIAPI1",
)
