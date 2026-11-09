"""把演示数据恢复到基线状态。

用法（在 code 目录下）：
    runtime\\python\\python.exe reset_demo_data.py

为什么要这个脚本：
    积分打卡、兑换记录、课表解析、三层记忆都是**会持久化**的。反复排练之后，
    "今日已打卡" 会被占掉、商品库存会被换空、预警列表会堆积历史记录，现场演示
    的起点就不再干净。跑一次本脚本即可回到首次启动的状态。

它做什么：
    1. 用 data/demo_baseline/ 里的快照覆盖业务数据（竞赛库、商品、积分、课表）；
    2. 删除三层记忆的 SQLite 文件（ZHQ_MEMORY_BACKEND=sqlite 时生效）；
    3. 删除兑换记录 exchange_records.json（如果存在）。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

BASELINE_FILES = (
    "competitions.json",
    "new_competitions.json",
    "exchange_products.json",
    "points.json",
    "points_records.json",
    "timetable.json",
)

# 只删除、不从基线恢复的运行时产物
RUNTIME_FILES = (
    "zhihui_qilu_memory.sqlite3",
    "zhihui_qilu_memory.sqlite3-wal",
    "zhihui_qilu_memory.sqlite3-shm",
    "exchange_records.json",
)


def main() -> int:
    code_dir = Path(__file__).resolve().parent
    data_dir = code_dir / "data"
    baseline_dir = data_dir / "demo_baseline"

    if not baseline_dir.is_dir():
        print(f"[错误] 找不到基线目录: {baseline_dir}")
        return 1

    restored = 0
    for name in BASELINE_FILES:
        source = baseline_dir / name
        if not source.is_file():
            print(f"[跳过] 基线缺少 {name}")
            continue
        shutil.copyfile(source, data_dir / name)
        print(f"[恢复] {name}")
        restored += 1

    removed = 0
    locked: list[str] = []
    for name in RUNTIME_FILES:
        target = data_dir / name
        if not target.is_file():
            continue
        try:
            target.unlink()
            print(f"[清除] {name}")
            removed += 1
        except OSError:
            # Windows 下后端进程会独占 sqlite 文件；此时明确告诉用户该关哪个窗口，
            # 而不是抛一串 traceback 让人以为脚本坏了。
            locked.append(name)
            print(f"[占用] {name} 正被后端进程使用，未能删除")

    print()
    print(f"完成：恢复 {restored} 个数据文件，清除 {removed} 个运行时文件。")
    if locked:
        print()
        print("注意：以下文件被占用，记忆库未清空——")
        for name in locked:
            print(f"  - {name}")
        print("请先关闭 ZHQ-Backend 窗口（或停掉 uvicorn），再运行一次本脚本。")
        print("业务数据（积分、库存、课表）已恢复，不受影响。")
        return 1

    print("下次启动即为干净的演示基线。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
