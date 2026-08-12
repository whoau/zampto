#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import requests
from seleniumbase import SB

# 从环境变量获取账号密码和 TG 配置
EMAIL        = os.environ.get("ZAM_PTO_EMAIL") or ""          # 登录邮箱
PASSWORD     = os.environ.get("ZAM_PTO_PASSWORD") or ""       # 账号密码
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""             # tg通知 chat id(可选)
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""           # tg通知bot token(可选)

BASE_URL = "https://dash.zampto.net"  # 网站链接

#  Telegram 推送模块
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

#  页面注入脚本（用于 Cloudflare Turnstile 展开）
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

# ===== ALTCHA 相关（与 katabump 相同，兼容 zampto 可能使用的验证码） =====
_ALTCHA_EXPAND_JS = """
(function() {
    var modal = document.querySelector('div.modal.show') || document;
    var iframes = modal.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var r = iframes[i].getBoundingClientRect();
        if (r.width > 0 && r.height > 0) {
            iframes[i].style.width  = '300px';
            iframes[i].style.height = '150px';
            iframes[i].style.minWidth  = '300px';
            iframes[i].style.minHeight = '150px';
            iframes[i].style.visibility = 'visible';
            iframes[i].style.opacity = '1';
            var el = iframes[i];
            for (var j = 0; j < 10; j++) {
                el = el.parentElement;
                if (!el) break;
                el.style.overflow = 'visible';
            }
            var r2 = iframes[i].getBoundingClientRect();
            return { cx: Math.round(r2.x + 30), cy: Math.round(r2.y + r2.height / 2) };
        }
    }
    return null;
})()
"""

_ALTCHA_SOLVED_JS = """
(function(){
    var modal = document.querySelector('div.modal.show') || document;
    var inputs = modal.querySelectorAll('input[type="hidden"]');
    for (var i = 0; i < inputs.length; i++) {
        var n = (inputs[i].name || '').toLowerCase();
        if ((n.includes('altcha') || n.includes('captcha')) &&
            inputs[i].value && inputs[i].value.length > 20) return true;
    }
    var cbs = modal.querySelectorAll('input[type="checkbox"]');
    for (var j = 0; j < cbs.length; j++) {
        if (cbs[j].disabled) return true;
    }
    var w = modal.querySelector('[data-state="verified"],.altcha--verified,.altcha-verified');
    if (w) return true;
    return false;
})()
"""

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
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
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

# ===== 登录 =====
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {BASE_URL}/auth/login")
    # 尝试两个常见的登录路径
    login_urls = [f"{BASE_URL}/auth/login", f"{BASE_URL}/login"]
    loaded = False
    for url in login_urls:
        try:
            sb.uc_open_with_reconnect(url, reconnect_time=8)
            time.sleep(5)
            if sb.is_element_present('input[name="email"]', timeout=3) or sb.is_element_present('input[name="Email"]', timeout=3):
                loaded = True
                break
        except:
            continue
    if not loaded:
        print("❌ 无法加载登录页面，请检查登录 URL")
        return False

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
            sb.save_screenshot("login_load_fail.png")
            return False

    # 关闭 Cookie 弹窗（如果有）
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

# ===== 自动续期流程 =====

def _read_alert(sb):
    """读取页面第一个 Bootstrap alert 的文本"""
    try:
        el = sb.find_element("div.alert", timeout=4)
        return (el.text or "").strip()
    except Exception:
        return ""

def _goto_server_detail(sb) -> bool:
    """在 Dashboard 首页查找并点击 View Server 进入服务器详情页"""
    print("\n🖥️  正在进入服务器续期页...")
    time.sleep(5)

    alert_text = _read_alert(sb)
    if alert_text and "can't renew" in alert_text.lower():
        print(f"ℹ️  页面顶部提示: {alert_text}")
        send_tg_message("ℹ️", "⚠️ 未到续期时间", alert_text)
        return False

    # 多种选择器查找 "View Server" 链接或按钮
    selectors = [
        'a[href*="/server/"]',          # 可能链接到 /server/xxx
        'a[href*="/servers/"]',
        'a:contains("View Server")',
        'button:contains("View Server")',
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

    # 如果未找到，遍历所有链接或按钮，通过文本匹配
    if view_btn is None:
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

def _click_renew_button(sb) -> bool:
    """点击 'Renew Server' 按钮（可能直接跳转或弹出模态框）"""
    print("\n🔄 查找 Renew Server 按钮...")
    selectors = [
        'button:contains("Renew Server")',
        'a:contains("Renew Server")',
        'button:contains("Renew")',
        'a:contains("Renew")',
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

    # 滚动到按钮
    sb.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", renew_btn)
    time.sleep(0.8)
    renew_btn.click()
    print("🖱️ 已点击 Renew Server 按钮")

    # 检查是否弹出模态框或页面变化
    time.sleep(3)
    # 如果弹出模态框，检测模态框
    if sb.is_element_present('div.modal.show', timeout=3):
        print("✅ 模态框已弹出")
        return True
    else:
        # 可能直接跳转或无需验证，视为成功
        print("ℹ️ 未检测到模态框，可能直接续期或跳转")
        return True

def _solve_altcha_if_present(sb) -> bool:
    """处理 ALTCHA 验证（如果存在）"""
    # 先检测是否有 ALTCHA 相关元素
    if not sb.is_element_present('div.modal.show iframe[src*="altcha"]', timeout=3):
        print("ℹ️ 未检测到 ALTCHA 验证框，跳过")
        return True

    print("\n🔐 处理 ALTCHA 人机验证...")
    time.sleep(2)

    if sb.execute_script(_ALTCHA_SOLVED_JS):
        print("✅ ALTCHA 已自动通过")
        return True

    coords = None
    try:
        coords = sb.execute_script(_ALTCHA_EXPAND_JS)
    except Exception:
        pass

    if coords:
        print(f"  📍 找到模态框内 iframe 坐标: ({coords['cx']}, {coords['cy']})")

    for attempt in range(3):
        if sb.execute_script(_ALTCHA_SOLVED_JS):
            print(f"✅ ALTCHA 验证通过（第 {attempt + 1} 轮）")
            return True

        if coords:
            try:
                wi = sb.execute_script(_WININFO_JS)
            except Exception:
                wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
            bar = wi["oh"] - wi["ih"]
            ax  = coords["cx"] + wi["sx"]
            ay  = coords["cy"] + wi["sy"] + bar
            print(f"🖱️  ALTCHA点击复选框  ({ax}, {ay})")
            _xdotool_click(ax, ay)

        try:
            iframes = sb.find_elements('div.modal.show iframe')
            for iframe in iframes:
                try:
                    iframe.click()
                    print("🖱️  SeleniumBase 点击模态框 iframe")
                except Exception:
                    pass
        except Exception:
            pass

        sb.execute_script("""
            (function(){
                var modal = document.querySelector('div.modal.show');
                if (!modal) return;
                var iframes = modal.querySelectorAll('iframe');
                for (var i = 0; i < iframes.length; i++) {
                    iframes[i].click();
                    iframes[i].dispatchEvent(new MouseEvent('click', {bubbles:true}));
                }
                var labels = modal.querySelectorAll('label');
                for (var j = 0; j < labels.length; j++) {
                    var txt = (labels[j].textContent || '').toLowerCase();
                    if (txt.includes('robot') || txt.includes('captcha') || txt.includes('verify'))
                        labels[j].click();
                }
                var cbs = modal.querySelectorAll('input[type="checkbox"]');
                for (var k = 0; k < cbs.length; k++) {
                    if (!cbs[k].disabled) {
                        cbs[k].click();
                        cbs[k].dispatchEvent(new MouseEvent('click', {bubbles:true}));
                    }
                }
            })()
        """)

        for _ in range(6):
            time.sleep(1)
            if sb.execute_script(_ALTCHA_SOLVED_JS):
                print(f"✅ ALTCHA 验证通过（第 {attempt + 1} 轮）")
                return True

        print(f"  ⚠️ 第 {attempt + 1} 轮未通过，重试...")
        try:
            new_coords = sb.execute_script(_ALTCHA_EXPAND_JS)
            if new_coords:
                coords = new_coords
        except Exception:
            pass

    print("  ❌ ALTCHA 3 轮均失败")
    return False

def _submit_renew(sb):
    """点击最终确认续期的按钮（可能在模态框内）"""
    print("🖱️  点击确认续期按钮...")
    # 尝试模态框内的提交按钮
    try:
        submit = sb.find_element('div.modal.show button.btn-primary', timeout=5)
        submit.click()
    except Exception:
        # 尝试查找包含 "Renew" 或 "Confirm" 的按钮
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
    """读取页面 alert 提示，判断续期结果并推送 TG 通知"""
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
        elif any(kw in low for kw in ( "renewed", "success", "extended", "completed")):
            send_tg_message("✅", "续期成功", alert_text)
        else:
            send_tg_message("ℹ️", "续期操作已执行", alert_text)
    else:
        print("ℹ️ 未检测到明确的提示框，可能续期操作未生效")
        send_tg_message("ℹ️", "续期操作已执行", "未检测到明确提示")

def renew_server(sb):
    """登录成功后调用：自动进入详情页 -> Renew -> 验证 -> 提交"""
    print("\n" + "#" * 25)
    print("  开始自动续期流程")
    print("#" * 25)

    if not _goto_server_detail(sb):
        return

    if not _click_renew_button(sb):
        return

    # 处理可能出现的验证码（ALTCHA 或 Turnstile 等）
    # 先尝试 ALTCHA，如果不是则尝试 Turnstile（如果有）
    altcha_ok = _solve_altcha_if_present(sb)
    if not altcha_ok:
        # 尝试 Turnstile（如果出现）
        if sb.is_element_present('iframe[src*="challenges.cloudflare.com"]', timeout=3):
            print("检测到 Turnstile，尝试处理...")
            if handle_turnstile(sb):
                print("✅ Turnstile 验证通过")
            else:
                print("⚠️ Turnstile 验证失败，仍尝试提交")
        else:
            print("⚠️ ALTCHA 验证未通过，仍尝试提交...")

    _submit_renew(sb)
    _check_renew_result(sb)

# ===== 主入口 =====
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
