"""jiuuij.de5.net 签到,支持多账号。

基于标准 New API 架构,复用 _newapi.py 的通用逻辑。

多账号配置:
  每个账号一对 Secret: JIUUIJDE5_<账号名>_TOKEN + JIUUIJDE5_<账号名>_USER_ID
  例如:
    JIUUIJDE5_LINUXDO21000_TOKEN  ↔  JIUUIJDE5_LINUXDO21000_USER_ID
"""
from checkins._newapi import build_tasks_for_site

SITE_LABEL = "jiuuij.de5.net"
BASE_URL = "https://jiuuij.de5.net"
ENV_PREFIX = "JIUUIJDE5"

tasks = build_tasks_for_site(SITE_LABEL, BASE_URL, ENV_PREFIX)
