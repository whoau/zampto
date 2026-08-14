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
# Telegram 通知
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
# Cloudflare Turnstile 绕过（移植自 katabump）
# ============================================================

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

def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)

    if sb.execute_script(_SOLVED_JS):
        print("✅ 已静默通过")
        return True

    for _ in range(3):
        try:
            sb.execute_script(_EXPAND_JS)
        except Exception:
            pass
        time.sleep(0.5)

    for attempt in range(6):
        if sb.execute_script(_SOLVED_JS):
            print(f"✅ Turnstile 通过（第 {attempt} 次尝试）")
            return True

        print(f"🖱️ 第 {attempt + 1} 次调用 uc_gui_click_captcha...")
        try:
            sb.uc_gui_click_captcha()
        except Exception as e:
            print(f"⚠️ uc_gui_click_captcha 调用异常: {e}")

        for _ in range(16):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True

        print(f"⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("  ❌ Turnstile 6 次均失败")
    return False

# ============================================================
# 辅助函数
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
# 登录
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

    print(f"📧 填写邮箱 ({EMAIL_SELECTOR})……")
    js_fill_input(sb, EMAIL_SELECTOR, EMAIL)
    print(f"🔑 填写密码 ({PASSWORD_SELECTOR})……")
    js_fill_input(sb, PASSWORD_SELECTOR, PASSWORD)
    time.sleep(1)

    # 处理 Turnstile（如果有）
    if sb.execute_script(_EXISTS_JS):
        print("🛡️ 检测到 Turnstile 验证，开始处理...")
        if not handle_turnstile(sb):
            print("❌ Turnstile 验证失败")
            sb.save_screenshot("login_turnstile_fail.png")
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")

    print("🖱️ 敲击回车提交表单...")
    sb.press_keys(PASSWORD_SELECTOR, '\n')

    print("⏳ 等待登录结果……")
    login_paths = {"/auth/login", "/login"}
    for i in range(30):
        time.sleep(1)
        current_url = sb.get_current_url()
        normalized = current_url.split("?", 1)[0].rstrip("/").lower()
        if "://" in normalized:
            from urllib.parse import urlparse
            normalized = urlparse(normalized).path.rstrip("/").lower()

        alert_text = read_alert(sb)
        if alert_text:
            lowered = alert_text.lower()
            if any(kw in lowered for kw in ("invalid", "incorrect", "wrong password", "invalid credentials")):
                print("❌ 账号或密码错误")
                sb.save_screenshot("login_failed.png")
                return False

        if normalized not in login_paths:
            print("✅ 登录成功！")
            print(f"📄 当前 URL: {current_url}")
            print(f"📄 标题: {sb.get_title() or ''}")
            return True

        if not sb.is_element_present(EMAIL_SELECTOR) and not sb.is_element_present(PASSWORD_SELECTOR):
            print("✅ 登录表单已消失，判定登录成功")
            return True

    print("❌ 登录超时（30秒）")
    sb.save_screenshot("login_timeout.png")
    return False

# ============================================================
# 续期流程
# ============================================================

def goto_server_detail(sb) -> bool:
    print("\n🖥️ 正在查找服务器详情入口……")
    time.sleep(4)

    alert_text = read_alert(sb)
    if alert_text and "can't renew" in alert_text.lower():
        print(f"ℹ️ 页面提示: {alert_text}")
        send_tg_message("ℹ️", "未到续期时间", alert_text)
        return False

    # 精确匹配 "View Server" 链接
    try:
        view_link = sb.find_element("//a[contains(text(),'View Server')]", timeout=5)
        print(f"✅ 找到 View Server 链接: {view_link.text}")
        sb.scroll_to(view_link)
        time.sleep(0.5)
        view_link.click()
        time.sleep(5)
        print(f"📄 点击后当前页面: {sb.get_current_url()}")
        if "server" in sb.get_current_url().lower():
            return True
        else:
            print("⚠️ 点击后未进入服务器详情页，尝试其他方法...")
    except Exception as e:
        print(f"⚠️ 通过 XPath 查找 View Server 失败: {e}")

    # 备用：遍历所有 a 标签
    try:
        all_links = sb.find_elements("a")
        print(f"🔎 页面共有 {len(all_links)} 个链接")
        for a in all_links:
            text = (a.text or "").strip()
            if text.lower() == "view server":
                print(f"✅ 通过文本匹配找到: {text}")
                sb.scroll_to(a)
                a.click()
                time.sleep(5)
                if "server" in sb.get_current_url().lower():
                    return True
    except Exception as e:
        print(f"⚠️ 遍历链接失败: {e}")

    print("❌ 未找到 'View Server' 入口")
    sb.save_screenshot("servers_page_fail.png")
    return False

def open_renew_dialog(sb) -> bool:
    print("\n🔄 查找 'Renew Server' 按钮……")
    time.sleep(3)
    print(f"当前 URL: {sb.get_current_url()}")
    print(f"页面标题: {sb.get_title() or ''}")

    renew_btn = None

    # 尝试多种 XPath 定位（同时支持 button 和 a）
    selectors = [
        "//button[contains(text(),'Renew Server')]",
        "//a[contains(text(),'Renew Server')]",
        "//*[contains(text(),'Renew Server') and (self::button or self::a)]",
    ]
    for xpath in selectors:
        try:
            renew_btn = sb.find_element(xpath, timeout=3)
            if renew_btn:
                print(f"✅ 通过 XPath 找到: {xpath}")
                break
        except Exception:
            continue

    if renew_btn is None:
        print("⚠️ XPath 未命中，遍历所有可点击元素...")
        try:
            elements = sb.find_elements("button, a, input[type='button']")
            for elem in elements:
                if "renew server" in (elem.text or "").lower():
                    renew_btn = elem
                    print("✅ 通过遍历找到 'Renew Server'")
                    break
        except Exception as e:
            print(f"⚠️ 遍历元素失败: {e}")

    if renew_btn is None:
        print("❌ 未找到 'Renew Server' 按钮")
        try:
            all_elements = sb.find_elements("button, a")
            print("页面所有 button/a 文本:")
            for e in all_elements[:20]:
                print(f"  - {e.text}")
        except Exception:
            pass
        sb.save_screenshot("renew_button_fail.png")
        return False

    try:
        sb.scroll_to(renew_btn)
        time.sleep(0.5)
        renew_btn.click()
        print("✅ 已点击 'Renew Server' 按钮")
        time.sleep(3)
        return True
    except Exception as e:
        print(f"⚠️ 点击失败: {e}")
        try:
            sb.execute_script("arguments[0].click();", renew_btn)
            print("✅ 使用 JS 点击成功")
            time.sleep(3)
            return True
        except Exception as e2:
            print(f"❌ JS 点击也失败: {e2}")
            return False

def submit_renew(sb) -> bool:
    print("⏳ 等待续期结果反馈（5秒）...")
    time.sleep(5)

    alert_text = read_alert(sb)
    if alert_text:
        print(f"📩 页面提示: {alert_text}")
        # 无论提示什么，都继续让 check_renew_result 判断
        return True
    else:
        print("ℹ️ 未检测到明确提示，默认续期请求已发送")
        return True

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
