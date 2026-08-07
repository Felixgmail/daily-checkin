"""api.hcnsec.cn 签到,支持多账号。

基于 One API / New API 架构(响应头 x-oneapi-request-id),复用 _newapi.py 的通用逻辑。

多账号配置:
  每个账号一对 Secret: HCNSEC_<账号名>_TOKEN + HCNSEC_<账号名>_USER_ID
  例如:
    HCNSEC_LINDINGCHAN_TOKEN  ↔  HCNSEC_LINDINGCHAN_USER_ID
    HCNSEC_FELIXSSFDF_TOKEN   ↔  HCNSEC_FELIXSSFDF_USER_ID
"""
from checkins._newapi import build_tasks_for_site

SITE_LABEL = "api.hcnsec.cn"
BASE_URL = "https://api.hcnsec.cn"
ENV_PREFIX = "HCNSEC"

tasks = build_tasks_for_site(SITE_LABEL, BASE_URL, ENV_PREFIX)
