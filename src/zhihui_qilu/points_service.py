"""Points and badge system service."""

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PointsRecord(BaseModel):
    """Points record model."""
    id: str = ""
    user_id: str
    user_name: str = ""
    points: int
    source: str  # "competition", "checkin", "activity"
    source_detail: str = ""
    created_at: str = ""


class UserPoints(BaseModel):
    """User points summary."""
    user_id: str
    user_name: str
    total_points: int = 0
    competition_points: int = 0
    checkin_points: int = 0
    activity_points: int = 0
    badges: list[str] = Field(default_factory=list)
    level: str = "新手"


class Badge(BaseModel):
    """Badge definition."""
    id: str
    name: str
    description: str
    icon: str
    requirement: int  # points needed
    category: str = "general"


# 积分规则
POINTS_RULES = {
    # 竞赛获奖积分
    "A1": 100, "A2": 80, "A3": 60,
    "B1": 50, "B2": 40, "B3": 30,
    "C1": 20, "C2": 15, "C3": 10,
    "D1": 8, "D2": 5, "D3": 3,
    # 打卡积分
    "checkin": 5,
    "checkin_streak_7": 20,
    "checkin_streak_30": 100,
}

# 徽章定义
BADGES = [
    {"id": "newcomer", "name": "初来乍到", "description": "获得首个积分", "icon": "🌱", "requirement": 1, "category": "general"},
    {"id": "active", "name": "活跃分子", "description": "累计获得100积分", "icon": "⭐", "requirement": 100, "category": "general"},
    {"id": "enthusiast", "name": "热心参与者", "description": "累计获得500积分", "icon": "🔥", "requirement": 500, "category": "general"},
    {"id": "expert", "name": "竞赛达人", "description": "累计获得1000积分", "icon": "🏆", "requirement": 1000, "category": "competition"},
    {"id": "master", "name": "竞赛大师", "description": "累计获得2000积分", "icon": "👑", "requirement": 2000, "category": "competition"},
    {"id": "streak7", "name": "坚持一周", "description": "连续打卡7天", "icon": "📅", "requirement": 0, "category": "checkin"},
    {"id": "streak30", "name": "月度坚持", "description": "连续打卡30天", "icon": "🗓️", "requirement": 0, "category": "checkin"},
    {"id": "competitor", "name": "参赛选手", "description": "参加过1次竞赛", "icon": "🎯", "requirement": 0, "category": "competition"},
    {"id": "winner", "name": "获奖选手", "description": "获得过1次奖项", "icon": "🥇", "requirement": 0, "category": "competition"},
]

# 等级定义
LEVELS = [
    (0, "新手"),
    (100, "入门"),
    (300, "进阶"),
    (500, "熟练"),
    (1000, "精通"),
    (2000, "大师"),
]


class PointsService:
    """Service for managing points and badges."""

    def __init__(self, data_dir: str | Path = "./data") -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._points_file = self._data_dir / "points.json"
        self._records_file = self._data_dir / "points_records.json"
        # JSON 文件没有事务，读-改-写必须串行化；否则并发打卡/兑换会互相覆盖。
        self._lock = threading.RLock()
        self._ensure_files()

    def _ensure_files(self) -> None:
        if not self._points_file.exists():
            self._points_file.write_text("[]", encoding="utf-8")
        if not self._records_file.exists():
            self._records_file.write_text("[]", encoding="utf-8")

    def _load_points(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self._points_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_points(self, data: list[dict[str, Any]]) -> None:
        self._points_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_records(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self._records_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_records(self, data: list[dict[str, Any]]) -> None:
        self._records_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_points(self, user_id: str, user_name: str, points: int, source: str, source_detail: str = "") -> dict[str, Any]:
        """Add points to user."""
        with self._lock:
            records = self._load_records()
            record = {
                "id": f"r{len(records) + 1}",
                "user_id": user_id,
                "user_name": user_name,
                "points": points,
                "source": source,
                "source_detail": source_detail,
                "created_at": datetime.now().isoformat()
            }
            records.append(record)
            self._save_records(records)

            # 更新用户总积分
            self._update_user_points(user_id, user_name, points, source)

            return record

    def _update_user_points(self, user_id: str, user_name: str, points: int, source: str) -> None:
        """Update user total points.

        兑换（``source == "exchange"``）只冲减总分，不进入竞赛/打卡/活动任何一个
        贡献分类；早期版本把它落进 ``activity_points`` 并加上负数，导致"总分下降、
        活动积分反而上升"的错误账目。
        """
        points_data = self._load_points()

        user = next((u for u in points_data if u["user_id"] == user_id), None)
        if not user:
            user = {
                "user_id": user_id,
                "user_name": user_name,
                "total_points": 0,
                "competition_points": 0,
                "checkin_points": 0,
                "activity_points": 0,
                "badges": [],
                "level": "新手"
            }
            points_data.append(user)

        user["total_points"] += points
        if source == "competition":
            user["competition_points"] += points
        elif source == "checkin":
            user["checkin_points"] += points
        elif source == "exchange":
            pass  # 兑换是消费，不属于任何贡献分类
        else:
            user["activity_points"] += points

        # 更新等级
        user["level"] = self._calculate_level(user["total_points"])

        # 检查并授予徽章（只增不减，兑换不会回收已得徽章）
        new_badges = self._check_badges(user)
        user["badges"] = list(set(user["badges"] + new_badges))

        self._save_points(points_data)

    def _calculate_level(self, points: int) -> str:
        """Calculate user level based on points."""
        level = "新手"
        for threshold, name in LEVELS:
            if points >= threshold:
                level = name
        return level

    def _check_badges(self, user: dict[str, Any]) -> list[str]:
        """Check and award new badges."""
        new_badges = []
        existing_badges = set(user.get("badges", []))
        
        for badge in BADGES:
            if badge["id"] in existing_badges:
                continue
            
            # 积分类徽章
            if badge["requirement"] > 0 and user["total_points"] >= badge["requirement"]:
                new_badges.append(badge["id"])
        
        return new_badges

    def get_user_points(self, user_id: str) -> dict[str, Any] | None:
        """Get user points summary."""
        points_data = self._load_points()
        return next((u for u in points_data if u["user_id"] == user_id), None)

    def get_leaderboard(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get points leaderboard."""
        points_data = self._load_points()
        sorted_data = sorted(points_data, key=lambda x: x["total_points"], reverse=True)
        return sorted_data[:limit]

    def get_user_records(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get user points records."""
        records = self._load_records()
        user_records = [r for r in records if r["user_id"] == user_id]
        return sorted(user_records, key=lambda x: x["created_at"], reverse=True)[:limit]

    def get_badges(self) -> list[dict[str, Any]]:
        """Get all badge definitions."""
        return BADGES

    def get_points_rules(self) -> dict[str, int]:
        """Get points rules."""
        return POINTS_RULES

    def add_competition_points(self, user_id: str, user_name: str, award_level: str, competition_name: str) -> dict[str, Any]:
        """Add points for competition award."""
        points = POINTS_RULES.get(award_level, 0)
        if points == 0:
            return {"error": "未知的奖项等级"}
        return self.add_points(user_id, user_name, points, "competition", f"{competition_name} - {award_level}")

    def add_checkin_points(self, user_id: str, user_name: str) -> dict[str, Any]:
        """Add points for daily check-in."""
        return self.add_points(user_id, user_name, POINTS_RULES["checkin"], "checkin", "每日打卡")

    # ==================== 积分兑换功能 ====================
    
    def _load_exchange_products(self) -> list[dict[str, Any]]:
        """Load exchange products from JSON file."""
        products_file = self._data_dir / "exchange_products.json"
        if not products_file.exists():
            return []
        try:
            return json.loads(products_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _save_exchange_products(self, products: list[dict[str, Any]]) -> None:
        """Save exchange products to JSON file."""
        products_file = self._data_dir / "exchange_products.json"
        products_file.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def _load_exchange_records(self) -> list[dict[str, Any]]:
        """Load exchange records."""
        records_file = self._data_dir / "exchange_records.json"
        if not records_file.exists():
            return []
        try:
            return json.loads(records_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _save_exchange_records(self, records: list[dict[str, Any]]) -> None:
        """Save exchange records."""
        records_file = self._data_dir / "exchange_records.json"
        records_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    
    def get_exchange_products(self) -> list[dict[str, Any]]:
        """Get all available exchange products."""
        return self._load_exchange_products()
    
    def get_exchange_product(self, product_id: str) -> dict[str, Any] | None:
        """Get exchange product by ID."""
        products = self._load_exchange_products()
        return next((p for p in products if p.get("id") == product_id), None)

    def exchange_product(self, user_id: str, user_name: str, product_id: str) -> dict[str, Any]:
        """Exchange points for a product.

        库存校验、积分扣减与库存落盘在同一把锁内完成，避免并发兑换超卖；
        商品只加载一次，防止校验用的库存和扣减用的库存不是同一份快照。
        """
        with self._lock:
            products = self._load_exchange_products()
            product = next((p for p in products if p.get("id") == product_id), None)
            if product is None:
                return {"success": False, "error": "商品不存在"}

            if product.get("stock", 0) <= 0:
                return {"success": False, "error": "商品已售罄"}

            user = self.get_user_points(user_id)
            if not user:
                return {"success": False, "error": "用户积分记录不存在"}

            cost = int(product.get("points", 0))
            if user["total_points"] < cost:
                return {"success": False, "error": f"积分不足，需要{cost}积分，当前{user['total_points']}积分"}

            # 扣除积分（source=exchange，只冲减总分，不进入贡献分类）
            self.add_points(user_id, user_name, -cost, "exchange", f"兑换: {product.get('name', '')}")

            # 减少库存
            product["stock"] = product.get("stock", 0) - 1
            self._save_exchange_products(products)

            exchange_code = str(uuid.uuid4())[:8].upper()

            records = self._load_exchange_records()
            record = {
                "id": f"ex{len(records) + 1}",
                "user_id": user_id,
                "user_name": user_name,
                "product_id": product_id,
                "product_name": product.get("name", ""),
                "points_cost": cost,
                "exchange_code": exchange_code,
                "exchange_time": datetime.now().isoformat(),
                "pick_up_location": product.get("location", ""),
                "status": "pending"  # pending, claimed, expired
            }
            records.append(record)
            self._save_exchange_records(records)

            return {
                "success": True,
                "exchange_code": exchange_code,
                "product_name": product.get("name", ""),
                "points_cost": cost,
                "pick_up_location": product.get("location", ""),
                "message": f"兑换成功！请凭兑换码 {exchange_code} 到 {product.get('location', '')} 领取"
            }
    
    def get_user_exchanges(self, user_id: str) -> list[dict[str, Any]]:
        """Get user exchange records."""
        records = self._load_exchange_records()
        return [r for r in records if r["user_id"] == user_id]
    
    def claim_exchange(self, exchange_id: str) -> dict[str, Any]:
        """Mark an exchange as claimed. 读-改-写必须在锁内，否则重复领取会互相覆盖。"""
        with self._lock:
            records = self._load_exchange_records()
            for record in records:
                if record.get("id") != exchange_id:
                    continue
                if record.get("status") != "pending":
                    return {"success": False, "error": "该兑换已被处理"}
                record["status"] = "claimed"
                record["claimed_time"] = datetime.now().isoformat()
                self._save_exchange_records(records)
                return {"success": True, "message": "已确认领取"}
            return {"success": False, "error": "兑换记录不存在"}
