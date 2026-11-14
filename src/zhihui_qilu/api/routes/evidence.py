"""规则依据路由：线下展示时评委最常追问的一页。

读接口公开，不含任何个人数据，只有出处。
"""

from typing import Any

from fastapi import APIRouter

from zhihui_qilu.evidence_service import evidence_payload

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])


@router.get("")
async def list_evidence() -> dict[str, Any]:
    """返回分组后的规则出处清单。"""
    return {"success": True, "data": evidence_payload()}
