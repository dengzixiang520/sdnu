# -*- coding: utf-8 -*-
"""把直链、亮点、备赛路线合并进 data/competitions.json（并同步 demo_baseline）。

与上一版相比：documents 里的「搜索链接」全部替换为真实可跳转的官方/通知/平台链接。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comp_links_a import LINKS_A  # noqa: E402
from comp_links_b import LINKS_B  # noqa: E402

LINKS = {**LINKS_A, **LINKS_B}
TARGETS = [Path("data/competitions.json"), Path("data/demo_baseline/competitions.json")]

# 兜底入口：极少数条目若既无官网也无通知页，用它保证「点得开」，而不是搜索页。
FALLBACK = {"title": "山东师范大学官网（竞赛通知入口）", "url": "https://www.sdnu.edu.cn", "kind": "platform"}


def main() -> None:
    for target in TARGETS:
        if not target.exists():
            print(f"skip {target}")
            continue
        entries = json.loads(target.read_text(encoding="utf-8"))
        changed = 0
        for entry in entries:
            extra = LINKS.get(entry["id"])
            if not extra:
                continue
            links = list(extra["links"])
            if not links:
                links = [FALLBACK]
            # 官网链接同步到 website 字段，前端「访问官网」按钮直接跳转
            official = next((link for link in links if link["kind"] == "official"), None)
            entry["website"] = official["url"] if official else links[0]["url"]
            entry["documents"] = links
            entry["highlights"] = extra["highlights"]
            entry["prep"] = extra["prep"]
            changed += 1
        target.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # 校验：不能残留 bing 搜索链接
        raw = target.read_text(encoding="utf-8")
        leftover = raw.count("bing.com/search")
        print(f"{target}: 更新 {changed} 条，残留搜索链接 {leftover} 处")


if __name__ == "__main__":
    main()
