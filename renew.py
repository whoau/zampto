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
        if re.search(r'Expiry\s*\(Next Renewal\)[:\s]*.*?Expired', page_text, re.IGNORECASE | re.DOTALL):
            print("⚠️ 检测到服务器已过期（Expired）")
            return 0
        
        # 匹配 "1d 23h 58m" 格式（更宽松的匹配）
        # 修复：使用非贪婪匹配，避免跨越多个元素
        match = re.search(
            r'Expiry\s*\(Next Renewal\)[:\s]*.*?(?:(\d+)\s*d\s*)?(?:(\d+)\s*h\s*)?(?:(\d+)\s*m\s*)?',
            page_text,
            re.IGNORECASE | re.DOTALL
        )
        
        if not match:
            print("⚠️ 未找到剩余时间匹配")
            return None

        days = int(match.group(1)) if match.group(1) else 0
        hours = int(match.group(2)) if match.group(2) else 0
        minutes = int(match.group(3)) if match.group(3) else 0

        # 如果三个值都是 0，说明可能匹配失败
        if days == 0 and hours == 0 and minutes == 0:
            print("⚠️ 匹配到的时间全为 0，可能是格式不符")
            return None

        total_minutes = days * 24 * 60 + hours * 60 + minutes
        return total_minutes
        
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
# 续期单个服务器（完全修复版）
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

        time.sleep(3)  # 增加等待时间，确保页面完全加载

        current_url = sb.get_current_url()
        if "server" not in current_url.lower():
            result["status"] = "failed"
            result["detail"] = "未进入详情页"
            print(f"❌ 未进入详情页，当前 URL: {current_url}")
            return result

        print(f"📄 当前页面: {current_url}")

        # ---------- 1. 提取原始剩余时间 ----------
        old_minutes = extract_remaining_minutes(sb)
        if old_minutes is not None:
            if old_minutes == 0:
                print(f"📅 原始状态: 已过期（Expired）")
            else:
                print(f"📅 原始剩余时间: {old_minutes} 分钟 ({old_minutes//1440}d {(old_minutes%1440)//60}h {old_minutes%60}m)")
        else:
            print("⚠️ 未能提取原始剩余时间，将依赖提示判断")

        # ---------- 2. 使用纯 JavaScript 查找并点击按钮（修复闭包问题） ----------
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
            time.sleep(1)  # 确保页面稳定
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
            print("🖱️ 方式3: 通过 data-slot 和文本组合查找")
            click_script_3 = """
            (function() {
                var cards = document.querySelectorAll('div[data-slot="card"]');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    if (card.textContent.includes('Server last renewed')) {
                        var buttons = card.querySelectorAll('button');
                        for (var j = 0; j < buttons.length; j++) {
                            if (buttons[j].textContent.includes('Renew Server')) {
                                buttons[j].scrollIntoView({behavior: 'smooth', block: 'center'});
                                buttons[j].click();
                                return 'success';
                            }
                        }
                    }
                }
                return 'not_found';
            })();
            """
            try:
                time.sleep(1)
                result_msg = sb.execute_script(click_script_3)
                if result_msg == 'success':
                    print("✅ data-slot 组合定位并点击成功")
                    click_success = True
            except Exception as e3:
                print(f"⚠️ data-slot 方式失败: {e3}")

        if not click_success:
            print("🖱️ 方式4: 通过渐变背景样式查找按钮")
            click_script_4 = """
            (function() {
                var buttons = document.querySelectorAll('button');
                for (var i = 0; i < buttons.length; i++) {
                    var classList = buttons[i].className;
                    if (classList.includes('from-purple-600') && 
                        classList.includes('to-purple-700') && 
                        buttons[i].textContent.includes('Renew Server')) {
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
                result_msg = sb.execute_script(click_script_4)
                if result_msg == 'success':
                    print("✅ 样式类定位并点击成功")
                    click_success = True
            except Exception as e4:
                print(f"⚠️ 样式类方式失败: {e4}")

        if not click_success:
            print("🖱️ 方式5: xdotool 物理点击（最后备选）")
            try:
                mark_script = """
                (function() {
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        if (buttons[i].textContent.trim() === 'Renew Server') {
                            buttons[i].setAttribute('data-renew-target', 'true');
                            buttons[i].scrollIntoView({behavior: 'smooth', block: 'center'});
                            return 'marked';
                        }
                    }
                    return 'not_found';
                })();
                """
                mark_result = sb.execute_script(mark_script)
                
                if mark_result == 'marked':
                    time.sleep(1)
                    
                    coords_script = """
                    (function() {
                        var btn = document.querySelector('button[data-renew-target="true"]');
                        if (!btn) return null;
                        var rect = btn.getBoundingClientRect();
                        return {
                            x: Math.round(rect.left + rect.width / 2),
                            y: Math.round(rect.top + rect.height / 2)
                        };
                    })();
                    """
                    coords = sb.execute_script(coords_script)
                    
                    if coords:
                        win_script = """
                        (function() {
                            return {
                                sx: window.screenX || 0,
                                sy: window.screenY || 0,
                                oh: window.outerHeight || 0,
                                ih: window.innerHeight || 0
                            };
                        })();
                        """
                        win_info = sb.execute_script(win_script)
                        
                        bar = win_info.get('oh', 0) - win_info.get('ih', 0)
                        if bar < 0 or bar > 200:
                            bar = 80
                        
                        screen_x = coords['x'] + win_info.get('sx', 0)
                        screen_y = coords['y'] + win_info.get('sy', 0) + bar
                        
                        print(f"   准备点击坐标: ({screen_x}, {screen_y})")
                        _xdotool_click(screen_x, screen_y)
                        print("✅ xdotool 物理点击成功")
                        click_success = True
                        
            except Exception as e5:
                print(f"⚠️ xdotool 方式失败: {e5}")

        if not click_success:
            result["status"] = "error"
            result["detail"] = "所有点击方式均失败"
            print(f"❌ {result['detail']}")
            sb.save_screenshot(f"click_all_failed_{server_id}.png")
            return result

        # ---------- 3. 点击后等待页面响应 ----------
        print("⏳ 等待页面响应...")
        time.sleep(3)  # 先等待基本响应
        
        # ---------- 4. 检测并处理 Turnstile（优先级高） ----------
        print("🛡️ 检查续期后是否出现 Turnstile 验证...")
        for check_attempt in range(5):  # 最多检查 5 次
            time.sleep(1)
            if sb.execute_script(_EXISTS_JS):
                print(f"🔍 检测到 Turnstile（第 {check_attempt + 1} 次检查），开始处理...")
                if not handle_turnstile(sb):
                    result["status"] = "error"
                    result["detail"] = "续期后 Turnstile 验证失败"
                    sb.save_screenshot(f"turnstile_after_renew_{server_id}.png")
                    return result
                print("✅ Turnstile 验证通过")
                break
            
            # 检查是否已经有成功提示（说明没有验证码）
            alert_text = read_alert(sb)
            if alert_text and any(kw in alert_text.lower() for kw in ("renewed", "success", "extended")):
                print("ℹ️ 检测到成功提示，无需 Turnstile")
                break
        else:
            print("ℹ️ 未检测到 Turnstile")

        # ---------- 5. 重新加载详情页获取最新剩余时间 ----------
        print("⏳ 等待续期处理完成，重新加载详情页...")
        time.sleep(5)
        try:
            sb.get(detail_url)
            sb.wait_for_text("Server last renewed", timeout=15)
            time.sleep(3)
        except Exception as e:
            print(f"⚠️ 重新打开详情页失败: {e}，尝试使用当前页面数据")

        new_minutes = extract_remaining_minutes(sb)
        if new_minutes is not None:
            if new_minutes == 0:
                print(f"📅 新状态: 仍为过期（Expired）")
            else:
                print(f"📅 新剩余时间: {new_minutes} 分钟 ({new_minutes//1440}d {(new_minutes%1440)//60}h {new_minutes%60}m)")
        else:
            print("⚠️ 未能提取新剩余时间")

        # ---------- 6. 读取提示（辅助） ----------
        alert_text = read_alert(sb)
        if alert_text:
            print(f"📩 页面提示: {alert_text}")

        # ---------- 7. 综合判定（多重验证） ----------
        success_indicators = 0
        fail_indicators = 0
        
        # 指标1: 时间对比
        if old_minutes is not None and new_minutes is not None:
            time_increase = new_minutes - old_minutes
            if time_increase > 60:  # 增加超过 1 小时
                print(f"✅ 指标1通过: 剩余时间增加 {time_increase} 分钟")
                success_indicators += 1
                result["detail"] = f"剩余时间从 {old_minutes} 分钟增加至 {new_minutes} 分钟"
            elif time_increase < -60:  # 减少超过 1 小时（异常）
                print(f"❌ 指标1失败: 剩余时间减少 {abs(time_increase)} 分钟")
                fail_indicators += 1
            else:
                print(f"⚠️ 指标1不明确: 时间变化 {time_increase} 分钟")
        
        # 指标2: 成功提示
        if alert_text:
            lowered = alert_text.lower()
            if any(kw in lowered for kw in ("renewed", "success", "extended", "completed")):
                print(f"✅ 指标2通过: 检测到成功提示")
                success_indicators += 1
                if not result["detail"]:
                    result["detail"] = alert_text
            elif any(kw in lowered for kw in ("can't renew", "unable", "failed", "error")):
                print(f"❌ 指标2失败: 检测到失败提示")
                fail_indicators += 1
                result["detail"] = alert_text
        
        # 指标3: 从 Expired 恢复
        if old_minutes == 0 and new_minutes is not None and new_minutes > 0:
            print(f"✅ 指标3通过: 从过期状态恢复")
            success_indicators += 1
        
        # 最终判定
        if success_indicators >= 2:
            result["status"] = "success"
            print("✅ 续期成功（多重指标确认）")
        elif fail_indicators >= 1:
            result["status"] = "failed"
            print("❌ 续期失败（检测到失败指标）")
        elif success_indicators >= 1:
            result["status"] = "success"
            print("✅ 续期成功（单一指标确认）")
        else:
            result["status"] = "unknown"
            result["detail"] = f"无法确认（原: {old_minutes}min, 新: {new_minutes}min, 提示: {alert_text or '无'}）"
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
        f"⏭️ 跳过(已续期/未到期): {skipped}\n"
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
