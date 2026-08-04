#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import requests
from seleniumbase import SB

# ===== 环境变量读取 =====
EMAIL        = os.environ.get("ZAMTO_EMAIL") or ""
PASSWORD     = os.environ.get("ZAMTO_PASSWORD") or ""
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""

# 代理相关（与原 Katabump 脚本一致）
IS_PROXY     = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER", "").strip() or "http://127.0.0.1:1081"

BASE_URL = "https://dash.zampto.net"

# ===== Telegram 推送模块 =====
def send_tg_message(status_icon, status_text, detail=""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    # 邮箱脱敏
    if '@' in EMAIL:
        name, domain = EMAIL.split('@', 1)
        if len(name) > 4:
            masked_email = f"{name[:2]}****{name[-2:]}@{domain}"
        else:
            masked_email = f"{name}@{domain}"
    else:
        masked_email = EMAIL[:2] + '****'

    text = (
        f"🇫🇷 Zampto 续期通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 续期账户: {masked_email}\n"
        f"⏱️ 执行时间: {current_time_str}"
    )
    if detail:
        text += f"\n📝 详情: {detail}"

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


# ===== 底层输入工具 =====
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


# ===== 登录模块 =====
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {BASE_URL}/auth/login")
    sb.uc_open_with_reconnect(BASE_URL + "/auth/login", reconnect_time=8)
    time.sleep(5)

    print("⏳ 等待登录表单加载...")
    try:
        sb.wait_for_element('input[name="email"]', timeout=15)
    except Exception:
        try:
            sb.wait_for_element('input[type="email"]', timeout=5)
        except Exception:
            print("❌ 页面未加载出登录表单")
            sb.save_screenshot("login_load_fail.png")
            return False

    print(f"📧 填写邮箱...")
    js_fill_input(sb, 'input[name="email"]', EMAIL)
    time.sleep(0.5)

    print("🔑 填写密码...")
    js_fill_input(sb, 'input[name="password"]', PASSWORD)
    time.sleep(0.5)

    print("🖱️ 点击登录按钮...")
    try:
        login_btn = sb.find_element('button[type="submit"]', timeout=5)
        login_btn.click()
    except Exception:
        for btn in sb.find_elements("button"):
            if "login" in (btn.text or "").lower() or "sign in" in (btn.text or "").lower():
                btn.click()
                break
        else:
            sb.press_keys('input[name="password"]', '\n')

    print("⏳ 等待登录跳转...")
    time.sleep(5)

    cur_url = sb.get_current_url()
    if "/overview" in cur_url or "/dashboard" in cur_url:
        print(f"✅ 登录成功！(URL: {cur_url})")
        return True

    print(f"❌ 登录失败，当前 URL: {cur_url}")
    sb.save_screenshot("login_failed.png")
    return False


# ===== 续期模块 =====
def renew_server(sb) -> bool:
    print("\n" + "#" * 30)
    print("  开始自动续期流程")
    print("#" * 30)

    # Step 1: 进入概览页面
    print("\n📂 进入服务器概览页面...")
    sb.get(BASE_URL + "/overview")
    time.sleep(5)

    page_source = sb.get_page_source()
    if "renew" not in page_source.lower():
        print("ℹ️ 页面未检测到 Renew 相关元素，可能已是付费用户或无服务器需要续期")
        send_tg_message("ℹ️", "无需续期", "未检测到 Renew 按钮（可能已是付费用户）")
        return True

    # Step 2: 查找 Manage Server 按钮
    print("\n🔍 查找服务器...")
    manage_btn = None
    selectors = [
        'a[href*="/manage"]',
        'button:contains("Manage")',
        'a:contains("Manage")',
        '.btn:contains("Manage")',
    ]
    for sel in selectors:
        try:
            manage_btn = sb.find_element(sel, timeout=3)
            print(f"✅ 通过选择器找到 Manage 按钮: {sel}")
            break
        except Exception:
            continue

    if manage_btn is None:
        print("⚠️ 选择器未命中，尝试遍历页面元素...")
        try:
            for el in sb.find_elements("a"):
                if "manage" in (el.text or "").lower():
                    manage_btn = el
                    print("✅ 通过文本 'Manage' 找到链接")
                    break
            if manage_btn is None:
                for el in sb.find_elements("button"):
                    if "manage" in (el.text or "").lower():
                        manage_btn = el
                        print("✅ 通过文本 'Manage' 找到按钮")
                        break
        except Exception:
            pass

    if manage_btn is None:
        print("❌ 未找到 Manage Server 按钮")
        sb.save_screenshot("no_manage_btn.png")
        send_tg_message("⚠️", "未找到服务器", "可能没有运行中的服务器")
        return False

    print("🖱️ 点击 Manage Server...")
    manage_btn.click()
    time.sleep(5)

    # Step 3: 查找 Renew 按钮
    print("\n🔄 查找 Renew 按钮...")
    renew_btn = None
    try:
        renew_btn = sb.find_element('button:contains("Renew")', timeout=5)
    except Exception:
        try:
            renew_btn = sb.find_element('a:contains("Renew")', timeout=3)
        except Exception:
            pass

    if renew_btn is None:
        try:
            for el in sb.find_elements("button"):
                if "renew" in (el.text or "").lower():
                    renew_btn = el
                    break
            if renew_btn is None:
                for el in sb.find_elements("a"):
                    if "renew" in (el.text or "").lower():
                        renew_btn = el
                        break
        except Exception:
            pass

    if renew_btn is None:
        print("ℹ️ 未找到 Renew 按钮，可能已是付费用户或不在续期窗口内")
        send_tg_message("ℹ️", "无需续期", "未找到 Renew 按钮")
        return True

    print("🖱️ 点击 Renew 按钮...")
    renew_btn.click()
    time.sleep(3)

    # Step 4: 检查续期结果
    print("\n📋 检查续期结果...")
    time.sleep(2)
    page_source = sb.get_page_source()
    if "success" in page_source.lower() or "renewed" in page_source.lower():
        print("✅ 续期成功！")
        send_tg_message("✅", "续期成功", "服务器已成功续期")
        return True
    elif "error" in page_source.lower() or "failed" in page_source.lower():
        print("❌ 续期失败")
        sb.save_screenshot("renew_failed.png")
        send_tg_message("❌", "续期失败", "请检查账户状态")
        return False
    else:
        print("ℹ️ 续期操作已执行，请手动确认结果")
        send_tg_message("ℹ️", "续期操作已执行", "请登录仪表盘确认")
        return True


# ===== 主入口 =====
def main():
    print("#" * 30)
    print("   Zampto 自动登录续期（支持代理）")
    print("#" * 30)

    if not EMAIL or not PASSWORD:
        print("❌ 请设置环境变量 ZAMTO_EMAIL 和 ZAMTO_PASSWORD")
        return

    sb_kwargs = {"uc": True, "headless": False}

    if IS_PROXY:
        print(f"🔗 使用代理: {PROXY_SERVER}")
        sb_kwargs["proxy"] = PROXY_SERVER
    else:
        print("🌐 未使用代理，直连访问")

    print("🚀 启动浏览器...")
    with SB(**sb_kwargs) as sb:
        # 打印出口 IP（确认代理是否生效）
        try:
            sb.open("https://api.ip.sb/ip")
            print(f"📍 当前出口 IP: {sb.get_text('body')}")
        except Exception:
            pass

        if login(sb):
            renew_server(sb)
        else:
            print("\n❌ 登录失败，终止后续续期操作。")
            send_tg_message("❌", "登录失败", "请检查账号密码")


if __name__ == "__main__":
    main()
