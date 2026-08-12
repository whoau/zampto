#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import requests
from seleniumbase import SB

# ===== 环境变量（改名为 ZAM_PTO_*） =====
EMAIL        = os.environ.get("ZAM_PTO_EMAIL") or ""      # 登录邮箱
PASSWORD     = os.environ.get("ZAM_PTO_PASSWORD") or ""   # 账号密码
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""         # tg通知 chat id(可选)
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""       # tg通知bot token(可选)

BASE_URL = "https://dash.zampto.net"  # 网站链接（改了）

# ===== Telegram 推送（改文案） =====
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
        f"🇫🇷 zampto 续期通知\n\n"          # 改这里
        f"{status_icon} {status_text}\n"
        f"👤 续期账户: {masked_email}\n"
        f"⏱️ 续期时间: {current_time_str}"
    )

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text
    }
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("📩 Telegram 通知发送成功！")
        else:
            print(f"⚠️ Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"⚠️ Telegram 通知发送异常: {e}")

# ===== 以下验证码处理、输入工具、登录函数完全不变 =====
# （省略 _EXPAND_JS, _EXISTS_JS, _SOLVED_JS, _WININFO_JS, 
#   _ALTCHA_EXPAND_JS, _ALTCHA_SOLVED_JS, js_fill_input, 
#   _activate_window, _xdotool_click, handle_turnstile 等，均保持不变）
# 您把原代码中这些函数原样复制过来即可。

# ===== 登录函数（仅改页面标题判断） =====
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {BASE_URL}/auth/login")
    # 尝试两个路径（有的站点是 /login）
    try:
        sb.uc_open_with_reconnect(BASE_URL + "/auth/login", reconnect_time=8)
    except:
        sb.uc_open_with_reconnect(BASE_URL + "/login", reconnect_time=8)
    time.sleep(6)

    # 等待 Cloudflare 验证（同原代码）
    print("⏳ 等待 Cloudflare 验证通过...")
    cf_passed = False
    for i in range(30):
        page_src = sb.get_page_source() or ""
        if 'input[name="email"]' in page_src.lower() or 'name="email"' in page_src.lower():
            cf_passed = True
            print(f"✅ Cloudflare 验证已通过（{i+1}s）")
            break
        time.sleep(1)
    if not cf_passed:
        print("⚠️ Cloudflare 验证可能未通过，继续尝试...")

    try:
        sb.wait_for_element('input[name="email"]', timeout=15)
    except Exception:
        try:
            sb.wait_for_element('input[name="Email"]', timeout=5)
        except Exception:
            print("❌ 页面未加载出登录表单")
            cur_url = sb.get_current_url()
            page_title = sb.get_title() or ""
            print(f"  当前 URL: {cur_url}")
            print(f"  当前标题: {page_title}")
            sb.save_screenshot("login_load_fail.png")
            return False

    # 关闭 Cookie 弹窗（同原代码）
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

    # Turnstile 处理（同原代码）
    print("⏳ 等待 Turnstile 验证框出现...")
    ts_found = False
    for i in range(10):
        if sb.execute_script(_EXISTS_JS):
            ts_found = True
            print(f"✅ 检测到 Turnstile（{i+1}s）")
            break
        time.sleep(1)

    if ts_found:
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证失败")
            sb.save_screenshot("login_turnstile_fail.png")
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")

    print("🖱️ 敲击回车提交表单...")
    sb.press_keys('input[name="password"]', '\n')

    print("⏳ 等待登录跳转...")
    for _ in range(12):
        time.sleep(1)
        cur_url = sb.get_current_url().split('?')[0].lower()
        page_title = sb.get_title() or ""
        # 改判断：zampto 的 dashboard 关键词
        if "dashboard" in cur_url or "Dashboard" in page_title:
            break

    cur_url = sb.get_current_url().split('?')[0].lower()
    page_title = sb.get_title() or ""
    if "dashboard" in cur_url or "Dashboard" in page_title:
        print(f"✅ 登录成功！(URL: {sb.get_current_url()}, Title: {page_title})")
        return True
        
    print(f"❌ 登录失败，页面未跳转到账户页。(URL: {sb.get_current_url()}, Title: {page_title})")
    sb.save_screenshot("login_failed.png")
    return False

# ===== 自动续期流程（完全重写选择器） =====

def _read_alert(sb):
    try:
        el = sb.find_element("div.alert", timeout=4)
        return (el.text or "").strip()
    except Exception:
        return ""

def _goto_server_detail(sb) -> bool:
    print("\n🖥️  正在进入服务器续期页...")
    time.sleep(5)

    alert_text = _read_alert(sb)
    if alert_text and "can't renew" in alert_text.lower():
        print(f"ℹ️  页面顶部提示: {alert_text}")
        send_tg_message("ℹ️", "⚠️ 未到续期时间", alert_text)
        return False

    # zampto 的 "View Server" 按钮选择器
    selectors = [
        'a:contains("View Server")',
        'button:contains("View Server")',
        'a[href*="/server/"]',
        'button[data-target*="server"]',
        'a:contains("View")',
        'button:contains("View")',
    ]

    view_btn = None
    for sel in selectors:
        try:
            view_btn = sb.find_element(sel, timeout=8)
            print(f"✅ 通过选择器找到元素: {sel}")
            break
        except Exception:
            continue

    if view_btn is None:
        # 遍历所有 a 和 button
        print("⚠️ 选择器未命中，尝试遍历所有 a 和 button...")
        for tag in ['a', 'button']:
            try:
                elements = sb.find_elements(tag)
                for el in elements:
                    txt = (el.text or "").strip()
                    if "view server" in txt.lower() or "view" in txt.lower():
                        view_btn = el
                        print(f"✅ 通过文本 '{txt}' 找到元素")
                        break
                if view_btn:
                    break
            except Exception:
                pass

    if view_btn is None:
        print("❌ 未找到 'View Server' 按钮")
        sb.save_screenshot("servers_page_fail.png")
        return False

    print("🖱️  点击 'View Server' 进入详情页...")
    view_btn.click()
    time.sleep(5)
    print(f"📄 当前页面: {sb.get_current_url()}")
    return True

def _open_renew_modal(sb) -> bool:
    print("\n🔄 查找 Renew Server 按钮...")
    selectors = [
        'button:contains("Renew Server")',
        'a:contains("Renew Server")',
        'button:contains("Renew")',
        'a:contains("Renew")',
        'button[data-target*="renew"]',
    ]
    renew_btn = None
    for sel in selectors:
        try:
            renew_btn = sb.find_element(sel, timeout=5)
            print(f"✅ 通过选择器找到: {sel}")
            break
        except Exception:
            continue

    if renew_btn is None:
        print("❌ 未找到 Renew Server 按钮")
        return False

    sb.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", renew_btn)
    time.sleep(0.8)
    renew_btn.click()
    print("🖱️ 已点击 Renew Server 按钮")
    time.sleep(3)

    # 检查是否弹出模态框
    if sb.is_element_present('div.modal.show', timeout=3):
        print("✅ 模态框已弹出")
        return True
    else:
        # 可能直接跳转或无需验证
        print("ℹ️ 未检测到模态框，可能直接续期或跳转")
        return True

def _solve_altcha(sb) -> bool:
    # 完全复用原代码的 _solve_altcha，无需改动
    # （原代码中的 _ALTCHA_EXPAND_JS 和 _ALTCHA_SOLVED_JS 已经通用）
    pass  # 实际粘贴原函数

def _submit_renew(sb):
    print("🖱️  点击确认续期按钮...")
    # 尝试模态框内的提交按钮
    try:
        submit = sb.find_element('div.modal.show button.btn-primary', timeout=5)
        submit.click()
    except Exception:
        # 查找包含 Renew/Confirm 的按钮
        try:
            btns = sb.find_elements('div.modal.show button')
            for btn in btns:
                txt = (btn.text or "").lower()
                if "renew" in txt or "confirm" in txt or "submit" in txt:
                    btn.click()
                    break
        except Exception:
            pass
    time.sleep(3)

def _check_renew_result(sb):
    print("\n📋 检查续期结果...")
    alert_text = _read_alert(sb)
    if not alert_text:
        time.sleep(3)
        alert_text = _read_alert(sb)

    if alert_text:
        print(f"📩 页面提示: {alert_text}")
        low = alert_text.lower()
        if "can't renew" in low or "unable" in low or "already renewed" in low:
            send_tg_message("⏳", "未到续期时间或已续期", alert_text)
        elif any(kw in low for kw in ("renewed", "success", "extended", "completed")):
            send_tg_message("✅", "续期成功", alert_text)
        else:
            send_tg_message("ℹ️", "续期操作已执行", alert_text)
    else:
        print("ℹ️ 未检测到明确的提示框，可能续期操作未生效")
        send_tg_message("ℹ️", "续期操作已执行", "未检测到明确提示")

def renew_server(sb):
    print("\n" + "#" * 25)
    print("  开始自动续期流程（zampto）")
    print("#" * 25)

    if not _goto_server_detail(sb):
        return

    if not _open_renew_modal(sb):
        return

    # 处理可能的 ALTCHA（同原代码）
    altcha_ok = _solve_altcha(sb)   # 需复制原函数
    if not altcha_ok:
        print("⚠️ ALTCHA 验证未通过，仍尝试提交 Renew...")

    _submit_renew(sb)
    _check_renew_result(sb)

# ===== 主入口（代理逻辑完全保留） =====
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
        except Exception:
            pass

        if login(sb):
            renew_server(sb)
        else:
            print("\n❌ 登录失败，终止后续续期操作。")
            send_tg_message("❌", "登录失败", "未知")

if __name__ == "__main__":
    main()
