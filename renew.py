#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import requests
from seleniumbase import SB

# ============================================================
# 环境变量
# ============================================================

EMAIL = os.environ.get("ZAM_PTO_EMAIL", "").strip()
PASSWORD = os.environ.get("ZAM_PTO_PASSWORD", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()

IS_PROXY = os.environ.get("IS_PROXY", "true").strip().lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER", "http://127.0.0.1:1081").strip()

BASE_URL = "https://dash.zampto.net"
EMAIL_SELECTOR = "#email"
PASSWORD_SELECTOR = "#password"

# ============================================================
# Telegram 通知（不变）
# ============================================================

def send_tg_message(status_icon: str, status_text: str, detail: str = ""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    if "@" in EMAIL:
        name, domain = EMAIL.split("@", 1)
        masked_email = f"{name[:2]}****{name[-2:]}@{domain}" if len(name) > 4 else f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + "****" if EMAIL else "未配置"

    text = (
        f"🇫🇷 ZamPTO 续期通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 续期账户: {masked_email}\n"
        f"⏱️ 操作时间: {current_time}"
    )
    if detail:
        text += f"\n📝 详情: {detail[:800]}"

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        if r.ok:
            print("📩 Telegram 通知发送成功！")
        else:
            print(f"⚠️ Telegram 通知发送失败: HTTP {r.status_code}")
    except Exception as e:
        print(f"⚠️ Telegram 通知发送异常: {e}")

# ============================================================
# 验证绕过相关 JS 和工具函数（移植自 katabump）
# ============================================================

# 用于展开 Turnstile 避免被父容器裁剪
_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

# 用于激活浏览器窗口（确保 xdotool 点击有效）
def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls],
                               capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]],
                               timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"],
                       timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)],
                       timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

# 核心 Turnstile 处理函数（主动点击）
def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)

    # 检查是否已静默通过
    if sb.execute_script(_SOLVED_JS):
        print("✅ 已静默通过")
        return True

    # 尝试展开 Turnstile（防止被父容器裁剪）
    for _ in range(3):
        try:
            sb.execute_script(_EXPAND_JS)
        except Exception:
            pass
        time.sleep(0.5)

    # 使用 SeleniumBase 内置 uc_gui_click_captcha 处理 Turnstile
    for attempt in range(6):
        if sb.execute_script(_SOLVED_JS):
            print(f"✅ Turnstile 通过（第 {attempt} 次尝试）")
            return True

        print(f"🖱️ 第 {attempt + 1} 次调用 uc_gui_click_captcha...")
        try:
            sb.uc_gui_click_captcha()
        except Exception as e:
            print(f"⚠️ uc_gui_click_captcha 调用异常: {e}")

        # 等待验证结果（最多 8 秒）
        for _ in range(16):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True

        print(f"⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("  ❌ Turnstile 6 次均失败")
    return False

# 可选：用于续期时可能出现的 ALTCHA 验证（简单版本）
# 这里简化为仅检测并尝试点击，不做复杂坐标计算（可根据需要扩展）
def handle_altcha(sb) -> bool:
    print("🔐 处理 ALTCHA 验证（简化版）...")
    # 检查是否有 ALTCHA 相关元素
    try:
        sb.find_element('[data-state="verified"], .altcha--verified', timeout=2)
        print("✅ ALTCHA 已自动通过")
        return True
    except Exception:
        pass

    # 尝试点击 iframe 或 checkbox
    try:
        iframes = sb.find_elements('iframe[src*="altcha"]')
        for ifr in iframes:
            ifr.click()
            time.sleep(1)
    except Exception:
        pass

    # 检查是否通过
    for _ in range(10):
        try:
            if sb.find_element('[data-state="verified"], .altcha--verified', timeout=1):
                print("✅ ALTCHA 验证通过")
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

# ============================================================
# 原有辅助函数（读取 alert，JS 输入等）
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

def js_fill_input(sb, selector: str, text: str):
    """使用 JS 设置输入框值，并触发事件（安全版本）"""
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, "value"
        ).set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, "{safe_text}");
        }} else {{
            el.value = "{safe_text}";
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)

# ============================================================
# 登录函数（整合 Turnstile 处理）
# ============================================================

def login(sb) -> bool:
    print("\n" + "#" * 25)
    print("   开始 ZamPTO 登录")
    print("#" * 25)

    login_url = f"{BASE_URL}/auth/login"
    print(f"🌐 打开登录页面: {login_url}")

    try:
        sb.uc_open_with_reconnect(login_url, reconnect_time=8)
    except Exception as exc:
        print(f"⚠️ 打开登录页面失败: {exc}")
        return False

    # 等待登录表单加载
    print("⏳ 等待登录表单加载……")
    try:
        sb.wait_for_element(EMAIL_SELECTOR, timeout=30)
        sb.wait_for_element(PASSWORD_SELECTOR, timeout=30)
        print("✅ 登录表单加载成功")
    except Exception as exc:
        print(f"❌ 登录表单未加载成功: {exc}")
        print(f"当前 URL: {sb.get_current_url()}")
        print(f"当前标题: {sb.get_title() or ''}")
        sb.save_screenshot("login_form_fail.png")
        return False

    # Cookie 同意
    try:
        for button in sb.find_elements("button"):
            text = (button.text or "").strip().lower()
            if text in {"accept", "accept all", "同意", "接受"}:
                button.click()
                time.sleep(1)
                break
    except Exception:
        pass

    # 填写邮箱和密码（使用 JS 输入，更稳定）
    print(f"📧 填写邮箱 ({EMAIL_SELECTOR})……")
    js_fill_input(sb, EMAIL_SELECTOR, EMAIL)
    print(f"🔑 填写密码 ({PASSWORD_SELECTOR})……")
    js_fill_input(sb, PASSWORD_SELECTOR, PASSWORD)
    time.sleep(1)

    # 检查是否触发了 Turnstile
    if sb.execute_script(_EXISTS_JS):
        print("🛡️ 检测到 Turnstile 验证，开始处理...")
        if not handle_turnstile(sb):
            print("❌ Turnstile 验证失败")
            sb.save_screenshot("login_turnstile_fail.png")
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")

    # 提交登录（敲回车）
    print("🖱️ 敲击回车提交表单...")
    sb.press_keys(PASSWORD_SELECTOR, '\n')

    # 等待登录跳转
    print("⏳ 等待登录结果……")
    login_paths = {"/auth/login", "/login"}
    for i in range(30):
        time.sleep(1)
        current_url = sb.get_current_url()
        normalized = current_url.split("?", 1)[0].rstrip("/").lower()
        # 提取 path
        if "://" in normalized:
            from urllib.parse import urlparse
            normalized = urlparse(normalized).path.rstrip("/").lower()

        # 检测错误提示
        alert_text = read_alert(sb)
        if alert_text:
            lowered = alert_text.lower()
            if any(kw in lowered for kw in ("invalid", "incorrect", "wrong password", "invalid credentials")):
                print("❌ 账号或密码错误")
                sb.save_screenshot("login_failed.png")
                return False

        # 如果已经离开登录页，视为成功
        if normalized not in login_paths:
            print("✅ 登录成功！")
            print(f"📄 当前 URL: {current_url}")
            print(f"📄 标题: {sb.get_title() or ''}")
            return True

        # 如果表单消失也视为成功
        if not sb.is_element_present(EMAIL_SELECTOR) and not sb.is_element_present(PASSWORD_SELECTOR):
            print("✅ 登录表单已消失，判定登录成功")
            return True

    print("❌ 登录超时（30秒）")
    sb.save_screenshot("login_timeout.png")
    return False

# ============================================================
# 续期流程（沿用原有逻辑，增加验证处理）
# ============================================================

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
                    sb.scroll_to(element)
                    time.sleep(0.5)
                    element.click()
                    time.sleep(5)
                    print(f"📄 当前页面: {sb.get_current_url()}")
                    return True
        except Exception:
            continue

    # 备用：通过文本找
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
                sb.scroll_to(element)
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
    # 如果续期过程中出现验证，简单处理一下（Turnstile 或 ALTCHA）
    if sb.execute_script(_EXISTS_JS):
        print("🛡️ 续期时出现 Turnstile，处理中...")
        if not handle_turnstile(sb):
            print("⚠️ Turnstile 处理失败，尝试继续")
    else:
        # 尝试检测 ALTCHA
        try:
            sb.find_element('iframe[src*="altcha"]', timeout=2)
            print("🔐 检测到 ALTCHA，尝试处理...")
            handle_altcha(sb)
        except Exception:
            pass

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
                if not text or any(word in text for word in ("renew", "confirm", "submit")):
                    button.click()
                    time.sleep(4)
                    print("✅ 续期确认按钮已点击")
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
    if any(kw in lowered for kw in ("can't renew", "unable", "already renewed")):
        send_tg_message("⏳", "未到续期时间或已续期", alert_text)
    elif any(kw in lowered for kw in ("renewed", "success", "extended", "completed")):
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

# ============================================================
# 主程序
# ============================================================

def main():
    print("#" * 25)
    print("   ZamPTO 自动登录续期")
    print("#" * 25)

    if not EMAIL or not PASSWORD:
        print("❌ 未配置 ZAM_PTO_EMAIL 或 ZAM_PTO_PASSWORD")
        send_tg_message("❌", "账号环境变量未配置")
        raise SystemExit(1)

    sb_kwargs = {
        "uc": True,
        "headless": False,
    }
    if IS_PROXY:
        print(f"🔗 使用 sing-box 本地代理: {PROXY_SERVER}")
        sb_kwargs["proxy"] = PROXY_SERVER
    else:
        print("🌐 未启用代理，使用直连")

    try:
        with SB(**sb_kwargs) as sb:
            # 获取出口 IP
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
                print("\n🎉 登录流程成功")
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
