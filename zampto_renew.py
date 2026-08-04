#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import requests
import json
from seleniumbase import SB

EMAIL        = os.environ.get("ZAMTO_EMAIL") or ""
PASSWORD     = os.environ.get("ZAMTO_PASSWORD") or ""
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
BASE_URL = "https://dash.zampto.net"

def send_tg_message(status_icon, status_text, time_left=""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        masked_email = f"{name[:2]}****{name[-2:]}@{domain}" if len(name) > 4 else f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + '****'
    text = (f"🇫🇷 zampto 续期通知\n\n{status_icon} {status_text}\n"
            f"👤 续期账户: {masked_email}\n⏱️ 续期时间: {current_time_str}")
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
    except:
        pass

_EXPAND_JS = """..."""  # 保持原样，太长省略，实际请保留全部
_EXISTS_JS = """..."""
_SOLVED_JS = """..."""
_WININFO_JS = """..."""
_ALTCHA_EXPAND_JS = ""
_ALTCHA_SOLVED_JS = ""

def js_fill_input(sb, selector, text):
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

def _activate_window(): ...
def _xdotool_click(x, y): ...
def handle_turnstile(sb): ...  # 保持原样

def login(sb): ...  # 保持原样，但注意调用了 js_fill_input

def _read_alert(sb):
    try:
        el = sb.find_element("div.alert", timeout=4)
        return (el.text or "").strip()
    except:
        return ""

# ====== 修改后的两个函数 ======
def _goto_server_overview(sb) -> bool:
    print("\n🖥️  正在进入服务器详情页...")
    time.sleep(5)
    alert_text = _read_alert(sb)
    if alert_text and "can't renew" in alert_text.lower():
        print(f"ℹ️  页面提示: {alert_text}")
        send_tg_message("ℹ️", "⚠️ 未到续期时间", alert_text)
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
        print(f"当前 URL: {cur_url}\n页面标题: {title}")
        sb.save_screenshot("no_view_server.png")
        return False

    print("🖱️  点击 'View Server'...")
    view_btn.click()
    time.sleep(5)
    print(f"📄 当前页面: {sb.get_current_url()}")
    return True

def _click_renew_button(sb) -> bool:
    print("\n🔄 查找 Renew 按钮...")
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
        for el in sb.find_elements("button") + sb.find_elements("a"):
            txt = (el.text or "").strip()
            if "renew" in txt.lower():
                renew_btn = el
                print(f"✅ 通过文本找到 Renew: {txt}")
                break

    if renew_btn is None:
        print("ℹ️  未找到 Renew 按钮，可能已是付费用户或不在续期窗口")
        send_tg_message("ℹ️", "无需续期", "未找到 Renew 按钮")
        return False

    sb.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", renew_btn)
    time.sleep(1)
    renew_btn.click()
    print("🖱️  已点击 Renew 按钮")
    time.sleep(3)
    return True

def _check_renew_result(sb):
    print("\n📋 检查续期结果...")
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

def renew_server(sb):
    print("\n" + "#" * 25)
    print("  开始自动续期流程")
    print("#" * 25)
    if not _goto_server_overview(sb):
        return
    if not _click_renew_button(sb):
        return
    _check_renew_result(sb)

def main():
    print("#" * 25)
    print("   zampto 自动登录续期")
    print("#" * 25)
    IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
    proxy_str = os.environ.get("PROXY_SERVER", "").strip() or "http://127.0.0.1:1081"
    sb_kwargs = {"uc": True, "headless": False}
    if IS_PROXY:
        print(f"🔗 挂载代理: {proxy_str}")
        sb_kwargs["proxy"] = proxy_str
    else:
        print("🌐 未使用代理，直连访问")
    print("🚀 启动浏览器...")
    with SB(**sb_kwargs) as sb:
        try:
            sb.open("https://api.ip.sb/ip")
            print(f"📍  当前出口IP: {sb.get_text('body')}")
        except:
            pass
        if login(sb):
            renew_server(sb)
        else:
            print("\n❌ 登录失败，终止后续续期操作。")
            send_tg_message("❌", "登录失败", "未知")

if __name__ == "__main__":
    main()
