"""ai.chuyel.cn 签到,支持多账号。

基于标准 New API 架构,复用 _newapi.py 的通用逻辑。

多账号配置:
  每个账号一对 Secret: AICHUYEL_<账号名>_TOKEN + AICHUYEL_<账号名>_USER_ID
  例如:
    AICHUYEL_BUTUISEDECHENGNUO_TOKEN  ↔  AICHUYEL_BUTUISEDECHENGNUO_USER_ID
"""
from checkins._newapi import build_tasks_for_site

SITE_LABEL = "ai.chuyel.cn"
BASE_URL = "https://ai.chuyel.cn"
ENV_PREFIX = "AICHUYEL"

tasks = build_tasks_for_site(SITE_LABEL, BASE_URL, ENV_PREFIX)
