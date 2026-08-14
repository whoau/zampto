#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import requests
from seleniumbase import SB

# ===== 环境变量 =====
EMAIL = os.environ.get("ZAM_PTO_EMAIL", "").strip()
PASSWORD = os.environ.get("ZAM_PTO_PASSWORD", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()

IS_PROXY = os.environ.get("IS_PROXY", "true").strip().lower() == "true"
PROXY_SERVER = os.environ.get(
    "PROXY_SERVER", "http://127.0.0.1:1081"
).strip()

BASE_URL = "https://dash.zampto.net/auth/login"


def send_tg_message(status_icon: str, status_text: str, detail: str = ""):
    """发送 Telegram 通知。未配置时自动跳过。"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    if "@" in EMAIL:
        name, domain = EMAIL.split("@", 1)
        if len(name) > 4:
            masked_email = f"{name[:2]}****{name[-2:]}@{domain}"
        else:
            masked_email = f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + "****" if EMAIL else "未配置"

    text = (
        "🇫🇷 ZamPTO 续期通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 续期账户: {masked_email}\n"
        f"⏱️ 操作时间: {current_time}"
    )
    if detail:
        text += f"\n📝 详情: {detail[:800]}"

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        response = requests.post(
            url,
            json={"chat_id": TG_CHAT_ID, "text": text},
            timeout=10,
        )
        if response.ok:
            print("📩 Telegram 通知发送成功！")
        else:
            print(f"⚠️ Telegram 通知发送失败: HTTP {response.status_code}")
    except requests.RequestException as exc:
        print(f"⚠️ Telegram 通知发送异常: {exc}")


def js_fill_input(sb, selector: str, text: str):
    """安全设置输入框值，并触发 input/change 事件。"""
    sb.execute_script(
        """
        const selector = arguments[0];
        const value = arguments[1];
        const el = document.querySelector(selector);
        if (!el) return false;
        const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, "value"
        ).set;
        setter.call(el, value);
        el.dispatchEvent(new Event("input", {bubbles: true}));
        el.dispatchEvent(new Event("change", {bubbles: true}));
        return true;
        """,
        selector,
        text,
    )


def has_challenge(sb) -> bool:
    """仅检测验证组件，不尝试绕过。"""
    try:
        return bool(
            sb.execute_script(
                """
                return Boolean(
                    document.querySelector('input[name="cf-turnstile-response"]') ||
                    document.querySelector('iframe[src*="challenges.cloudflare.com"]') ||
                    document.querySelector('altcha-widget') ||
                    document.querySelector('[class*="altcha"]')
                );
                """
            )
        )
    except Exception:
        return False


def wait_for_challenge_to_clear(sb, timeout: int = 30) -> bool:
    """等待网站自行完成或用户合法完成验证，不执行自动绕过。"""
    if not has_challenge(sb):
        return True

    print("⚠️ 页面出现人机验证，等待其正常完成……")
    for _ in range(timeout):
        time.sleep(1)
        try:
            solved = sb.execute_script(
                """
                const cf = document.querySelector(
                    'input[name="cf-turnstile-response"]'
                );
                if (cf && cf.value && cf.value.length > 20) return true;

                const altcha = document.querySelector(
                    'input[name*="altcha" i], input[name*="captcha" i]'
                );
                if (altcha && altcha.value && altcha.value.length > 20) {
                    return true;
                }

                return !document.querySelector(
                    'iframe[src*="challenges.cloudflare.com"], altcha-widget'
                );
                """
            )
            if solved:
                print("✅ 验证已正常完成")
                return True
        except Exception:
            pass

    print("❌ 人机验证未在限定时间内完成")
    return False


def login(sb) -> bool:
    login_urls = [f"{BASE_URL}/auth/login", f"{BASE_URL}/login"]

    loaded = False
    for login_url in login_urls:
        print(f"🌐 打开登录页面: {login_url}")
        try:
            sb.uc_open_with_reconnect(login_url, reconnect_time=8)
            time.sleep(5)
            if sb.is_element_present('input[name="email"]'):
                loaded = True
                break
        except Exception as exc:
            print(f"⚠️ 页面打开失败: {exc}")

    if not loaded:
        if has_challenge(sb) and not wait_for_challenge_to_clear(sb, timeout=30):
            sb.save_screenshot("login_challenge.png")
            return False

        try:
            sb.wait_for_element('input[name="email"]', timeout=15)
        except Exception:
            print("❌ 页面未加载出登录表单")
            print(f"当前 URL: {sb.get_current_url()}")
            print(f"当前标题: {sb.get_title() or ''}")
            sb.save_screenshot("login_load_fail.png")
            return False

    try:
        for button in sb.find_elements("button"):
            text = (button.text or "").strip().lower()
            if text in {"accept", "accept all", "同意", "接受"}:
                button.click()
                time.sleep(0.5)
                break
    except Exception:
        pass

    print("📧 填写邮箱……")
    js_fill_input(sb, 'input[name="email"]', EMAIL)

    print("🔑 填写密码……")
    js_fill_input(sb, 'input[name="password"]', PASSWORD)
    time.sleep(1)

    if has_challenge(sb) and not wait_for_challenge_to_clear(sb, timeout=30):
        sb.save_screenshot("login_challenge.png")
        return False

    print("🖱️ 提交登录表单……")
    sb.press_keys('input[name="password"]', "\n")

    for _ in range(20):
        time.sleep(1)
        current_url = sb.get_current_url().split("?", 1)[0].lower()
        page_title = (sb.get_title() or "").lower()
        if "dashboard" in current_url or "dashboard" in page_title:
            print(
                f"✅ 登录成功！URL: {sb.get_current_url()}, "
                f"Title: {sb.get_title() or ''}"
            )
            return True

    print(
        "❌ 登录失败，页面未跳转到账户页。"
        f"URL: {sb.get_current_url()}, Title: {sb.get_title() or ''}"
    )
    sb.save_screenshot("login_failed.png")
    return False


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


def goto_server_detail(sb) -> bool:
    print("\n🖥️ 正在查找服务器详情入口……")
    time.sleep(4)

    alert_text = read_alert(sb)
    if alert_text and "can't renew" in alert_text.lower():
        print(f"ℹ️ 页面提示: {alert_text}")
        send_tg_message("ℹ️", "未到续期时间", alert_text)
        return False

    selectors = [
        'a[href*="/server/"]',
        'a[href*="/servers/"]',
        'a[href*="server"]',
    ]

    for selector in selectors:
        try:
            elements = sb.find_elements(selector)
            for element in elements:
                text = (element.text or "").strip().lower()
                if any(word in text for word in ("view server", "server", "view", "see")):
                    print(f"✅ 找到服务器入口: {text or selector}")
                    sb.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", element
                    )
                    element.click()
                    time.sleep(5)
                    print(f"📄 当前页面: {sb.get_current_url()}")
                    return True
        except Exception:
            continue

    try:
        for element in sb.find_elements("a, button"):
            text = (element.text or "").strip().lower()
            if text in {"view server", "view", "see"}:
                element.click()
                time.sleep(5)
                return True
    except Exception:
        pass

    print("❌ 未找到服务器详情入口")
    sb.save_screenshot("servers_page_fail.png")
    return False


def open_renew_dialog(sb) -> bool:
    print("\n🔄 查找续期按钮……")

    try:
        for element in sb.find_elements("button, a"):
            text = (element.text or "").strip().lower()
            if text in {"renew server", "renew", "confirm renewal"}:
                sb.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", element
                )
                time.sleep(0.5)
                element.click()
                time.sleep(3)
                print(f"✅ 已点击续期按钮: {text}")
                return True
    except Exception as exc:
        print(f"⚠️ 查找续期按钮时出错: {exc}")

    print("❌ 未找到续期按钮")
    sb.save_screenshot("renew_button_fail.png")
    return False


def submit_renew(sb) -> bool:
    if has_challenge(sb) and not wait_for_challenge_to_clear(sb, timeout=30):
        sb.save_screenshot("renew_challenge.png")
        print("❌ 续期验证未完成，停止提交")
        return False

    print("🖱️ 点击确认续期按钮……")
    selectors = [
        "div.modal.show button.btn-primary",
        "div.modal.show button[type='submit']",
        "button[type='submit']",
    ]

    for selector in selectors:
        try:
            buttons = sb.find_elements(selector)
            for button in buttons:
                text = (button.text or "").strip().lower()
                if not text or any(
                    word in text for word in ("renew", "confirm", "submit")
                ):
                    button.click()
                    time.sleep(4)
                    return True
        except Exception:
            continue

    print("❌ 未找到确认续期按钮")
    sb.save_screenshot("renew_submit_fail.png")
    return False


def check_renew_result(sb):
    print("\n📋 检查续期结果……")
    time.sleep(2)
    alert_text = read_alert(sb)

    if not alert_text:
        print("ℹ️ 未检测到明确的续期结果")
        send_tg_message("ℹ️", "续期操作已执行", "页面没有明确提示")
        return

    print(f"📩 页面提示: {alert_text}")
    lowered = alert_text.lower()

    if any(word in lowered for word in ("can't renew", "unable", "already renewed")):
        send_tg_message("⏳", "未到续期时间或已续期", alert_text)
    elif any(word in lowered for word in ("renewed", "success", "extended", "completed")):
        send_tg_message("✅", "续期成功", alert_text)
    else:
        send_tg_message("ℹ️", "续期操作已执行", alert_text)


def renew_server(sb):
    print("\n" + "#" * 25)
    print("  开始 ZamPTO 自动续期流程")
    print("#" * 25)

    if not goto_server_detail(sb):
        return
    if not open_renew_dialog(sb):
        return
    if not submit_renew(sb):
        return

    check_renew_result(sb)


def main():
    print("#" * 25)
    print("   ZamPTO 自动登录续期")
    print("#" * 25)

    if not EMAIL or not PASSWORD:
        print("❌ 未配置 ZAM_PTO_EMAIL 或 ZAM_PTO_PASSWORD")
        send_tg_message("❌", "账号环境变量未配置")
        raise SystemExit(1)

    sb_kwargs = {"uc": True, "headless": False}

    if IS_PROXY:
        print(f"🔗 使用 sing-box 本地代理: {PROXY_SERVER}")
        sb_kwargs["proxy"] = PROXY_SERVER
    else:
        print("🌐 未启用代理，使用直连")

    try:
        with SB(**sb_kwargs) as sb:
            try:
                sb.open("https://api.ip.sb/ip")
                exit_ip = sb.get_text("body").strip()
                print(f"📍 当前出口 IP: {exit_ip}")
            except Exception as exc:
                print(f"⚠️ 无法获取出口 IP: {exc}")
                if IS_PROXY:
                    send_tg_message("❌", "代理连接失败", str(exc))
                    raise SystemExit(1)

            if login(sb):
                renew_server(sb)
            else:
                print("\n❌ 登录失败，终止续期操作。")
                send_tg_message("❌", "登录失败")
                raise SystemExit(1)

    except SystemExit:
        raise
    except Exception as exc:
        print(f"❌ 程序运行异常: {exc}")
        send_tg_message("❌", "程序运行异常", str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
