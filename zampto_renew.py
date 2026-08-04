#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import requests
from seleniumbase import SB

# ===== 环境变量 =====
EMAIL        = os.environ.get("ZAMTO_EMAIL") or ""
PASSWORD     = os.environ.get("ZAMTO_PASSWORD") or ""
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""

IS_PROXY     = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER", "").strip() or "http://127.0.0.1:1081"

BASE_URL = "https://dash.zampto.net"

# ===== Telegram 推送 =====
def send_tg_message(status_icon, status_text, detail=""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG 变量，跳过推送。")
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        masked_email = f"{name[:2]}****{name[-2:]}@{domain}" if len(name) > 4 else f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + '****'

    text = (
        f"🇫🇷 Zampto 续期通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 账户: {masked_email}\n"
        f"⏱️ 时间: {current_time_str}"
    )
    if detail:
        text += f"\n📝 {detail}"

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("📩 TG 通知成功")
        else:
            print(f"⚠️ TG 通知失败: {r.text}")
    except Exception as e:
        print(f"⚠️ TG 异常: {e}")

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

# ===== Turnstile 处理函数 =====
def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile...")
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
            print(f"✅ Turnstile 通过（第 {attempt} 次）")
            return True

        print(f"🖱️ 第 {attempt+1} 次调用 uc_gui_click_captcha...")
        try:
            sb.uc_gui_click_captcha()
        except Exception as e:
            print(f"⚠️ 调用异常: {e}")

        for _ in range(16):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"✅ Turnstile 通过（第 {attempt+1} 次）")
                return True

        print(f"⚠️ 第 {attempt+1} 次未通过，重试...")

    print("❌ Turnstile 6 次均失败")
    return False

# ===== JS 填充输入 =====
def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, "{safe_text}");
        }} else {{
            el.value = "{safe_text}";
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)

# ===== 登录 =====
def login(sb) -> bool:
    print(f"🌐 打开登录页: {BASE_URL}/auth/login")
    sb.uc_open_with_reconnect(BASE_URL + "/auth/login", reconnect_time=8)
    time.sleep(5)

    # 等待登录表单
    try:
        sb.wait_for_element('input[name="email"]', timeout=15)
    except Exception:
        try:
            sb.wait_for_element('input[type="email"]', timeout=5)
        except Exception:
            print("❌ 登录表单未加载")
            sb.save_screenshot("login_load_fail.png")
            return False

    print("📧 填写邮箱...")
    js_fill_input(sb, 'input[name="email"]', EMAIL)
    time.sleep(0.5)

    print("🔑 填写密码...")
    js_fill_input(sb, 'input[name="password"]', PASSWORD)
    time.sleep(0.5)

    # 检测 Turnstile
    print("⏳ 检测 Turnstile...")
    ts_found = False
    for i in range(10):
        if sb.execute_script(_EXISTS_JS):
            ts_found = True
            print(f"✅ 检测到 Turnstile（{i+1}s）")
            break
        time.sleep(1)

    if ts_found:
        if not handle_turnstile(sb):
            print("❌ Turnstile 验证失败")
            sb.save_screenshot("turnstile_fail.png")
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")

    print("🖱️ 提交登录...")
    try:
        sb.find_element('button[type="submit"]', timeout=5).click()
    except:
        sb.press_keys('input[name="password"]', '\n')

    time.sleep(5)
    cur_url = sb.get_current_url()
    if "/overview" in cur_url or "/dashboard" in cur_url:
        print(f"✅ 登录成功！({cur_url})")
        return True

    print(f"❌ 登录失败，当前 URL: {cur_url}")
    sb.save_screenshot("login_failed.png")
    return False

# ===== 续期 =====
def renew_server(sb) -> bool:
    print("\n" + "#" * 30)
    print("  开始自动续期")
    print("#" * 30)

    print("\n📂 进入概览...")
    sb.get(BASE_URL + "/overview")
    time.sleep(5)

    page_src = sb.get_page_source()
    if "renew" not in page_src.lower():
        print("ℹ️ 未检测到 Renew，可能无需续期")
        send_tg_message("ℹ️", "无需续期", "未发现 Renew 按钮")
        return True

    # 查找 Manage 按钮
    print("🔍 查找服务器...")
    manage_btn = None
    for sel in ['a[href*="/manage"]', 'button:contains("Manage")', 'a:contains("Manage")']:
        try:
            manage_btn = sb.find_element(sel, timeout=3)
            break
        except:
            continue

    if manage_btn is None:
        for el in sb.find_elements("a") + sb.find_elements("button"):
            if "manage" in (el.text or "").lower():
                manage_btn = el
                break

    if manage_btn is None:
        print("❌ 未找到 Manage Server")
        sb.save_screenshot("no_manage.png")
        send_tg_message("⚠️", "未找到服务器", "可能没有运行中的服务器")
        return False

    print("🖱️ 点击 Manage...")
    manage_btn.click()
    time.sleep(5)

    # 查找 Renew 按钮
    print("🔄 查找 Renew...")
    renew_btn = None
    try:
        renew_btn = sb.find_element('button:contains("Renew")', timeout=5)
    except:
        try:
            renew_btn = sb.find_element('a:contains("Renew")', timeout=3)
        except:
            pass

    if renew_btn is None:
        for el in sb.find_elements("button") + sb.find_elements("a"):
            if "renew" in (el.text or "").lower():
                renew_btn = el
                break

    if renew_btn is None:
        print("ℹ️ 未找到 Renew，可能已付费或不在窗口期")
        send_tg_message("ℹ️", "无需续期", "未找到 Renew 按钮")
        return True

    print("🖱️ 点击 Renew...")
    renew_btn.click()
    time.sleep(3)

    # 检查结果
    print("📋 检查结果...")
    time.sleep(2)
    page_src = sb.get_page_source()
    if "success" in page_src.lower() or "renewed" in page_src.lower():
        print("✅ 续期成功")
        send_tg_message("✅", "续期成功", "服务器已续期")
        return True
    else:
        print("⚠️ 续期操作完成，未明确成功标志")
        send_tg_message("ℹ️", "续期操作已执行", "请人工确认")
        return True

# ===== 主入口 =====
def main():
    print("#" * 30)
    print("   Zampto 自动续期（带 Turnstile）")
    print("#" * 30)

    if not EMAIL or not PASSWORD:
        print("❌ 请设置 ZAMTO_EMAIL 和 ZAMTO_PASSWORD")
        return

    sb_kwargs = {"uc": True, "headless": False}
    if IS_PROXY:
        print(f"🔗 使用代理: {PROXY_SERVER}")
        sb_kwargs["proxy"] = PROXY_SERVER
    else:
        print("🌐 直连")

    with SB(**sb_kwargs) as sb:
        # 显示出口 IP
        try:
            sb.open("https://api.ip.sb/ip")
            print(f"📍 IP: {sb.get_text('body')}")
        except:
            pass

        if login(sb):
            renew_server(sb)
        else:
            send_tg_message("❌", "登录失败", "请检查账号密码")

if __name__ == "__main__":
    main()
