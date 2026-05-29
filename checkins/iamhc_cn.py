"""api.iamhc.cn 签到 (基于 New API,x-new-api-version: v1.0.0-rc.6),支持多账号。

接口/鉴权与其他 New API 站点(makelove / 52mx / uu6 / tokenwork)完全相同,
复用 _newapi.NewAPITask。

多账号配置:
   每个账号一对 Secret: IAMHC_<账号名>_TOKEN + IAMHC_<账号名>_USER_ID
   例如:
     IAMHC_LINDINGCHAN_TOKEN  ↔  IAMHC_LINDINGCHAN_USER_ID

获取 access token:
   浏览器登录 https://api.iamhc.cn → /console/personal 找 Access Token,
   或登录后 GET /api/user/token 直接拿 data 字段。
"""
from checkins._newapi import build_tasks_for_site

tasks = build_tasks_for_site(
    site_label="iamhc.cn",
    base_url="https://api.iamhc.cn",
    env_prefix="IAMHC",
)
