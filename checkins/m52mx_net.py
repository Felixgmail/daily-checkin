"""52mx.net 签到 (基于 New API,X-New-Api-Version: v1.0.0-rc.8),支持多账号。

接口/鉴权与 makelove.cloud 完全相同(同一套 New API 代码),复用 _newapi.NewAPITask。
该站登录接口未发现 IP 风控,但仍然推荐用 access token,与 makelove 保持一致。

多账号配置:
   每个账号一对 Secret: M52MX_<账号名>_TOKEN + M52MX_<账号名>_USER_ID
   (Secret 名不能以数字开头,所以加了 M 前缀)
   例如:
     M52MX_A6732413_TOKEN  ↔  M52MX_A6732413_USER_ID
     M52MX_LINFANGJI_TOKEN ↔  M52MX_LINFANGJI_USER_ID

获取 access token:
   浏览器登录 https://52mx.net,F12 调 GET /api/user/token,
   响应 data 字段就是 token。或在个人设置里找系统访问令牌。
"""
from checkins._newapi import build_tasks_for_site

tasks = build_tasks_for_site(
    site_label="52mx.net",
    base_url="https://52mx.net",
    env_prefix="M52MX",
)
