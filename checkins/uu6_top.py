"""api.uu6.top 签到 (基于 New API,meta generator=new-api),支持多账号。

接口/鉴权与 makelove.cloud / 52mx.net 完全相同(同一套 New API 代码),
复用 _newapi.NewAPITask。该站走 Cloudflare,未见明显 IP 风控,
但仍统一使用 access token,与其他 New API 站点保持一致。

多账号配置:
   每个账号一对 Secret: UU6_<账号名>_TOKEN + UU6_<账号名>_USER_ID
   例如:
     UU6_A6732413_TOKEN  ↔  UU6_A6732413_USER_ID

获取 access token:
   浏览器登录 https://api.uu6.top → /console/personal 找 Access Token,
   或登录后 GET /api/user/token 直接拿 data 字段。
"""
from checkins._newapi import build_tasks_for_site

tasks = build_tasks_for_site(
    site_label="uu6.top",
    base_url="https://api.uu6.top",
    env_prefix="UU6",
)
