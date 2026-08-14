#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import requests
from seleniumbase import SB
from selenium.common.exceptions import NoSuchElementException


# ============================================================
# 环境变量
# ============================================================

EMAIL = os.environ.get("ZAM_PTO_EMAIL", "").strip()
PASSWORD = os.environ.get("ZAM_PTO_PASSWORD", "").strip()

TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()

IS_PROXY = (
    os.environ.get("IS_PROXY", "true").strip().lower() == "true"
)

PROXY_SERVER = os.environ.get(
    "PROXY_SERVER",
    "http://127.0.0.1:1081"
).strip()

BASE_URL = "https://dash.zampto.net"

# 从 DevTools 确认的选择器
EMAIL_SELECTOR = "#email"
PASSWORD_SELECTOR = "#password"


# ============================================================
# Telegram 通知
# ============================================================

def send_tg_message(
    status_icon: str,
    status_text: str,
    detail: str = ""
):
    """发送 Telegram 通知。未配置时自动跳过。"""

    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print(
            "ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，"
            "跳过 Telegram 推送。"
        )
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time = time.strftime(
        "%Y-%m-%d %H:%M:%S",
        local_time
    )

    # 邮箱脱敏
    if "@" in EMAIL:
        name, domain = EMAIL.split("@", 1)

        if len(name) > 4:
            masked_email = (
                f"{name[:2]}****{name[-2:]}@{domain}"
            )
        else:
            masked_email = f"{name}@{domain}"
    else:
        masked_email = (
            EMAIL[:2] + "****"
            if EMAIL
            else "未配置"
        )

    text = (
        "🇫🇷 ZamPTO 续期通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 续期账户: {masked_email}\n"
        f"⏱️ 操作时间: {current_time}"
    )

    if detail:
        text += f"\n📝 详情: {detail[:800]}"

    url = (
        f"https://api.telegram.org/"
        f"bot{TG_BOT_TOKEN}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            json={
                "chat_id": TG_CHAT_ID,
                "text": text
            },
            timeout=10,
        )

        if response.ok:
            print("📩 Telegram 通知发送成功！")
        else:
            print(
                "⚠️ Telegram 通知发送失败: "
                f"HTTP {response.status_code}"
            )

    except requests.RequestException as exc:
        print(
            f"⚠️ Telegram 通知发送异常: {exc}"
        )


# ============================================================
# Cloudflare / 人机验证检测（纯 SeleniumBase 方法）
# ============================================================

def has_challenge(sb) -> bool:
    """
    仅检测验证组件，不尝试绕过。
    """
    return (
        sb.is_element_present('input[name="cf-turnstile-response"]') or
        sb.is_element_present('iframe[src*="challenges.cloudflare.com"]') or
        sb.is_element_present('altcha-widget') or
        sb.is_element_present('[class*="altcha"]')
    )


def wait_for_challenge_to_clear(
    sb,
    timeout: int = 60
) -> bool:
    """
    等待网站自行完成或用户合法完成验证。
    不执行自动绕过。
    """

    if not has_challenge(sb):
        return True

    print(
        "⚠️ 页面出现人机验证，"
        "等待其正常完成……"
    )

    for _ in range(timeout):
        time.sleep(1)

        # 检查 cf-turnstile-response 是否有值（长度>20）
        try:
            cf_elem = sb.find_element(
                'input[name="cf-turnstile-response"]',
                timeout=0.5
            )
            cf_val = cf_elem.get_attribute("value") or ""
            if len(cf_val) > 20:
                print("✅ 验证已正常完成 (cf-turnstile-response)")
                return True
        except NoSuchElementException:
            pass
        except Exception:
            pass

        # 检查 altcha 或 captcha 输入框
        try:
            altcha_elem = sb.find_element(
                'input[name*="altcha" i], input[name*="captcha" i]',
                timeout=0.5
            )
            altcha_val = altcha_elem.get_attribute("value") or ""
            if len(altcha_val) > 20:
                print("✅ 验证已正常完成 (altcha/captcha)")
                return True
        except NoSuchElementException:
            pass
        except Exception:
            pass

        # 检查验证组件是否已消失
        if not has_challenge(sb):
            print("✅ 验证组件已消失")
            return True

    print(
        "❌ 人机验证未在限定时间内完成"
    )
    return False


# ============================================================
# 读取页面 Alert
# ============================================================

def read_alert(sb) -> str:

    try:
        alerts = sb.find_elements("div.alert")

        for alert in alerts:
            text = (alert.text or "").strip()

            if text:
                return text

    except Exception:
        pass

    return ""


# ============================================================
# 登录（优化版：先验证再等表单）
# ============================================================

def login(sb) -> bool:

    print("\n" + "#" * 25)
    print("   开始 ZamPTO 登录")
    print("#" * 25)

    # --------------------------------------------------------
    # 固定使用已经确认的登录地址
    # --------------------------------------------------------

    login_url = f"{BASE_URL}/auth/login"

    print(
        f"🌐 打开登录页面: {login_url}"
    )

    try:
        sb.uc_open_with_reconnect(
            login_url,
            reconnect_time=8
        )
    except Exception as exc:
        print(
            f"⚠️ 打开登录页面失败: {exc}"
        )
        return False

    # --------------------------------------------------------
    # 先处理可能出现的 Cloudflare 验证（重要调整）
    # --------------------------------------------------------

    if has_challenge(sb):
        print(
            "🛡️ 检测到人机验证，"
            "等待正常完成……"
        )
        if not wait_for_challenge_to_clear(
            sb,
            timeout=60
        ):
            sb.save_screenshot(
                "login_challenge.png"
            )
            return False
    else:
        print(
            "ℹ️ 未检测到人机验证组件"
        )

    # --------------------------------------------------------
    # 等待登录表单加载
    # --------------------------------------------------------

    print(
        "⏳ 等待登录表单加载……"
    )

    try:
        sb.wait_for_element(
            EMAIL_SELECTOR,
            timeout=30
        )

        sb.wait_for_element(
            PASSWORD_SELECTOR,
            timeout=30
        )

        print(
            "✅ 登录表单加载成功"
        )

    except Exception as exc:

        print(
            f"❌ 登录表单未加载成功: {exc}"
        )

        print(
            f"当前 URL: {sb.get_current_url()}"
        )

        print(
            f"当前标题: {sb.get_title() or ''}"
        )

        # 调试：打印当前页面所有 input
        try:

            inputs = sb.find_elements("input")

            print(
                f"🔎 当前页面检测到 "
                f"{len(inputs)} 个 input"
            )

            for index, element in enumerate(inputs):

                try:
                    input_type = (
                        element.get_attribute("type")
                    )

                    input_id = (
                        element.get_attribute("id")
                    )

                    input_name = (
                        element.get_attribute("name")
                    )

                    placeholder = (
                        element.get_attribute(
                            "placeholder"
                        )
                    )

                    autocomplete = (
                        element.get_attribute(
                            "autocomplete"
                        )
                    )

                    print(
                        f"   input[{index}] "
                        f"type={input_type} "
                        f"id={input_id} "
                        f"name={input_name} "
                        f"placeholder={placeholder} "
                        f"autocomplete={autocomplete}"
                    )

                except Exception:
                    pass

        except Exception:
            pass

        sb.save_screenshot(
            "login_form_fail.png"
        )

        return False

    # --------------------------------------------------------
    # Cookie 同意
    # --------------------------------------------------------

    try:

        for button in sb.find_elements(
            "button"
        ):

            text = (
                button.text or ""
            ).strip().lower()

            if text in {
                "accept",
                "accept all",
                "同意",
                "接受"
            }:

                print(
                    "🍪 点击 Cookie 同意按钮"
                )

                button.click()

                time.sleep(1)

                break

    except Exception:
        pass

    # --------------------------------------------------------
    # 填写 Email（使用 SeleniumBase 原生方法）
    # --------------------------------------------------------

    print(
        f"📧 填写邮箱 "
        f"({EMAIL_SELECTOR})……"
    )

    try:
        sb.update_text(EMAIL_SELECTOR, EMAIL)
        print("✅ 邮箱填写成功")
    except Exception as exc:
        print(f"❌ 邮箱填写失败: {exc}")
        sb.save_screenshot("email_input_fail.png")
        return False

    # --------------------------------------------------------
    # 填写 Password
    # --------------------------------------------------------

    print(
        f"🔑 填写密码 "
        f"({PASSWORD_SELECTOR})……"
    )

    try:
        sb.update_text(PASSWORD_SELECTOR, PASSWORD)
        print("✅ 密码填写成功")
    except Exception as exc:
        print(f"❌ 密码填写失败: {exc}")
        sb.save_screenshot("password_input_fail.png")
        return False

    time.sleep(1)

    # --------------------------------------------------------
    # 确认输入框中确实有值（使用 SeleniumBase 方法）
    # --------------------------------------------------------

    try:
        email_value = sb.get_value(EMAIL_SELECTOR) or ""
        password_value = sb.get_value(PASSWORD_SELECTOR) or ""
        print(f"✅ Email 已填写，长度: {len(email_value)}")
        print(f"✅ Password 已填写，长度: {len(password_value)}")
    except Exception as exc:
        print(f"⚠️ 检查输入值失败: {exc}")

    # --------------------------------------------------------
    # 再次检查验证（可能在填写后触发）
    # --------------------------------------------------------

    if has_challenge(sb):
        print(
            "🛡️ 填写后再次检测到人机验证，"
            "等待正常完成……"
        )
        if not wait_for_challenge_to_clear(
            sb,
            timeout=60
        ):
            sb.save_screenshot(
                "login_challenge_after_fill.png"
            )
            return False

    # --------------------------------------------------------
    # 查找 Login 按钮
    # --------------------------------------------------------

    print(
        "🖱️ 查找 Login 按钮……"
    )

    login_button = None

    try:

        buttons = sb.find_elements(
            "button"
        )

        print(
            f"🔎 页面共有 "
            f"{len(buttons)} 个 button"
        )

        for index, button in enumerate(
            buttons
        ):

            try:

                text = (
                    button.text or ""
                ).strip()

                button_type = (
                    button.get_attribute(
                        "type"
                    )
                )

                print(
                    f"   button[{index}] "
                    f"text={text!r} "
                    f"type={button_type!r}"
                )

                if text.lower() == "login":

                    login_button = button

                    print(
                        "✅ 找到 Login 按钮"
                    )

                    break

            except Exception:
                continue

    except Exception as exc:

        print(
            f"⚠️ 查找 Login 按钮失败: "
            f"{exc}"
        )

    # --------------------------------------------------------
    # 没找到时，使用备用选择器
    # --------------------------------------------------------

    if login_button is None:

        print(
            "⚠️ 通过文字没有找到 Login，"
            "尝试备用选择器……"
        )

        fallback_selectors = [
            'button[type="submit"]',
            'button',
            'input[type="submit"]',
        ]

        for selector in fallback_selectors:

            try:

                elements = sb.find_elements(
                    selector
                )

                for element in elements:

                    text = (
                        element.text or ""
                    ).strip().lower()

                    value = (
                        element.get_attribute(
                            "value"
                        ) or ""
                    ).strip().lower()

                    if (
                        text == "login"
                        or value == "login"
                        or selector == 'button[type="submit"]'
                    ):

                        login_button = element

                        print(
                            f"✅ 找到登录按钮: "
                            f"{selector}"
                        )

                        break

                if login_button is not None:
                    break

            except Exception:
                continue

    # --------------------------------------------------------
    # 最终仍未找到
    # --------------------------------------------------------

    if login_button is None:

        print(
            "❌ 没找到 Login 按钮"
        )

        sb.save_screenshot(
            "login_button_fail.png"
        )

        return False

    # --------------------------------------------------------
    # 滚动到按钮并点击
    # --------------------------------------------------------

    print(
        "🖱️ 滚动到 Login 按钮并点击……"
    )

    try:
        sb.scroll_to(login_button)
        time.sleep(0.5)
        login_button.click()
        print("✅ Login 按钮已点击")
    except Exception as exc:
        print(f"⚠️ 点击 Login 失败: {exc}")
        # 备用：使用 SeleniumBase 的 click 方法
        try:
            sb.click(login_button)
            print("✅ 已通过 SeleniumBase 点击 Login")
        except Exception as exc2:
            print(f"❌ 备用点击也失败: {exc2}")
            sb.save_screenshot("login_click_fail.png")
            return False

    # --------------------------------------------------------
    # 等待登录结果
    # --------------------------------------------------------

    print(
        "⏳ 等待登录结果……"
    )

    login_paths = {
        "/auth/login",
        "/login",
    }

    for i in range(30):

        time.sleep(1)

        current_url = sb.get_current_url()

        normalized_path = (
            current_url
            .split("?", 1)[0]
            .rstrip("/")
            .lower()
        )

        # 提取 path
        if "://" in normalized_path:
            try:
                from urllib.parse import urlparse

                normalized_path = (
                    urlparse(
                        normalized_path
                    ).path.rstrip("/").lower()
                )
            except Exception:
                pass

        print(
            f"   [{i + 1}/30] "
            f"URL: {current_url}"
        )

        # ----------------------------------------------------
        # 检测明显错误
        # ----------------------------------------------------

        alert_text = read_alert(sb)

        if alert_text:

            print(
                f"   📩 页面提示: "
                f"{alert_text}"
            )

            lowered = alert_text.lower()

            if any(
                word in lowered
                for word in (
                    "invalid",
                    "incorrect",
                    "wrong password",
                    "invalid credentials",
                    "authentication failed",
                    "login failed",
                )
            ):

                print(
                    "❌ 检测到账号/密码错误"
                )

                sb.save_screenshot(
                    "login_failed.png"
                )

                return False

        # ----------------------------------------------------
        # URL 已经离开登录页
        # ----------------------------------------------------

        if normalized_path not in login_paths:

            print(
                "✅ 登录成功！"
            )

            print(
                f"📄 登录后 URL: "
                f"{current_url}"
            )

            print(
                f"📄 登录后标题: "
                f"{sb.get_title() or ''}"
            )

            return True

        # ----------------------------------------------------
        # 检查登录表单是否消失
        # ----------------------------------------------------

        try:

            email_exists = (
                sb.is_element_present(
                    EMAIL_SELECTOR
                )
            )

            password_exists = (
                sb.is_element_present(
                    PASSWORD_SELECTOR
                )
            )

            if not email_exists and not password_exists:

                print(
                    "✅ 登录表单已消失，"
                    "判断登录成功"
                )

                print(
                    f"📄 当前 URL: "
                    f"{current_url}"
                )

                return True

        except Exception:
            pass

    # --------------------------------------------------------
    # 登录超时
    # --------------------------------------------------------

    print(
        "❌ 登录超时，"
        "30 秒内没有离开登录页面。"
    )

    print(
        f"最终 URL: "
        f"{sb.get_current_url()}"
    )

    print(
        f"最终标题: "
        f"{sb.get_title() or ''}"
    )

    sb.save_screenshot(
        "login_timeout.png"
    )

    return False


# ============================================================
# 查找服务器详情
# ============================================================

def goto_server_detail(sb) -> bool:

    print(
        "\n🖥️ 正在查找服务器详情入口……"
    )

    time.sleep(4)

    alert_text = read_alert(sb)

    if (
        alert_text
        and "can't renew"
        in alert_text.lower()
    ):

        print(
            f"ℹ️ 页面提示: "
            f"{alert_text}"
        )

        send_tg_message(
            "ℹ️",
            "未到续期时间",
            alert_text
        )

        return False

    selectors = [
        'a[href*="/server/"]',
        'a[href*="/servers/"]',
        'a[href*="server"]',
    ]

    for selector in selectors:

        try:

            elements = sb.find_elements(
                selector
            )

            for element in elements:

                text = (
                    element.text or ""
                ).strip().lower()

                if any(
                    word in text
                    for word in (
                        "view server",
                        "server",
                        "view",
                        "see"
                    )
                ):

                    print(
                        f"✅ 找到服务器入口: "
                        f"{text or selector}"
                    )

                    # 滚动到元素
                    sb.scroll_to(element)
                    time.sleep(0.5)
                    element.click()
                    time.sleep(5)

                    print(
                        f"📄 当前页面: "
                        f"{sb.get_current_url()}"
                    )

                    return True

        except Exception:
            continue

    # --------------------------------------------------------
    # 备用
    # --------------------------------------------------------

    try:

        for element in sb.find_elements(
            "a, button"
        ):

            text = (
                element.text or ""
            ).strip().lower()

            if text in {
                "view server",
                "view",
                "see"
            }:

                print(
                    f"✅ 点击服务器入口: "
                    f"{text}"
                )

                element.click()
                time.sleep(5)
                return True

    except Exception:
        pass

    print(
        "❌ 未找到服务器详情入口"
    )

    sb.save_screenshot(
        "servers_page_fail.png"
    )

    return False


# ============================================================
# 打开续期窗口
# ============================================================

def open_renew_dialog(sb) -> bool:

    print(
        "\n🔄 查找续期按钮……"
    )

    try:

        for element in sb.find_elements(
            "button, a"
        ):

            text = (
                element.text or ""
            ).strip().lower()

            if text in {
                "renew server",
                "renew",
                "confirm renewal"
            }:

                sb.scroll_to(element)
                time.sleep(0.5)
                element.click()
                time.sleep(3)

                print(
                    f"✅ 已点击续期按钮: "
                    f"{text}"
                )

                return True

    except Exception as exc:

        print(
            f"⚠️ 查找续期按钮时出错: "
            f"{exc}"
        )

    print(
        "❌ 未找到续期按钮"
    )

    sb.save_screenshot(
        "renew_button_fail.png"
    )

    return False


# ============================================================
# 提交续期
# ============================================================

def submit_renew(sb) -> bool:

    if has_challenge(sb):

        if not wait_for_challenge_to_clear(
            sb,
            timeout=60
        ):

            sb.save_screenshot(
                "renew_challenge.png"
            )

            print(
                "❌ 续期验证未完成，停止提交"
            )

            return False

    print(
        "🖱️ 点击确认续期按钮……"
    )

    selectors = [
        "div.modal.show button.btn-primary",
        "div.modal.show button[type='submit']",
        "button[type='submit']",
    ]

    for selector in selectors:

        try:

            buttons = sb.find_elements(
                selector
            )

            for button in buttons:

                text = (
                    button.text or ""
                ).strip().lower()

                if (
                    not text
                    or any(
                        word in text
                        for word in (
                            "renew",
                            "confirm",
                            "submit"
                        )
                    )
                ):

                    button.click()
                    time.sleep(4)

                    print(
                        "✅ 续期确认按钮已点击"
                    )

                    return True

        except Exception:
            continue

    print(
        "❌ 未找到确认续期按钮"
    )

    sb.save_screenshot(
        "renew_submit_fail.png"
    )

    return False


# ============================================================
# 检查续期结果
# ============================================================

def check_renew_result(sb):

    print(
        "\n📋 检查续期结果……"
    )

    time.sleep(2)

    alert_text = read_alert(sb)

    if not alert_text:

        print(
            "ℹ️ 未检测到明确的续期结果"
        )

        send_tg_message(
            "ℹ️",
            "续期操作已执行",
            "页面没有明确提示"
        )

        return

    print(
        f"📩 页面提示: "
        f"{alert_text}"
    )

    lowered = alert_text.lower()

    if any(
        word in lowered
        for word in (
            "can't renew",
            "unable",
            "already renewed"
        )
    ):

        send_tg_message(
            "⏳",
            "未到续期时间或已续期",
            alert_text
        )

    elif any(
        word in lowered
        for word in (
            "renewed",
            "success",
            "extended",
            "completed"
        )
    ):

        send_tg_message(
            "✅",
            "续期成功",
            alert_text
        )

    else:

        send_tg_message(
            "ℹ️",
            "续期操作已执行",
            alert_text
        )


# ============================================================
# 续期流程
# ============================================================

def renew_server(sb):

    print(
        "\n" + "#" * 25
    )

    print(
        "  开始 ZamPTO 自动续期流程"
    )

    print(
        "#" * 25
    )

    if not goto_server_detail(sb):
        return

    if not open_renew_dialog(sb):
        return

    if not submit_renew(sb):
        return

    check_renew_result(sb)


# ============================================================
# 主程序
# ============================================================

def main():

    print(
        "#" * 25
    )

    print(
        "   ZamPTO 自动登录续期"
    )

    print(
        "#" * 25
    )

    # --------------------------------------------------------
    # 环境变量检查
    # --------------------------------------------------------

    if not EMAIL or not PASSWORD:

        print(
            "❌ 未配置 "
            "ZAM_PTO_EMAIL 或 "
            "ZAM_PTO_PASSWORD"
        )

        send_tg_message(
            "❌",
            "账号环境变量未配置"
        )

        raise SystemExit(1)

    # --------------------------------------------------------
    # SeleniumBase
    # --------------------------------------------------------

    sb_kwargs = {
        "uc": True,
        "uc_cdp": True,          # 启用 CDP 规避，降低被检测概率
        "headless": False,
    }

    # --------------------------------------------------------
    # 代理
    # --------------------------------------------------------

    if IS_PROXY:

        print(
            f"🔗 使用 sing-box 本地代理: "
            f"{PROXY_SERVER}"
        )

        sb_kwargs["proxy"] = PROXY_SERVER

    else:

        print(
            "🌐 未启用代理，使用直连"
        )

    # --------------------------------------------------------
    # 启动浏览器
    # --------------------------------------------------------

    try:

        with SB(**sb_kwargs) as sb:

            # ------------------------------------------------
            # 获取出口 IP
            # ------------------------------------------------

            try:

                sb.open(
                    "https://api.ip.sb/ip"
                )

                exit_ip = (
                    sb.get_text("body")
                    .strip()
                )

                print(
                    f"📍 当前出口 IP: "
                    f"{exit_ip}"
                )

            except Exception as exc:

                print(
                    f"⚠️ 无法获取出口 IP: "
                    f"{exc}"
                )

                if IS_PROXY:

                    send_tg_message(
                        "❌",
                        "代理连接失败",
                        str(exc)
                    )

                    raise SystemExit(1)

            # ------------------------------------------------
            # 登录
            # ------------------------------------------------

            if login(sb):

                print(
                    "\n🎉 登录流程成功"
                )

                # ------------------------------------------------
                # 续期
                # ------------------------------------------------

                renew_server(sb)

            else:

                print(
                    "\n❌ 登录失败，"
                    "终止续期操作。"
                )

                send_tg_message(
                    "❌",
                    "登录失败"
                )

                raise SystemExit(1)

    except SystemExit:
        raise

    except Exception as exc:

        print(
            f"❌ 程序运行异常: "
            f"{exc}"
        )

        send_tg_message(
            "❌",
            "程序运行异常",
            str(exc)
        )

        raise SystemExit(1)


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":
    main()
