"""Task 5 services for auditable points, UGC review, and innovation team formation."""

import hashlib
import math
import re
from collections import defaultdict
from copy import deepcopy
from urllib.parse import urlparse

from zhihui_qilu.innovation_models import (
    CompetitionReviewResult,
    CompetitionSubmission,
    ContributionKind,
    PointTransaction,
    ProposalOutline,
    ProposalSection,
    ReviewDecision,
    ReviewStatus,
    ScoringDecision,
    StudentSkillProfile,
    TeamMatch,
    TeamRequirement,
)


class CampusPointsLedger:
    """Append-only in-memory reference ledger; production adapters should persist transactions."""

    def __init__(self) -> None:
        self._transactions: list[PointTransaction] = []
        self._source_index: dict[str, PointTransaction] = {}

    def post(self, transaction: PointTransaction) -> PointTransaction:
        """Post an idempotent approved contribution; the same source can never award twice."""
        existing = self._source_index.get(transaction.source_id)
        if existing is not None:
            return existing
        self._transactions.append(transaction)
        self._source_index[transaction.source_id] = transaction
        return transaction

    def balance_for(self, user_id: str) -> int:
        """Return the unified balance across all platform contribution sources."""
        return sum(transaction.points for transaction in self._transactions if transaction.user_id == user_id)

    def transactions_for(self, user_id: str) -> list[PointTransaction]:
        """Return the user's chronological audit trail."""
        return [transaction for transaction in self._transactions if transaction.user_id == user_id]


class CompetitionFingerprint:
    """Create stable competition identity hashes from normalized name, edition, and official domain."""

    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self._aliases = {self._normalize_name(key): self._normalize_name(value) for key, value in (aliases or {}).items()}

    def create(self, submission: CompetitionSubmission) -> str:
        """Hash canonical identity fields; mutable details such as deadlines remain diffable fields."""
        name = self._aliases.get(self._normalize_name(submission.competition_name), self._normalize_name(submission.competition_name))
        domain = urlparse(submission.official_url or "").netloc.lower().removeprefix("www.") or "unknown-domain"
        payload = "|".join((name, self._normalize_name(submission.edition), domain))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_name(value: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]", "", value).lower()


class CompetitionScorer:
    """Apply first-release decay using hashes and field-level value differences."""

    _COMPLETE_FIELDS = ("competition_name", "official_url", "deadline", "eligible_participants", "official_attachment_uri")
    _KEY_FIELDS = ("official_url", "deadline", "eligible_participants", "official_attachment_uri")

    def score(self, submission: CompetitionSubmission, fingerprint: str, existing: CompetitionSubmission | None) -> ScoringDecision:
        """Recommend 10/5/2-per-key-field/1/0 points without making the final approval decision."""
        if existing is None:
            is_complete = all(getattr(submission, field) not in (None, "") for field in self._COMPLETE_FIELDS)
            return ScoringDecision(points=10 if is_complete else 5, category="first_complete" if is_complete else "first_partial", fingerprint=fingerprint, explanation="首次提交该竞赛，按五要素完整度计算。")
        changed = self._changed_fields(existing, submission)
        key_changes = [field for field in changed if field in self._KEY_FIELDS]
        if key_changes:
            counted = key_changes[:3]
            return ScoringDecision(points=len(counted) * 2, category="key_increment", fingerprint=fingerprint, changed_fields=counted, explanation="已存在同一竞赛，新增或更新关键字段，按每项 2 分、最多计 3 项。")
        if changed:
            return ScoringDecision(points=1, category="minor_increment", fingerprint=fingerprint, changed_fields=changed, explanation="已存在同一竞赛，仅补充非关键说明信息。")
        return ScoringDecision(points=0, category="duplicate", fingerprint=fingerprint, explanation="与已收录信息实质重复，建议驳回且不计入贡献。")

    @staticmethod
    def _changed_fields(existing: CompetitionSubmission, incoming: CompetitionSubmission) -> list[str]:
        fields = ("official_url", "deadline", "eligible_participants", "organizer", "official_attachment_uri", "description")
        return [field for field in fields if getattr(incoming, field) not in (None, "") and getattr(incoming, field) != getattr(existing, field)]


class CompetitionReviewHall:
    """Admin-gated UGC workflow; AI scoring is advisory and never posts points before approval."""

    def __init__(self, ledger: CampusPointsLedger | None = None, fingerprint: CompetitionFingerprint | None = None, scorer: CompetitionScorer | None = None) -> None:
        self.ledger = ledger or CampusPointsLedger()
        self._fingerprint = fingerprint or CompetitionFingerprint()
        self._scorer = scorer or CompetitionScorer()
        self._submissions: dict[str, CompetitionSubmission] = {}
        self._catalog: dict[str, CompetitionSubmission] = {}

    def submit(self, submission: CompetitionSubmission) -> ScoringDecision:
        """Accept a pending submission and return an advisory scoring decision for the review hall."""
        fingerprint = self._fingerprint.create(submission)
        self._submissions[str(submission.submission_id)] = submission
        return self._scorer.score(submission, fingerprint, self._catalog.get(fingerprint))

    def pending(self) -> list[CompetitionSubmission]:
        """List submissions awaiting human review, newest first."""
        return sorted((item for item in self._submissions.values() if item.status == ReviewStatus.PENDING), key=lambda item: item.submitted_at, reverse=True)

    def review(self, submission_id: str, decision: ReviewDecision) -> CompetitionReviewResult:
        """Approve/reject once; approved nonzero contributions receive an immutable ledger entry."""
        submission = self._submissions.get(submission_id)
        if submission is None:
            raise KeyError("Submission was not found")
        if submission.status != ReviewStatus.PENDING:
            raise ValueError("A submission may be reviewed only once")
        fingerprint = self._fingerprint.create(submission)
        scoring = self._scorer.score(submission, fingerprint, self._catalog.get(fingerprint))
        reviewed = submission.model_copy(update={"status": ReviewStatus.APPROVED if decision.approved else ReviewStatus.REJECTED, "reviewer_id": decision.reviewer_id, "review_note": decision.note})
        self._submissions[submission_id] = reviewed
        if not decision.approved:
            return CompetitionReviewResult(submission=reviewed, scoring=scoring)
        self._catalog[fingerprint] = self._merge_catalog(self._catalog.get(fingerprint), reviewed)
        transaction = None
        if scoring.points > 0:
            transaction = self.ledger.post(PointTransaction(user_id=reviewed.submitter_id, points=scoring.points, kind=ContributionKind.COMPETITION_UGC, source_id=f"competition-review:{reviewed.submission_id}", metadata={"fingerprint": fingerprint, "category": scoring.category, "changed_fields": scoring.changed_fields}))
        return CompetitionReviewResult(submission=reviewed, scoring=scoring, transaction=transaction)

    @staticmethod
    def _merge_catalog(existing: CompetitionSubmission | None, incoming: CompetitionSubmission) -> CompetitionSubmission:
        if existing is None:
            return incoming
        updates = {field: getattr(incoming, field) for field in CompetitionScorer._KEY_FIELDS + ("organizer", "description") if getattr(incoming, field) not in (None, "")}
        return existing.model_copy(update=updates)


class TeamMatcher:
    """Rank opt-in student profiles by cosine similarity against an explicit project skill vector."""

    def match(self, requirement: TeamRequirement, candidates: list[StudentSkillProfile]) -> list[TeamMatch]:
        """Return only candidates with positive overlap, ranked deterministically by score then name."""
        matches: list[TeamMatch] = []
        for candidate in candidates:
            score = self._cosine(requirement.required_skills, candidate.skills)
            overlap = sorted(skill for skill in requirement.required_skills if candidate.skills.get(skill, 0) > 0)
            if score > 0:
                matches.append(TeamMatch(student_id=candidate.student_id, display_name=candidate.display_name, score=round(score, 4), matched_skills=overlap))
        return sorted(matches, key=lambda item: (-item.score, item.display_name))[: requirement.max_candidates]

    @staticmethod
    def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
        dot = sum(left.get(key, 0.0) * right.get(key, 0.0) for key in set(left) | set(right))
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


class ProposalOutlineGenerator:
    """Generate a proposal skeleton aligned with the official 2026 scoring sections.

    结构来自《中国国际大学生创新大赛（2026）创业计划书撰写要点》的九大要素，
    每段附「评委看什么」和可逐条勾选的自检点。项目名与技术关键词只用于个性化提示，
    不改变段落结构——评审标准是固定的，不应随项目变化。
    """

    # (id, 段落标题, 评委在这一段看什么, 自检点)
    _BLUEPRINT: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
        (
            "overview",
            "一、项目概述",
            "开篇锚定国家战略与行业背景，一句话说清给谁解决什么问题，并说明与专业课程、科研训练的关系。",
            (
                "开头两句话就说清了国家/行业背景，没有长铺垫",
                "有一句话能说清「给谁、解决什么问题」",
                "点明了目标市场与服务客群",
                "写出了与同类项目相比的差异点",
                "说明了项目与专业课程、科研训练、社会实践的关系",
            ),
        ),
        (
            "market",
            "二、市场分析",
            "调研过程要能被复述：怎么设计的、怎么实施的、数据从哪来；结论要有产业与用户两端支撑。",
            (
                "写了调研设计（问卷/访谈/实地，样本量多少）",
                "写了数据来源与获取时间，别人能复核",
                "产业端、市场端、用户端至少覆盖两类",
                "有产业规模、增速、竞争格局",
                "拆出了目标用户未被满足的具体痛点",
                "对比了至少 2 个同类方案并说明我们的差异",
            ),
        ),
        (
            "product",
            "三、产品或服务",
            "技术原理讲得清、创新点具体、有验证证据、有知识产权布局；不是把名词堆在一起。",
            (
                "讲清了核心技术原理，不只是名词罗列",
                "功能架构能对应到具体模块",
                "创新点写的是「和现有做法比新在哪」",
                "写了当前研发进展（到哪一步、能跑什么）",
                "有试验验证数据或真实使用记录",
                "列出了已申请/计划申请的知识产权",
            ),
        ),
        (
            "business",
            "四、商业模式",
            "价值主张、客户细分、收入来源、成本结构、渠道、关键资源、核心业务七件事必须自洽。",
            (
                "价值主张一句话说得清",
                "客户细分到具体角色，不是笼统的「大学生」",
                "收入来源写清了谁付钱、付多少、为什么愿意付",
                "成本结构列了主要项与量级",
                "落地路径有明确节点和时间",
            ),
        ),
        (
            "marketing",
            "五、营销策略",
            "分阶段、渠道具体、定价有依据、客户关系有维护机制。",
            (
                "按阶段（试点/推广/规模化）分开写，不是一套打法通吃",
                "每个阶段有可量化的市场目标",
                "线上线下渠道具体到平台和动作",
                "定价有依据（成本/竞品/用户支付意愿）",
                "有客户关系维护机制（复购、转介）",
            ),
        ),
        (
            "team",
            "六、团队管理",
            "能力互补、分工明确、决策与激励机制清晰，指导教师有实质贡献而不是挂名。",
            (
                "核心成员专业背景与能力结构互补",
                "每个人职责写清了，不是「共同负责」",
                "写了协作机制与决策模式",
                "写了激励制度",
                "指导教师在项目里有具体贡献",
                "有外部合作资源（企业/实验室/导师网络）",
            ),
        ),
        (
            "finance",
            "七、财务管理",
            "启动资金用途细分、分阶段测算、假设有依据、算得出回报周期。",
            (
                "启动资金总额与用途细分到项",
                "收入/成本/利润按阶段测算",
                "每个关键假设都写了依据",
                "有现金流分析",
                "算了投资回报周期",
            ),
        ),
        (
            "risk",
            "八、风险管理",
            "识别技术/市场/政策/财务四类风险，分级防控，并有材料真实性承诺。",
            (
                "覆盖技术迭代、市场接受、政策变动、财务运营四类",
                "每类风险评了发生概率与影响程度",
                "有分级防控措施，不是「加强管理」",
                "写了合规承诺与数据/知识产权真实性声明",
            ),
        ),
        (
            "plan",
            "九、发展规划",
            "短中长期目标、里程碑可量化，并体现育人价值与社会价值。",
            (
                "短期/中期/长期各写了目标",
                "每个阶段有可量化的里程碑指标",
                "写了规模化推广路径",
                "写了人才培养/育人价值",
                "写了社会价值（就业、区域、民生）",
            ),
        ),
    )

    def generate(self, project_name: str, competition_name: str, technical_keywords: list[str]) -> ProposalOutline:
        """Return the official nine scored sections, personalised with the caller's project facts."""
        stack = "、".join(technical_keywords) if technical_keywords else "待论证的核心技术"
        blueprint = [
            ProposalSection(
                id=section_id,
                title=title,
                # 技术关键词只落在「产品或服务」这一段，避免九段都被同一句模板污染
                weight_note=(f"{note}本项目需论证的核心技术：{stack}。" if section_id == "product" else note),
                checkpoints=list(checkpoints),
            )
            for section_id, title, note, checkpoints in self._BLUEPRINT
        ]
        return ProposalOutline(
            project_name=project_name,
            competition_name=competition_name,
            sections=[item.title for item in blueprint],
            blueprint=blueprint,
            source_note="结构依据《中国国际大学生创新大赛（2026）创业计划书撰写要点》九大要素；自检点按评审标准拆解，供逐条自查。",
            checkpoint_total=sum(len(item.checkpoints) for item in blueprint),
        )
