"""钓鱼邮件与可疑链接识别（定向命题七）。

命题原文要求「支持用户上传邮件正文、邮件截图、HTML 页面、可疑链接、短信内容或通知文本后，
自动对其进行钓鱼风险识别与分析，输出风险等级、疑似钓鱼原因、可疑证据点和处置建议」。
这里做其中三种：**文本、HTML、链接**。截图 OCR 不做，因为识别图片里的字是另一件事，
做一半反而让人以为看懂了整张图。

三条实现原则：

1. **纯规则，不调大模型**。钓鱼识别是安全判断，必须可解释、可复现、离线可用。
   每条命中都能指回一条具体规则，而不是「模型觉得可疑」。
2. **证据点引用原文片段**。只说「高风险」没用，得让人看见是哪句话、哪个链接。
3. **不访问链接**。只解析字符串，不发请求——否则识别工具本身就成了探测工具，
   而且现场网络不可控。域名是否属于学校靠白名单判断，不靠 DNS。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

# 学校与可信域名。只认这几个后缀，其余一律要人工确认。
SAFE_DOMAIN_SUFFIXES: tuple[str, ...] = ("sdnu.edu.cn", "sdnu.edu", "gov.cn", "edu.cn")
SAFE_EXACT_DOMAINS: tuple[str, ...] = ("12356.org",)

# 短链服务：真实目标看不见，一律先降信任。
SHORTENERS: tuple[str, ...] = (
    "bit.ly", "t.cn", "dwz.cn", "tinyurl.com", "goo.gl", "is.gd", "url.cn",
    "suo.im", "sina.lt", "rebrand.ly", "cutt.ly", "shorturl.at",
)

# 高风险的顶级域：正常机构极少用。
RISKY_TLDS: tuple[str, ...] = (".top", ".xyz", ".tk", ".cc", ".icu", ".buzz", ".cyou", ".click", ".link")

# 紧急措辞：制造时间压力是钓鱼最稳的手法。
URGENCY_WORDS: tuple[str, ...] = (
    "立即", "马上", "24 小时内", "24小时内", "今日内", "今天内", "尽快", "限时",
    "否则", "逾期", "冻结", "停用", "注销", "封号", "清退", "最后通知", "紧急",
)

# 索要凭证：只要出现这些组合，基本可以定性。
CREDENTIAL_WORDS: tuple[str, ...] = (
    "验证码", "密码", "账号密码", "银行卡号", "身份证号", "CVV", "有效期",
    "统一身份认证", "校园网账号", "登录密码", "支付密码", "短信验证码",
)

# 冒充校内身份。
IMPERSONATION_WORDS: tuple[str, ...] = (
    "教务处", "学生处", "学生工作部", "财务处", "研究生院", "图书馆", "一卡通",
    "辅导员", "班主任", "资助中心", "信息中心", "校办", "校医院",
)

# 转账与支付诱导。
MONEY_WORDS: tuple[str, ...] = (
    "汇款", "转账", "扫码支付", "代付", "垫付", "打款", "收款码", "支付宝", "微信转账",
    "补缴", "缴纳", "缴费",
)

# 附件诱导。
ATTACHMENT_WORDS: tuple[str, ...] = (
    "点击下载", "双击打开", "解压后运行", "下载附件", "附件见", "安装包", "补丁",
)
RISKY_EXTENSIONS: tuple[str, ...] = (".exe", ".scr", ".bat", ".cmd", ".vbs", ".js", ".jar", ".msi", ".zip", ".rar")

# 奖励诱导。
REWARD_WORDS: tuple[str, ...] = (
    "中奖", "恭喜您", "助学金到账", "补贴发放", "退款", "返现", "红包", "免费领取", "抽奖",
)

_URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s，。；、）)\]\"'<>]+", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IP_URL = re.compile(r"^https?://\d{1,3}(?:\.\d{1,3}){3}", re.IGNORECASE)
_FORM_ACTION = re.compile(r"<form[^>]*action\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_PASSWORD_INPUT = re.compile(r"<input[^>]*type\s*=\s*[\"']password[\"']", re.IGNORECASE)
_IFRAME = re.compile(r"<iframe[^>]*>", re.IGNORECASE)
_BASE_HREF = re.compile(r"<base[^>]*href\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_JS_REDIRECT = re.compile(r"(?:location\.(?:href|replace)\s*=|window\.open\s*\()", re.IGNORECASE)
_SCRIPT_BLOCK = re.compile(r"<script[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)


class PhishingInputError(ValueError):
    """输入为空或类型不对时抛出，消息面向用户。"""


@dataclass
class Finding:
    """一条命中：规则码、给人看的标题、解释，以及引用到的原文片段。"""

    code: str
    title: str
    detail: str
    weight: int
    evidence: list[str] = field(default_factory=list)


@dataclass
class PhishingReport:
    """一次识别的完整结果。"""

    input_type: str
    risk_level: str
    risk_label: str
    score: int
    findings: list[Finding] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)
    note: str = ""
    scanned_links: list[str] = field(default_factory=list)
    safe_links: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_type": self.input_type,
            "risk_level": self.risk_level,
            "risk_label": self.risk_label,
            "score": self.score,
            "findings": [
                {
                    "code": item.code,
                    "title": item.title,
                    "detail": item.detail,
                    "weight": item.weight,
                    "evidence": item.evidence,
                }
                for item in self.findings
            ],
            "advice": self.advice,
            "note": self.note,
            "scanned_links": self.scanned_links,
            "safe_links": self.safe_links,
        }


def _domain_of(url: str) -> str:
    """取出主机名，去掉端口与 www 前缀，统一小写。"""
    try:
        parsed = urlparse(url if "://" in url else f"http://{url}")
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _is_safe_domain(host: str) -> bool:
    """白名单判断，不做 DNS 查询。"""
    if not host:
        return False
    if host in SAFE_EXACT_DOMAINS:
        return True
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in SAFE_DOMAIN_SUFFIXES)


def _looks_like_fake_school(host: str) -> bool:
    """域名里带学校关键词，但不是学校域名——这是最典型的仿冒。"""
    if _is_safe_domain(host):
        return False
    tokens = ("sdnu", "shanshi", "sdnuedu", "sdnu-edu", "sdnu.edu")
    return any(token in host for token in tokens)


def _excerpt(text: str, word: str, width: int = 24) -> str:
    """截取命中词周围的一小段，作为证据点。"""
    index = text.find(word)
    if index < 0:
        return ""
    start = max(0, index - width)
    end = min(len(text), index + len(word) + width)
    snippet = text[start:end].replace("\n", " ").strip()
    return f"…{snippet}…" if start > 0 or end < len(text) else snippet


def _scan_text(text: str, findings: list[Finding]) -> None:
    """文本类特征：紧急措辞、索要凭证、冒充身份、转账、附件、奖励。"""
    lowered = text.lower()

    hits = [word for word in URGENCY_WORDS if word in text]
    if hits:
        findings.append(
            Finding(
                code="urgency_pressure",
                title="制造时间压力",
                detail="用「立即 / 否则 / 冻结」这类词逼你来不及核实就操作。真正的通知不会只给几小时。",
                weight=18,
                evidence=[_excerpt(text, word) for word in hits[:3]],
            )
        )

    hits = [word for word in CREDENTIAL_WORDS if word in text]
    if hits:
        findings.append(
            Finding(
                code="credential_request",
                title="索要账号、密码或验证码",
                detail="学校任何部门都不会通过邮件或短信向你索取密码和验证码。这一条单独出现就足够定性。",
                weight=40,
                evidence=[_excerpt(text, word) for word in hits[:3]],
            )
        )

    hits = [word for word in MONEY_WORDS if word in text]
    if hits:
        findings.append(
            Finding(
                code="money_request",
                title="涉及转账或缴费",
                detail="学校收费走统一支付平台，不会让你扫码、转账或垫付到个人账户。",
                weight=26,
                evidence=[_excerpt(text, word) for word in hits[:3]],
            )
        )

    hits = [word for word in ATTACHMENT_WORDS if word in text]
    if hits:
        findings.append(
            Finding(
                code="attachment_lure",
                title="诱导下载或打开附件",
                detail="附件是投递木马最常见的方式。学校通知一般放在官网或办事大厅，不靠邮件附件。",
                weight=16,
                evidence=[_excerpt(text, word) for word in hits[:3]],
            )
        )

    hits = [word for word in REWARD_WORDS if word in text]
    if hits:
        findings.append(
            Finding(
                code="reward_lure",
                title="用奖励诱导点击",
                detail="助学金和补贴都有正式发放流程，不会通过一条链接「立即领取」。",
                weight=16,
                evidence=[_excerpt(text, word) for word in hits[:3]],
            )
        )

    for ext in RISKY_EXTENSIONS:
        if ext in lowered:
            findings.append(
                Finding(
                    code="risky_attachment",
                    title=f"出现可执行附件类型 {ext}",
                    detail="这类文件打开就可能运行代码。即使发件人看起来可信，也先电话核实。",
                    weight=22,
                    evidence=[_excerpt(text, ext)],
                )
            )
            break


def _impersonation_finding(text: str) -> Finding | None:
    """「冒充校内部门」只在别的地方已经有疑点时才算一条。

    正常通知本来就会署名「教务处」。把它当成独立信号，等于给每一份真通知
    都盖一个黄标，现场一问就露怯。所以这一条是**放大器**，不是触发器：
    只有同时存在施压、索要凭证、仿冒域名之类的硬信号时，才补上这一条。
    """
    hits = [word for word in IMPERSONATION_WORDS if word in text]
    if not hits:
        return None
    return Finding(
        code="impersonation",
        title="署名冒充校内部门",
        detail="提到具体部门不等于来自该部门。核实要看发件域名，不看签名。",
        weight=12,
        evidence=[_excerpt(text, word) for word in hits[:3]],
    )


def _scan_links(text: str, findings: list[Finding]) -> tuple[list[str], list[str]]:
    """链接特征：仿冒域名、短链、IP 直连、高风险后缀。返回（全部链接, 可信链接）。"""
    links = _URL_PATTERN.findall(text)
    scanned: list[str] = []
    safe: list[str] = []
    seen: set[str] = set()

    for link in links:
        cleaned = link.rstrip(".,;:!?")
        host = _domain_of(cleaned)
        if not host or cleaned in seen:
            continue
        seen.add(cleaned)
        scanned.append(cleaned)

        if _is_safe_domain(host):
            safe.append(cleaned)
            continue

        # 一条链接可能同时命中多条规则（仿冒域名 + 高风险后缀 + 无 HTTPS），
        # 所以这里不 continue，把能说的都说清楚。
        if _looks_like_fake_school(host):
            findings.append(
                Finding(
                    code="lookalike_domain",
                    title="仿冒学校域名",
                    detail=f"域名 {host} 里带学校关键词，但不是 sdnu.edu.cn。这类域名注册成本很低，是最常见的手法。",
                    weight=40,
                    evidence=[cleaned],
                )
            )

        if any(host == short or host.endswith(f".{short}") for short in SHORTENERS):
            findings.append(
                Finding(
                    code="shortened_link",
                    title="短链接隐藏真实地址",
                    detail=f"{host} 是短链服务，点开前看不出会去哪。要核实就把短链换成展开后的完整地址。",
                    weight=30,
                    evidence=[cleaned],
                )
            )

        if _IP_URL.match(cleaned):
            findings.append(
                Finding(
                    code="ip_link",
                    title="直接用 IP 地址访问",
                    detail="正规校园服务不会用 IP 当访问地址。IP 链接无法用证书验证身份。",
                    weight=26,
                    evidence=[cleaned],
                )
            )

        if any(host.endswith(tld) for tld in RISKY_TLDS):
            findings.append(
                Finding(
                    code="risky_tld",
                    title="高风险域名后缀",
                    detail=f"{host} 使用的后缀在钓鱼站点里出现频率很高，正常机构极少使用。",
                    weight=18,
                    evidence=[cleaned],
                )
            )

        if host.startswith("xn--") or "xn--" in host:
            findings.append(
                Finding(
                    code="punycode_domain",
                    title="域名含编码字符（同形字风险）",
                    detail="这类域名能用外形相近的字母冒充真域名，肉眼几乎看不出差别。",
                    weight=30,
                    evidence=[cleaned],
                )
            )

    return scanned, safe


def _scan_html(html: str, findings: list[Finding]) -> None:
    """HTML 特征：外域表单、密码框、隐藏 iframe、base 跳转、JS 跳转。"""
    actions = _FORM_ACTION.findall(html)
    has_password = bool(_PASSWORD_INPUT.search(html))
    for action in actions:
        host = _domain_of(action)
        if host and not _is_safe_domain(host):
            findings.append(
                Finding(
                    code="external_form_action",
                    title="表单把内容提交到校外地址",
                    detail=f"页面上的输入框会把内容发到 {host}。仿冒登录页最典型的做法就是这一条。",
                    weight=44 if has_password else 28,
                    evidence=[f'<form action="{action}">'],
                )
            )
            break

    if has_password and not any(_is_safe_domain(_domain_of(action)) for action in actions if action):
        findings.append(
            Finding(
                code="password_form",
                title="页面含密码输入框",
                detail="如果这个页面不是从学校官网点进来的，先关掉，再从官网重新进。",
                weight=24,
                evidence=["<input type=\"password\">"],
            )
        )

    iframe = _IFRAME.search(html)
    if iframe:
        findings.append(
            Finding(
                code="iframe_present",
                title="页面内嵌了外部框架",
                detail="iframe 能把别的站点整个嵌进来，让你以为还在原网站。需要看清 iframe 的地址。",
                weight=14,
                evidence=[iframe.group(0)[:120]],
            )
        )

    base = _BASE_HREF.search(html)
    if base:
        host = _domain_of(base.group(1))
        if host and not _is_safe_domain(host):
            findings.append(
                Finding(
                    code="base_href_redirect",
                    title="页面基准地址被指向校外",
                    detail=f"<base href> 会让页面上所有相对链接都跳到 {host}，即使地址栏看起来正常。",
                    weight=32,
                    evidence=[f'<base href="{base.group(1)}">'],
                )
            )

    for block in _SCRIPT_BLOCK.findall(html):
        if _JS_REDIRECT.search(block):
            findings.append(
                Finding(
                    code="js_redirect",
                    title="脚本里有自动跳转",
                    detail="打开页面就被跳到别处，是钓鱼页常见做法。",
                    weight=20,
                    evidence=[_excerpt(block, "location", 30) or block.strip()[:80]],
                )
            )
            break


def _score_to_level(score: int) -> tuple[str, str]:
    if score >= 60:
        return "high", "高风险"
    if score >= 30:
        return "medium", "需要核实"
    return "low", "暂未发现明显问题"


def _advice_for(level: str, findings: list[Finding]) -> list[str]:
    codes = {item.code for item in findings}
    if level == "high":
        advice = [
            "先不要点任何链接，也不要下载附件。",
            "已经点过或填过密码的，立刻改密码并退出所有已登录设备。",
            "把这条消息转发给学校信息办（86180371）或辅导员核实。",
        ]
        if "credential_request" in codes or "password_form" in codes:
            advice.insert(1, "验证码和密码不要补给任何人，包括自称老师的人。")
        if "money_request" in codes:
            advice.insert(1, "涉及缴费的，只走学校统一支付平台，不向个人账户转账。")
        return advice
    if level == "medium":
        return [
            "先别急着操作，从学校官网重新进一次，不要用消息里的链接。",
            "发件人邮箱是不是 @sdnu.edu.cn 结尾？不是就当陌生人处理。",
            "拿不准就把原文发给辅导员看一眼，问一句不丢人。",
        ]
    return [
        "目前没发现典型钓鱼特征，但「没发现」不等于「一定安全」。",
        "涉及账号和钱的，仍然只从官网入口进。",
    ]


def analyze_text(text: str) -> PhishingReport:
    """邮件正文、短信、通知文本。"""
    body = (text or "").strip()
    if not body:
        raise PhishingInputError("内容为空。把邮件正文或短信原文粘进来再分析。")
    if len(body) > 20000:
        raise PhishingInputError("内容太长了（超过 2 万字）。只粘可疑的那一段就够。")

    findings: list[Finding] = []
    _scan_text(body, findings)
    scanned, safe = _scan_links(body, findings)

    if _EMAIL_PATTERN.search(body):
        for address in _EMAIL_PATTERN.findall(body):
            domain = address.split("@", 1)[-1].lower()
            if not _is_safe_domain(domain):
                findings.append(
                    Finding(
                        code="external_sender",
                        title="发件人不是学校邮箱",
                        detail=f"{address} 的域名是 {domain}，不是 sdnu.edu.cn。签名写「教务处」也不改变这一点。",
                        weight=18,
                        evidence=[address],
                    )
                )
                break

    # 已经有硬信号了，再补「署名冒充」这一条放大说明。
    if findings:
        extra = _impersonation_finding(body)
        if extra is not None:
            findings.append(extra)

    score = min(100, sum(item.weight for item in findings))
    level, label = _score_to_level(score)
    return PhishingReport(
        input_type="text",
        risk_level=level,
        risk_label=label,
        score=score,
        findings=findings,
        advice=_advice_for(level, findings),
        scanned_links=scanned,
        safe_links=safe,
        note="只做字符串分析，不访问任何链接，也不上传到外部服务。",
    )


def analyze_html(html: str) -> PhishingReport:
    """HTML 页面源码。"""
    body = (html or "").strip()
    if not body:
        raise PhishingInputError("内容为空。把网页源码粘进来再分析（浏览器里按 Ctrl+U 可以看源码）。")
    if len(body) > 200000:
        raise PhishingInputError("源码太长（超过 20 万字符）。只粘表单附近那一段就够。")

    findings: list[Finding] = []
    # HTML 里的可见文字也要过一遍文本规则，否则只查标签会漏掉正文里的诱导话术。
    visible = re.sub(r"<[^>]+>", " ", body)
    _scan_text(visible, findings)
    _scan_links(visible, findings)
    _scan_html(body, findings)

    if findings:
        extra = _impersonation_finding(visible)
        if extra is not None:
            findings.append(extra)

    score = min(100, sum(item.weight for item in findings))
    level, label = _score_to_level(score)
    return PhishingReport(
        input_type="html",
        risk_level=level,
        risk_label=label,
        score=score,
        findings=findings,
        advice=_advice_for(level, findings),
        note="只解析源码，不渲染页面、不执行脚本、不访问其中任何地址。",
    )


def analyze_url(url: str) -> PhishingReport:
    """单条可疑链接。"""
    raw = (url or "").strip()
    if not raw:
        raise PhishingInputError("链接为空。把要核实的那条链接粘进来。")
    if "://" not in raw:
        raw = f"http://{raw}"

    findings: list[Finding] = []
    host = _domain_of(raw)
    if not host:
        raise PhishingInputError("这条链接看不出域名，检查一下是不是粘漏了。")

    if _is_safe_domain(host):
        return PhishingReport(
            input_type="url",
            risk_level="low",
            risk_label="学校域名",
            score=0,
            findings=[],
            advice=[
                "域名属于学校（sdnu.edu.cn 或 edu.cn 体系），但仍要看具体页面是不是官方入口。",
                "如果要输入密码，确认地址栏是 https 且域名完全一致。",
            ],
            scanned_links=[raw],
            safe_links=[raw],
            note="只按域名白名单判断，没有访问该链接。",
        )

    _scan_links(raw, findings)

    # _scan_links 已经覆盖仿冒域名、短链、IP、高风险后缀、同形字；
    # 一条都没命中才补「不是学校域名」，避免同一问题说两遍。
    if not findings:
        findings.append(
            Finding(
                code="unknown_domain",
                title="不是学校域名",
                detail=f"{host} 不在学校域名白名单里。校外地址不等于钓鱼，但涉及账号密码时必须核实。",
                weight=30,
                evidence=[raw],
            )
        )

    if raw.lower().startswith("http://"):
        findings.append(
            Finding(
                code="no_tls",
                title="没有 HTTPS",
                detail="明文传输意味着中间人可以改内容。学校服务都已启用 HTTPS。",
                weight=16,
                evidence=[raw],
            )
        )

    score = min(100, sum(item.weight for item in findings))
    level, label = _score_to_level(score)
    return PhishingReport(
        input_type="url",
        risk_level=level,
        risk_label=label,
        score=score,
        findings=findings,
        advice=_advice_for(level, findings),
        scanned_links=[raw],
        note="只解析字符串，没有访问该链接。",
    )
