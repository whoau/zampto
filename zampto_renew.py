#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import requests
import json
from seleniumbase import SB

# ===== 环境变量 =====
EMAIL        = os.environ.get("ZAMTO_EMAIL") or ""
PASSWORD     = os.environ.get("ZAMTO_PASSWORD") or ""
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""

BASE_URL = "https://dash.zampto.net"

# ===== Telegram 推送 =====
def send_tg_message(status_icon, status_text, time_left=""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return
    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        if len(name) > 4:
            masked_email = f"{name[:2]}****{name[-2:]}@{domain}"
        else:
            masked_email = f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + '****'
    text = (
        f"🇫🇷 zampto 续期通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 续期账户: {masked_email}\n"
        f"⏱️ 续期时间: {current_time_str}"
    )
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("📩 Telegram 通知发送成功！")
        else:
            print(f"⚠️ Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"⚠️ Telegram 通知发送异常: {e}")

# ===== Turnstile 相关 JS =====
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

_WININFO_JS = """
(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()
"""

# Zampto 没有 ALTCHA，但保留空变量以兼容
_ALTCHA_EXPAND_JS = ""
_ALTCHA_SOLVED_JS = ""

# ===== 辅助函数 =====
def js_fill_input(sb, selector: str, text: str):
    """使用 json.dumps 安全转义，处理特殊字符"""
    safe_text = json.dumps(text)
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, {safe_text});
        }} else {{
            el.value = {safe_text};
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)

def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
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

def _read_alert(sb):
    try:
        el = sb.find_element("div.alert", timeout=4)
        return (el.text or "").strip()
    except Exception:
        return ""

# ===== 登录模块（带增强截图） =====
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {BASE_URL}/auth/login")
    sb.uc_open_with_reconnect(BASE_URL + "/auth/login", reconnect_time=8)
    time.sleep(6)

    sb.save_screenshot("01_after_page_load.png")
    print("📸 已截图: 01_after_page_load.png")
    print(f"  当前URL: {sb.get_current_url()}")
    print(f"  页面标题: {sb.get_title() or '无标题'}")

    page_source = sb.get_page_source() or ""
    if "cf-challenge" in page_source.lower() or "captcha" in page_source.lower():
        sb.save_screenshot("02_cloudflare_challenge.png")
        print("⚠️ 检测到 Cloudflare 挑战页面，可能被拦截")
        print("📸 已截图: 02_cloudflare_challenge.png")

    print("⏳ 等待登录表单...")
    try:
        sb.wait_for_element('input[name="email"]', timeout=15)
    except Exception:
        try:
            sb.wait_for_element('input[type="email"]', timeout=5)
        except Exception:
            print("❌ 页面未加载出登录表单")
            cur_url = sb.get_current_url()
            page_title = sb.get_title() or ""
            print(f"  当前 URL: {cur_url}")
            print(f"  当前标题: {page_title}")
            sb.save_screenshot("03_login_form_not_found.png")
            print("📸 已截图: 03_login_form_not_found.png")
            return False

    sb.save_screenshot("04_login_form_visible.png")
    print("📸 已截图: 04_login_form_visible.png")

    print("🍪 关闭可能的 Cookie 弹窗...")
    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or ""):
                btn.click()
                time.sleep(0.5)
                break
    except Exception:
        pass

    print(f"📧 填写邮箱...")
    js_fill_input(sb, 'input[name="email"]', EMAIL)
    time.sleep(0.3)

    print("🔑 填写密码...")
    js_fill_input(sb, 'input[name="password"]', PASSWORD)
    time.sleep(1)

    sb.save_screenshot("05_after_fill.png")
    print("📸 已截图: 05_after_fill.png")

    print("⏳ 等待 Turnstile 验证框出现...")
    ts_found = False
    for i in range(10):
        if sb.execute_script(_EXISTS_JS):
            ts_found = True
            print(f"✅ 检测到 Turnstile（{i+1}s）")
            sb.save_screenshot("06_turnstile_detected.png")
            print("📸 已截图: 06_turnstile_detected.png")
            break
        time.sleep(1)

    if ts_found:
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证失败")
            sb.save_screenshot("07_turnstile_fail.png")
            print("📸 已截图: 07_turnstile_fail.png")
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")

    print("🖱️ 点击登录按钮...")
    try:
        sb.find_element('button[type="submit"]', timeout=5).click()
    except Exception:
        sb.press_keys('input[name="password"]', '\n')

    print("⏳ 等待登录跳转...")
    time.sleep(5)
    for i in range(12):
        time.sleep(1)
        cur_url = sb.get_current_url().split('?')[0].lower()
        page_title = sb.get_title() or ""
        if "/overview" in cur_url or "/dashboard" in cur_url:
            break

    cur_url = sb.get_current_url().split('?')[0].lower()
    page_title = sb.get_title() or ""
    if "/overview" in cur_url or "/dashboard" in cur_url:
        print(f"✅ 登录成功！(URL: {sb.get_current_url()}, Title: {page_title})")
        sb.save_screenshot("08_login_success.png")
        return True

    print(f"❌ 登录失败，页面未跳转到账户页。")
    print(f"  当前 URL: {sb.get_current_url()}")
    print(f"  当前标题: {page_title}")
    sb.save_screenshot("09_login_failed.png")
    print("📸 已截图: 09_login_failed.png")
    with open("login_failed_source.html", "w", encoding="utf-8") as f:
        f.write(sb.get_page_source())
    print("📄 已保存页面源码: login_failed_source.html")
    return False

# ===== 续期流程（带增强截图） =====
def _goto_server_overview(sb) -> bool:
    print("\n🖥️  正在进入服务器详情页...")
    time.sleep(5)
    sb.save_screenshot("10_overview_page.png")
    print("📸 已截图: 10_overview_page.png")

    alert_text = _read_alert(sb)
    if alert_text and "can't renew" in alert_text.lower():
        print(f"ℹ️  页面提示: {alert_text}")
        send_tg_message("ℹ️", "⚠️ 未到续期时间", alert_text)
        sb.save_screenshot("11_cannot_renew_alert.png")
        return False

    selectors = [
        'a:contains("View Server")',
        'button:contains("View Server")',
        'a[href*="/server/"]',
        'a[href*="/manage"]',
        'td a:contains("View")',
    ]
    view_btn = None
    for sel in selectors:
        try:
            view_btn = sb.find_element(sel, timeout=5)
            print(f"✅ 通过选择器找到 View Server: {sel}")
            break
        except Exception:
            continue

    if view_btn is None:
        print("⚠️ 选择器未命中，尝试遍历元素...")
        for el in sb.find_elements("a") + sb.find_elements("button"):
            txt = (el.text or "").strip()
            if "view server" in txt.lower() or "view" in txt.lower():
                view_btn = el
                print(f"✅ 通过文本找到: {txt}")
                break

    if view_btn is None:
        cur_url = sb.get_current_url()
        title = sb.get_title() or ""
        print(f"❌ 未找到 'View Server' 按钮")
        print(f"当前 URL: {cur_url}")
        print(f"页面标题: {title}")
        sb.save_screenshot("12_no_view_server.png")
        print("📸 已截图: 12_no_view_server.png")
        return False

    print("🖱️  点击 'View Server'...")
    view_btn.click()
    time.sleep(5)
    sb.save_screenshot("13_after_click_view_server.png")
    print("📸 已截图: 13_after_click_view_server.png")
    print(f"📄 当前页面: {sb.get_current_url()}")
    return True

def _click_renew_button(sb) -> bool:
    print("\n🔄 查找 Renew 按钮...")
    sb.save_screenshot("14_before_renew_search.png")
    print("📸 已截图: 14_before_renew_search.png")

    renew_btn = None
    selectors = [
        'button:contains("Renew")',
        'a:contains("Renew")',
        'button:contains("Renew Server")',
        'a:contains("Renew Server")',
        'button.btn-primary:contains("Renew")',
        'a[href*="renew"]',
    ]
    for sel in selectors:
        try:
            renew_btn = sb.find_element(sel, timeout=5)
            print(f"✅ 通过选择器找到 Renew: {sel}")
            break
        except Exception:
            continue

    if renew_btn is None:
        print("⚠️ 选择器未命中，遍历所有按钮/链接...")
        for el in sb.find_elements("button") + sb.find_elements("a"):
            txt = (el.text or "").strip()
            if "renew" in txt.lower():
                renew_btn = el
                print(f"✅ 通过文本找到 Renew: {txt}")
                break

    if renew_btn is None:
        print("ℹ️  未找到 Renew 按钮，可能已是付费用户或不在续期窗口")
        send_tg_message("ℹ️", "无需续期", "未找到 Renew 按钮")
        sb.save_screenshot("15_no_renew_button.png")
        print("📸 已截图: 15_no_renew_button.png")
        return False

    sb.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", renew_btn)
    time.sleep(1)
    renew_btn.click()
    print("🖱️  已点击 Renew 按钮")
    time.sleep(3)
    sb.save_screenshot("16_after_click_renew.png")
    print("📸 已截图: 16_after_click_renew.png")
    return True

def _check_renew_result(sb):
    print("\n📋 检查续期结果...")
    time.sleep(2)
    sb.save_screenshot("17_before_result_check.png")
    alert_text = _read_alert(sb)
    if not alert_text:
        time.sleep(3)
        alert_text = _read_alert(sb)
    if alert_text:
        print(f"📩 页面提示: {alert_text}")
        low = alert_text.lower()
        if "can't renew" in low or "unable" in low:
            send_tg_message("⏳", "未到续期时间", alert_text)
        elif any(kw in low for kw in ("renewed", "success", "extended")):
            send_tg_message("✅", "续期成功", alert_text)
        else:
            send_tg_message("ℹ️", "续期操作已执行", alert_text)
    else:
        print("ℹ️ 未检测到明确的提示框，可能续期操作未生效")
        send_tg_message("ℹ️", "续期操作已执行", "未检测到明确提示")
        sb.save_screenshot("18_no_alert.png")

def renew_server(sb):
    print("\n" + "#" * 25)
    print("  开始自动续期流程")
    print("#" * 25)
    if not _goto_server_overview(sb):
        return
    if not _click_renew_button(sb):
        return
    _check_renew_result(sb)

# ===== 主入口（强制要求代理环境变量，无默认值） =====
def main():
    print("#" * 25)
    print("   zampto 自动登录续期")
    print("#" * 25)

    # 不设置默认值，必须从环境变量读取
    proxy_str = os.environ.get("PROXY_SERVER", "").strip()
    if not proxy_str:
        proxy_str = os.environ.get("http_proxy", "").strip()
    if not proxy_str:
        proxy_str = os.environ.get("HTTP_PROXY", "").strip()
    if not proxy_str:
        print("❌ 错误：未检测到代理配置。")
        print("   请设置环境变量 PROXY_SERVER 或 http_proxy（由 setup_proxy.sh 自动设置）")
        print("   例如：export PROXY_SERVER='http://127.0.0.1:1080'")
        return  # 直接退出，不执行后续

    sb_kwargs = {"uc": True, "headless": False}
    print(f"🔗 使用代理: {proxy_str}")
    sb_kwargs["proxy"] = proxy_str

    print("🚀 启动浏览器...")
    with SB(**sb_kwargs) as sb:
        try:
            sb.open("https://api.ip.sb/ip")
            print(f"📍  当前出口IP: {sb.get_text('body')}")
        except Exception:
            pass

        if login(sb):
            renew_server(sb)
        else:
            print("\n❌ 登录失败，终止后续续期操作。")
            send_tg_message("❌", "登录失败", "未知")

if __name__ == "__main__":
    main()
