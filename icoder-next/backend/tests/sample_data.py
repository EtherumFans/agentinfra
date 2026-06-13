"""Shared sample clinical text for tests + the embed demo.

Crafted so the deterministic pipeline yields a clear primary (慢性心力衰竭 → I50.900),
two high-risk candidates (M80.900 病理性骨折, 45.1600x001 胃镜活检), and embedded PHI
(姓名/住院号/手机) to exercise redaction.
"""

SAMPLE_TEXT = (
    "主要诊断：慢性心力衰竭，心功能Ⅲ级。\n"
    "其他诊断：高血压病，2型糖尿病，慢性肾脏病，心房颤动。\n"
    "手术操作：胃镜检查及活检。\n"
    "影像学：X线提示骨质疏松伴病理性骨折。\n"
    "患者姓名：张三，住院号：ZY20260613，联系电话：13800001111。"
)
