"""造演示基线：给总览页的评价条留一组真实数字。

重置演示数据会清空记忆库，评价条就变成「还没有人评价」。线下展示时那一条
本来是最能说明「有真实用户在用」的证据，所以重置之后补一组种子评价。

刻意做成 8 条、6 好 2 差：全是好评反而不可信，留两条具体的差评更像真话。
"""

import asyncio
import sys

import httpx

BASE = "http://127.0.0.1:8000"

# (user_id, target, helpful, note)
SEEDS = [
    ("demo-student", "doc_normalize", True, ""),
    ("demo-student-2", "doc_normalize", True, ""),
    ("demo-student-3", "doc_normalize", False, "表格里的字号没跟着改"),
    ("demo-student-4", "interview_report", True, ""),
    ("demo-student-5", "interview_report", False, "英语题太少，英语水平那项基本没测到"),
    ("demo-student-6", "credit_warning", True, ""),
    ("demo-student-7", "proposal_outline", True, ""),
    ("demo-student-8", "wellbeing_chat", True, ""),
]


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        health = await client.get("/healthz")
        if health.status_code != 200:
            print("后端没起来，先启动后端再跑这个脚本")
            return 1

        for user_id, target, helpful, note in SEEDS:
            response = await client.post(
                "/api/v1/feedback",
                headers={
                    "X-User-Id": user_id,
                    "X-Session-Id": "demo-seed",
                    "X-User-Role": "student",
                },
                json={"target": target, "helpful": helpful, "note": note},
            )
            if response.status_code != 200:
                print(f"[失败] {user_id} -> {target}: {response.text[:120]}")
                return 1

        summary = (await client.get("/api/v1/feedback/summary")).json()["data"]
        print(f"评价种子写入完成：{summary['total']} 条，有用率 {summary['rate']}%")
        for item in summary["by_target"]:
            print(f"  - {item['target_name']}: {item['total']} 条 / {item['rate']}%")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
