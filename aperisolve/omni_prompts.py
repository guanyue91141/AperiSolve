"""Shared quick-solve instructions for fresh and resumed ALL-mode tasks."""

# ruff: noqa: RUF001 -- Chinese task instructions use Chinese punctuation.

from pathlib import Path


def problem_prompt(task: Path, uploads: list[dict], instructions: str) -> str:
    """Keep the current problem and output contract independent of session history."""
    attachments = "\n".join(f"- {task / item['path']}" for item in uploads) or "（无附件）"
    instruction_section = f"\n用户解题说明原文：\n{instructions}\n" if instructions.strip() else ""
    return (
        "ALL mode 以快速获得答案为目标，请直接解题并自主推进。"
        "可随时搜索工具文档、技术资料和公开题解，直接采用适用思路；"
        "无需先独立分析，也无需完整重跑参考题解。\n"
        "完成必要核对，确认资料适用于本题附件或目标；不要照搬其他实例的动态 flag。"
        "答案前缀、大小写和包装方式遵循题面或提取内容，不凭惯例补造。\n"
        "可以安装任意解题所需工具，并在当前任务环境中使用；先检查已有工具和解释器。\n"
        f"任务工作目录（绝对路径）：{task}\n"
        "每条解题命令使用本题绝对路径或先切换到本题目录，"
        "所有解题文件和临时产物写在本题目录内。"
        "不要读取其他任务的附件、答案或题解来推断本题结论。\n"
        f"附件（绝对路径）：\n{attachments}\n"
        + instruction_section
        + f"\n找到答案并完成必要核对后，立即将答案原文写入 {task / 'flag-re.txt'}。"
        "每行一个答案，不要写说明或 Markdown；多问题按题面顺序输出，"
        "密码、命令、数字等答案保留原样。"
        f"随后将简明解题过程、关键命令或脚本路径另存 {task / 'solution.txt'}。"
        "若未找到答案，保存已取得的进展与原因，不要编造答案或将无依据猜测写入 flag-re.txt。"
        "这是无人值守任务，将缺失信息和错误写入日志，自主选择可行方法继续推进。\n"
    )
