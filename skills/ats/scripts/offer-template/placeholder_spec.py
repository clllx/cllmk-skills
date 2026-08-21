#!/usr/bin/env python3
from __future__ import annotations

"""
Offer 附件模板占位符规格：标准变量枚举表 + 占位符编解码规则。

被 build_offer_docx.py 与 validate_placeholders.py 共用。本模块不发任何网络请求。

标准变量表来源：前端 bundle（`hrWeb-<ver>-release.js`）里的变量枚举，形如
    de.CANDIDATE_NAME,{name:"候选人姓名",translation:"Candidate name"}
共 37 项。**该表随前端版本变化**；怀疑过期时按主文档「附录 B」重新提取，不要凭记忆增删。
"""

# ---------------------------------------------------------------------------
# 标准变量：占位符写 {名称}，不带字段 ID
# ---------------------------------------------------------------------------

# 业务常用。已由使用方确认可用。
STANDARD_COMMON = (
    "候选人姓名",
    "候选人身份证",
    "候选人手机号",
    "候选人邮箱",
    "创建人姓名",
    "创建人手机号",
    "创建人邮箱",
    "Offer生成日期",
    "公司名称",
    "职位描述",
    "预计入职时间",
    "offer职位",
    "薪资待遇",
    "入职地点",
    "职位级别",
    "入职部门",
    "入职部门路径",
)

# 电子签专用。只在 templateType != 0 的模板里有意义。
# 注意：这些**不出现**在 UI「查看字段」列表里，但实测可用（已落库的电子签模板
# occurrences 里含「个人签署区」「公章签署区」）。
STANDARD_SIGNATURE = (
    "个人签署区",
    "公章签署区",
    "人事章签署区",
    "人名章签署区",
    "合同章签署区",
    "法人章签署区",
    "公司签署人1",
    "公司签署人2",
    "公司签署人3",
    "公司签署时间_1",
    "公司签署时间_2",
    "公司签署时间_3",
    "人选签署时间",
    "个人签署文本字段",
    "公司签署1文本字段",
    "公司签署2文本字段",
    "公司签署3文本字段",
)

# ⚠️ 可用性未知：在前端枚举表里，但既不在 UI「查看字段」列表里，也没有实测过替换。
# 使用前必须向用户明示这一点，不要当作已验证能力。
STANDARD_UNVERIFIED = (
    "候选人最高学历毕业院校",
    "候选人专业（最高学历）",
    "候选人最高学历",
)

STANDARD_VARIABLES = STANDARD_COMMON + STANDARD_SIGNATURE + STANDARD_UNVERIFIED

# 附件标题（attachmentTitle）可选的纯前端变量。正文可用的比这多，见主文档 §4。
ATTACHMENT_TITLE_INJECTED = (
    "候选人姓名",
    "候选人身份证",
    "候选人手机号",
    "候选人邮箱",
    "创建人姓名",
    "创建人手机号",
    "创建人邮箱",
    "Offer生成日期",
    "公司名称",
)

# Offer 字段中不能作为占位符的 type（附件、人员选择、招聘需求、附件发送开关）。
# 实测这些 type 被 UI 从占位符清单里排除。
NON_PLACEHOLDER_FIELD_TYPES = frozenset({5, 8, 11, 12})


# ---------------------------------------------------------------------------
# 空格编码
# ---------------------------------------------------------------------------


def encode_placeholder_name(name: str) -> str:
    """把字段名编码成占位符里的形式。

    实测只有空格被转成 %20；全角/半角括号、斜杠、连字符等一律原样保留
    （所以**不是** urllib.parse.quote）。连续空格逐个转。

    >>> encode_placeholder_name("Annual Leave")
    'Annual%20Leave'
    >>> encode_placeholder_name("基本薪资（元/月）")
    '基本薪资（元/月）'
    """
    return name.replace(" ", "%20")


def decode_placeholder_name(encoded: str) -> str:
    """encode_placeholder_name 的逆操作。"""
    return encoded.replace("%20", " ")


def build_placeholder(name: str, field_id: int | None = None) -> str:
    """按名称与可选字段 ID 拼出占位符（含花括号）。

    field_id 为 None 时按标准变量处理（不带 ID）。判据是「名称是否在
    STANDARD_VARIABLES 里」，**不是** Offer 字段的 isBuiltin / builtinType。
    """
    encoded = encode_placeholder_name(name)
    if field_id is None:
        return "{" + encoded + "}"
    return "{" + f"{encoded}[{field_id}]" + "}"
