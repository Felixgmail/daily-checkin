"""newapi.makelove.cloud 签到 (基于 New API 的衍生版),支持多账号。

⚠️ 该站对 GitHub Actions 的 Azure IP 段做了登录风控:
   1) /api/user/login 直接拒登("用户名或密码错误,或用户已被封禁",即使密码正确)
   2) session cookie 绑定登录 IP,跨 IP 复用会被拒(401 "无权进行此操作")
   因此本脚本使用 access token 鉴权(见 checkins/_newapi.py)。

多账号配置:
   每个账号一对 Secret: MAKELOVE_<账号名>_TOKEN + MAKELOVE_<账号名>_USER_ID
   <账号名> 全大写(字母/数字)。例如:
     MAKELOVE_A6732413_TOKEN  ↔  MAKELOVE_A6732413_USER_ID
     MAKELOVE_JDUHG82736_TOKEN ↔  MAKELOVE_JDUHG82736_USER_ID

获取 access token:
   浏览器登录 → /console/personal 找 Access Token,
   或登录后 GET /api/user/token 直接拿 data 字段。
"""
from checkins._newapi import build_tasks_for_site

tasks = build_tasks_for_site(
    site_label="makelove.cloud",
    base_url="https://newapi.makelove.cloud",
    env_prefix="MAKELOVE",
)
