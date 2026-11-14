"""学业预警自检：把学校的学生学业预警办法翻译成学生自己能算的一次检查。

规则来自公开的院校长文件，不是本系统自造：

* 学年学业预警：一学年所修学分总量（不含通识选修课及辅修专业学分）不足 20 学分
* 毕业班学业预警：标准修业年限内，到毕业前一学年学分总量达不到培养方案规定
  额定学分总量 65% 的（五年制专业 70%）
* 处置流程：确定名单 → 送达通知书（本人签字确认）→ 谈话交流 → 学业帮扶建档

（口径参照《山东科技大学本科学生学业预警工作通知》，各校细则略有差异，
 因此这里只做「自检提示」，不下结论，也不替代教务系统的正式判定。）
"""

from dataclasses import dataclass, field

# 学年最低修读学分（细则常见口径）
ANNUAL_MIN_CREDITS = 20.0
# 毕业班学分完成率下限：四年制 65%，五年制 70%
GRADUATION_RATIO = {4: 0.65, 5: 0.70}
# 本系统补充的进度提醒：落后应修进度超过 15 个百分点才提示
PACE_GAP = 0.15
# 不及格门数提醒线
FAILED_COURSE_ALERT = 3


@dataclass
class CreditTrigger:
    """一条命中的预警标准。"""

    code: str
    title: str
    detail: str
    basis: str


@dataclass
class CreditAssessment:
    """自检结果：等级、完成率、命中的标准、学生该做的动作。"""

    level: str
    progress: float
    required_credits: float
    earned_credits: float
    triggers: list[CreditTrigger] = field(default_factory=list)
    student_steps: list[str] = field(default_factory=list)
    school_steps: list[str] = field(default_factory=list)
    note: str = ""


class CreditWarningService:
    """按学校学业预警办法做一次确定性自检，不涉及任何外部系统调用。"""

    def assess(
        self,
        *,
        grade: int,
        program_years: int,
        required_credits: float,
        earned_credits: float,
        year_credits: float,
        failed_courses: int = 0,
    ) -> CreditAssessment:
        """返回自检结论。参数非法时抛 ValueError，由 Skill 层转成可读提示。"""
        if program_years not in GRADUATION_RATIO:
            raise ValueError("学制只支持 4 年制或 5 年制")
        if not 1 <= grade <= program_years:
            raise ValueError("当前学年必须在 1 到学制年限之间")
        if required_credits <= 0:
            raise ValueError("培养方案额定总学分必须大于 0")
        if earned_credits < 0 or year_credits < 0:
            raise ValueError("学分数不能为负")
        if earned_credits > required_credits:
            # 允许辅修/提前修读造成的超出，但不把它当成错误
            earned_credits = required_credits

        progress = round(earned_credits / required_credits, 4)
        triggers: list[CreditTrigger] = []

        if year_credits < ANNUAL_MIN_CREDITS:
            triggers.append(
                CreditTrigger(
                    code="annual_shortfall",
                    title="学年学业预警",
                    detail=f"本学年已修 {year_credits:g} 学分，低于 {ANNUAL_MIN_CREDITS:g} 学分线",
                    basis="一学年所修学分总量（不含通识选修课及辅修专业学分）不足 20 学分",
                )
            )

        ratio_line = GRADUATION_RATIO[program_years]
        if grade == program_years and progress < ratio_line:
            triggers.append(
                CreditTrigger(
                    code="graduation_shortfall",
                    title="毕业班学业预警",
                    detail=f"累计完成 {progress * 100:.1f}%，低于 {ratio_line * 100:.0f}% 线",
                    basis=f"{program_years} 年制专业毕业前一学年学分总量不得低于额定总量的 {ratio_line * 100:.0f}%",
                )
            )

        expected = grade / program_years
        # 毕业班已有专门标准（65% / 70%），不再叠加线性进度提醒，
        # 否则「第 4 学年应完成 100%」会误报——那不是学校的线。
        if grade < program_years and progress + PACE_GAP < expected:
            triggers.append(
                CreditTrigger(
                    code="pace_behind",
                    title="进度偏慢提醒",
                    detail=f"按第 {grade} 学年应有约 {expected * 100:.0f}%，当前 {progress * 100:.1f}%",
                    basis="本系统按学制线性推算的进度参考值，不是学校预警标准",
                )
            )

        if failed_courses >= FAILED_COURSE_ALERT:
            triggers.append(
                CreditTrigger(
                    code="failed_courses",
                    title="不及格课程偏多",
                    detail=f"当前有 {failed_courses} 门不及格，重修会挤占后续学期学分",
                    basis="重修学分通常不计入当学年新增学分，容易连带触发学年预警",
                )
            )

        # 等级：命中学校标准 → warning；只命中本系统提醒 → watch
        hard = {"annual_shortfall", "graduation_shortfall"}
        if any(trigger.code in hard for trigger in triggers):
            level = "warning"
        elif triggers:
            level = "watch"
        else:
            level = "ok"

        return CreditAssessment(
            level=level,
            progress=progress,
            required_credits=required_credits,
            earned_credits=earned_credits,
            triggers=triggers,
            student_steps=self._student_steps(level, triggers),
            school_steps=self._school_steps(),
            note="自检结果只作提示，正式预警名单以教务处审核、学院复核后的通知为准。",
        )

    @staticmethod
    def _student_steps(level: str, triggers: list[CreditTrigger]) -> list[str]:
        """学生这一侧该做的动作：从「弄清触发哪一条」到「主动汇报」。"""
        if level == "ok":
            return [
                "学分进度正常，保持每学年不低于 20 学分即可",
                "提前看清培养方案里剩下的必修课，避免高年级撞课",
            ]
        codes = {trigger.code for trigger in triggers}
        steps = ["先看清触发的是哪一条标准，别把「进度偏慢」当成「已经被预警」"]
        if codes & {"annual_shortfall", "graduation_shortfall"}:
            steps.append("收到《学业预警通知书》时当面核对学分数据，确认无误再签字")
        steps.append("带一份成绩单和本学期选课记录去谈话，说清哪几门课卡住了")
        if "failed_courses" in codes:
            steps.append("先排重修：重修学分不进当学年新增，拖到下一年会连带触发学年预警")
        steps.append("和辅导员或学业导师定一份本学期提升计划，写清每门课的目标分")
        steps.append("期末前主动汇报一次进度，不要等到下一轮预警再解释")
        return steps

    @staticmethod
    def _school_steps() -> list[str]:
        """学校这一侧的四步流程，让学生知道后面会发生什么。"""
        return [
            "确定名单：教务处审核学业情况，学院登录教务系统复核",
            "送达通知：学院当面下达《学业预警通知书》，本人签字确认后存档",
            "谈话交流：分析原因、共同制定学习计划；需要家长配合的会联系家长",
            "学业帮扶：建立帮扶档案，跟踪效果，效果不理想会调整措施",
        ]
