#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import re
import subprocess
import requests
from seleniumbase import SB
from datetime import datetime

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
# Cloudflare Turnstile 绕过
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
            print(f"✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
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

def extract_remaining_minutes(sb):
    """
    从页面源码中提取 'Expiry (Next Renewal)' 后面的相对剩余时间。
    优先匹配 <span> 标签内的时间。
    支持格式：
    - "1d 23h 58m"
    - "23h 58m"
    - "58m"
    - "Expired"
    返回总分钟数（int），Expired 返回 0，无法提取返回 None。
    """
    try:
        page_text = sb.get_page_source()
        
        # 先检查是否已过期
        if re.search(r'Expiry\s*\(Next Renewal\).*?Expired', page_text, re.IGNORECASE | re.DOTALL):
            print("⚠️ 检测到服务器已过期（Expired）")
            return 0
        
        # 方法1: 匹配 <span class="font-medium text-foreground">1d 23h 57m</span>
        span_match = re.search(
            r'Expiry\s*\(Next Renewal\).*?<span[^>]*>(\d+d\s*)?(\d+h\s*)?(\d+m\s*)?</span>',
            page_text,
            re.IGNORECASE | re.DOTALL
        )
        
        if span_match:
            days = int(re.search(r'(\d+)d', span_match.group(1)).group(1)) if span_match.group(1) else 0
            hours = int(re.search(r'(\d+)h', span_match.group(2)).group(1)) if span_match.group(2) else 0
            minutes = int(re.search(r'(\d+)m', span_match.group(3)).group(1)) if span_match.group(3) else 0
            
            total_minutes = days * 24 * 60 + hours * 60 + minutes
            if total_minutes > 0:
                print(f"✅ 成功提取时间（方法1-span标签）: {total_minutes} 分钟")
                return total_minutes
        
        # 方法2: 直接匹配纯文本 "1d 23h 58m"
        text_match = re.search(
            r'Expiry\s*\(Next Renewal\)[:\s]*(\d+d\s*)?(\d+h\s*)?(\d+m\s*)?',
            page_text,
            re.IGNORECASE
        )
        
        if text_match:
            days = int(re.search(r'(\d+)d', text_match.group(1)).group(1)) if text_match.group(1) else 0
            hours = int(re.search(r'(\d+)h', text_match.group(2)).group(1)) if text_match.group(2) else 0
            minutes = int(re.search(r'(\d+)m', text_match.group(3)).group(1)) if text_match.group(3) else 0
            
            total_minutes = days * 24 * 60 + hours * 60 + minutes
            if total_minutes > 0:
                print(f"✅ 成功提取时间（方法2-纯文本）: {total_minutes} 分钟")
                return total_minutes
        
        # 方法3: 使用 JavaScript 直接从 DOM 提取
        try:
            js_extract = """
            (function() {
                var spans = document.querySelectorAll('span.font-medium.text-foreground, span.text-foreground');
                for (var i = 0; i < spans.length; i++) {
                    var text = spans[i].textContent.trim();
                    if (/\d+[dhm]/.test(text)) {
                        return text;
                    }
                }
                
                // 检查是否过期
                var expiredSpans = document.querySelectorAll('span.text-red-400, span.font-medium.text-red-400');
                for (var i = 0; i < expiredSpans.length; i++) {
                    if (expiredSpans[i].textContent.trim().toLowerCase() === 'expired') {
                        return 'Expired';
                    }
                }
                
                return null;
            })();
            """
            time_text = sb.execute_script(js_extract)
            
            if time_text:
                if time_text.lower() == 'expired':
                    print("⚠️ 检测到服务器已过期（JavaScript 方法）")
                    return 0
                
                days = hours = minutes = 0
                d_match = re.search(r'(\d+)d', time_text)
                h_match = re.search(r'(\d+)h', time_text)
                m_match = re.search(r'(\d+)m', time_text)
                
                if d_match:
                    days = int(d_match.group(1))
                if h_match:
                    hours = int(h_match.group(1))
                if m_match:
                    minutes = int(m_match.group(1))
                
                total_minutes = days * 24 * 60 + hours * 60 + minutes
                if total_minutes > 0:
                    print(f"✅ 成功提取时间（方法3-JavaScript）: {total_minutes} 分钟")
                    return total_minutes
        except Exception as e:
            print(f"⚠️ JavaScript 提取失败: {e}")
        
        print("⚠️ 所有提取方法均未成功")
        return None
        
    except Exception as e:
        print(f"⚠️ 提取剩余时间异常: {e}")
        return None

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
    sb.update_text(EMAIL_SELECTOR, EMAIL)
    print(f"🔑 填写密码 ({PASSWORD_SELECTOR})……")
    sb.update_text(PASSWORD_SELECTOR, PASSWORD)
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
# 获取服务器 ID 列表
# ============================================================

def get_server_ids(sb) -> list:
    print("🔍 正在提取服务器 ID 列表...")
    time.sleep(5)

    server_ids = []

    try:
        page_text = sb.get_page_source()
        pattern = r'ID:\s*(\d+)'
        matches = re.findall(pattern, page_text)
        if matches:
            server_ids = list(set(matches))
            print(f"✅ 通过正则找到 {len(server_ids)} 个服务器 ID: {server_ids}")
            return server_ids
    except Exception as e:
        print(f"⚠️ 正则提取失败: {e}")

    try:
        all_elements = sb.find_elements("*")
        for elem in all_elements:
            text = (elem.text or "").strip()
            if "ID:" in text:
                parts = text.split("ID:")
                if len(parts) > 1:
                    id_part = parts[1].strip().split()[0]
                    if id_part.isdigit():
                        server_ids.append(id_part)
        if server_ids:
            server_ids = list(set(server_ids))
            print(f"✅ 通过遍历找到 {len(server_ids)} 个服务器 ID: {server_ids}")
            return server_ids
    except Exception as e:
        print(f"⚠️ 遍历提取失败: {e}")

    current_url = sb.get_current_url()
    if "id=" in current_url:
        import urllib.parse
        parsed = urllib.parse.urlparse(current_url)
        params = urllib.parse.parse_qs(parsed.query)
        if "id" in params:
            server_ids = params["id"]
            print(f"✅ 从当前 URL 提取到 ID: {server_ids}")
            return server_ids

    print("❌ 未能提取到任何服务器 ID")
    return []

# ============================================================
# 续期单个服务器（最终修复版 - 点击前提取时间）
# ============================================================

def renew_one_server_by_id(sb, server_id, index) -> dict:
    result = {
        "index": index,
        "server_id": server_id,
        "server_name": f"Server-{server_id}",
        "status": "unknown",
        "detail": ""
    }

    try:
        detail_url = f"{BASE_URL}/server?id={server_id}"
        print(f"\n🔄 正在处理第 {index+1} 个服务器: ID={server_id}")
        print(f"🌐 打开详情页: {detail_url}")

        sb.get(detail_url)

        print("⏳ 等待页面关键内容加载...")
        try:
            sb.wait_for_text("Server last renewed", timeout=15)
            print("✅ 检测到 'Server last renewed' 文字")
        except Exception:
            try:
                sb.wait_for_text("Expiry (Next Renewal)", timeout=10)
                print("✅ 检测到 'Expiry (Next Renewal)' 文字")
            except Exception:
                print("⚠️ 未检测到预期文字，但继续尝试...")

        time.sleep(3)

        current_url = sb.get_current_url()
        if "server" not in current_url.lower():
            result["status"] = "failed"
            result["detail"] = "未进入详情页"
            print(f"❌ 未进入详情页，当前 URL: {current_url}")
            return result

        print(f"📄 当前页面: {current_url}")

        # ---------- 1. 【关键】点击前提取原始剩余时间 ----------
        old_minutes = extract_remaining_minutes(sb)
        if old_minutes is not None:
            if old_minutes == 0:
                print(f"📅 原始状态: 已过期（Expired）")
            else:
                print(f"📅 原始剩余时间: {old_minutes} 分钟 ({old_minutes//1440}d {(old_minutes%1440)//60}h {old_minutes%60}m)")
        else:
            print("⚠️ 未能提取原始剩余时间")

        # ---------- 2. 点击续期按钮 ----------
        click_success = False
        
        print("🖱️ 方式1: 通过 XPath 精确定位并 JavaScript 点击")
        click_script_1 = """
        (function() {
            var xpath = "//div[@data-slot='card'][.//div[contains(text(),'Server last renewed')]]//button[normalize-space()='Renew Server']";
            var button = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if (button) {
                button.scrollIntoView({behavior: 'smooth', block: 'center'});
                button.click();
                return 'success';
            }
            return 'not_found';
        })();
        """
        try:
            time.sleep(1)
            result_msg = sb.execute_script(click_script_1)
            if result_msg == 'success':
                print("✅ XPath 定位并点击成功")
                click_success = True
        except Exception as e1:
            print(f"⚠️ XPath 方式失败: {e1}")

        if not click_success:
            print("🖱️ 方式2: 通过按钮文本查找并 JavaScript 点击")
            click_script_2 = """
            (function() {
                var buttons = document.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    if (buttons[i].textContent.trim() === 'Renew Server') {
                        buttons[i].scrollIntoView({behavior: 'smooth', block: 'center'});
                        buttons[i].click();
                        return 'success';
                    }
                }
                return 'not_found';
            })();
            """
            try:
                time.sleep(1)
                result_msg = sb.execute_script(click_script_2)
                if result_msg == 'success':
                    print("✅ 按钮文本定位并点击成功")
                    click_success = True
            except Exception as e2:
                print(f"⚠️ 按钮文本方式失败: {e2}")

        if not click_success:
            result["status"] = "error"
            result["detail"] = "无法点击续期按钮"
            print(f"❌ {result['detail']}")
            sb.save_screenshot(f"click_failed_{server_id}.png")
            return result

        # ---------- 3. 点击后等待并尝试处理 Turnstile（但不强制成功） ----------
        print("⏳ 等待页面响应...")
        time.sleep(8)  # 增加等待时间，让续期操作完成
        
        print("🛡️ 检查是否出现 Turnstile 验证...")
        turnstile_handled = False
        for check_attempt in range(3):
            time.sleep(1)
            if sb.execute_script(_EXISTS_JS):
                print(f"🔍 检测到 Turnstile（第 {check_attempt + 1} 次检查），尝试处理...")
                if handle_turnstile(sb):
                    print("✅ Turnstile 验证通过")
                    turnstile_handled = True
                    break
                else:
                    print("⚠️ Turnstile 验证失败，但继续检查续期结果...")
                    # 不立即返回失败，继续检查时间变化
                    break
            
            # 检查是否已经有成功提示
            alert_text = read_alert(sb)
            if alert_text and any(kw in alert_text.lower() for kw in ("renewed", "success", "extended")):
                print("ℹ️ 检测到成功提示，无需 Turnstile")
                turnstile_handled = True
                break
        else:
            print("ℹ️ 未检测到 Turnstile，可能已自动通过")
            turnstile_handled = True

        # ---------- 4. 重新加载详情页获取最新剩余时间 ----------
        print("⏳ 重新加载详情页获取最新状态...")
        time.sleep(3)
        try:
            sb.get(detail_url)
            sb.wait_for_text("Server last renewed", timeout=15)
            time.sleep(3)
        except Exception as e:
            print(f"⚠️ 重新打开详情页失败: {e}")

        new_minutes = extract_remaining_minutes(sb)
        if new_minutes is not None:
            if new_minutes == 0:
                print(f"📅 新状态: 仍为过期（Expired）")
            else:
                print(f"📅 新剩余时间: {new_minutes} 分钟 ({new_minutes//1440}d {(new_minutes%1440)//60}h {new_minutes%60}m)")
        else:
            print("⚠️ 未能提取新剩余时间")

        # ---------- 5. 读取提示 ----------
        alert_text = read_alert(sb)
        if alert_text:
            print(f"📩 页面提示: {alert_text}")

        # ---------- 6. 【核心】基于时间变化判定（优先级最高） ----------
        if old_minutes is not None and new_minutes is not None:
            time_change = new_minutes - old_minutes
            
            # 场景1: 时间显著增加（通常续期会增加 28-30 天）
            if time_change > 1000:  # 增加超过 16 小时（1000分钟）
                result["status"] = "success"
                result["detail"] = f"✅ 续期成功！时间从 {old_minutes//1440}d{(old_minutes%1440)//60}h 增加到 {new_minutes//1440}d{(new_minutes%1440)//60}h"
                print(f"✅ 续期成功：剩余时间增加 {time_change} 分钟")
                sb.save_screenshot(f"renew_success_{server_id}.png")
                return result
            
            # 场景2: 从过期恢复（0 -> 任意正数）
            elif old_minutes == 0 and new_minutes > 0:
                result["status"] = "success"
                result["detail"] = f"✅ 从过期状态恢复！新剩余时间: {new_minutes//1440}d{(new_minutes%1440)//60}h"
                print(f"✅ 续期成功：从过期恢复")
                sb.save_screenshot(f"renew_success_{server_id}.png")
                return result
            
            # 场景3: 时间未变化或减少（自然流逝）
            elif -10 < time_change < 100:  # 允许 -10 到 +100 分钟的误差
                result["status"] = "skipped"
                result["detail"] = f"⏭️ 可能已续期或未到期（时间变化: {time_change} 分钟）"
                print(f"⏭️ 跳过：时间变化不明显")
            else:
                result["status"] = "unknown"
                result["detail"] = f"时间变化异常: {time_change} 分钟"
                print(f"⚠️ 时间变化异常")
        
        # 如果时间提取失败，依赖提示判断
        elif alert_text:
            lowered = alert_text.lower()
            if any(kw in lowered for kw in ("renewed", "success", "extended", "completed")):
                result["status"] = "success"
                result["detail"] = alert_text
                print("✅ 续期成功（根据提示判断）")
            elif any(kw in lowered for kw in ("can't renew", "unable", "failed", "error")):
                result["status"] = "failed"
                result["detail"] = alert_text
                print("❌ 续期失败（根据提示判断）")
            else:
                result["status"] = "unknown"
                result["detail"] = alert_text
        else:
            result["status"] = "unknown"
            result["detail"] = f"无法确认（原: {old_minutes}, 新: {new_minutes}, Turnstile: {turnstile_handled}）"
            print("⚠️ 无法确认续期结果")

        sb.save_screenshot(f"renew_result_{server_id}.png")
        return result

    except Exception as e:
        print(f"⚠️ 处理服务器 ID={server_id} 时发生异常: {e}")
        result["status"] = "error"
        result["detail"] = str(e)
        sb.save_screenshot(f"exception_{server_id}.png")
        return result

# ============================================================
# 主续期流程
# ============================================================

def renew_all_servers_by_id(sb) -> list:
    print("\n" + "#" * 25)
    print("   开始 ZamPTO 自动续期流程（通过服务器 ID）")
    print("#" * 25)

    server_ids = get_server_ids(sb)

    if not server_ids:
        print("❌ 未获取到任何服务器 ID")
        return []

    print(f"📋 待续期服务器 ID 列表: {server_ids}")

    results = []
    for idx, server_id in enumerate(server_ids):
        result = renew_one_server_by_id(sb, server_id, idx)
        results.append(result)
        print(f"📊 第 {idx+1} 个服务器 (ID={server_id}) 续期结果: {result['status']} - {result['detail']}")

    total = len(results)
    success = sum(1 for r in results if r['status'] == 'success')
    skipped = sum(1 for r in results if r['status'] == 'skipped')
    failed = sum(1 for r in results if r['status'] in ('failed', 'error', 'unknown'))

    summary = (
        f"续期完成：共 {total} 个服务器\n"
        f"✅ 成功: {success}\n"
        f"⏭️ 跳过: {skipped}\n"
        f"❌ 失败/未知: {failed}"
    )
    detail_lines = []
    for r in results:
        detail_lines.append(f"  #{r['index']+1} ID={r['server_id']}: {r['status']} - {r['detail']}")
    detail = "\n".join(detail_lines)

    send_tg_message("📋", summary, detail)
    print(summary)
    print("详细结果:\n" + detail)

    return results

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
                renew_all_servers_by_id(sb)
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
