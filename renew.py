#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import re
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
# Cloudflare Turnstile 绕过（保留无参 JS）
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

# ============================================================
# 登录（使用原生方法）
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
# 获取服务器 ID 列表（从列表页提取）
# ============================================================

def get_server_ids(sb) -> list:
    print("🔍 正在提取服务器 ID 列表...")
    time.sleep(5)

    server_ids = []

    # 方法1：正则从页面源码提取
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

    # 方法2：遍历元素查找 "ID:"
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

    # 方法3：从当前 URL 提取
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
# 续期单个服务器（基于您提供的 HTML 结构精准定位）
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

        # 等待页面关键文字出现，确保内容加载完成
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

        time.sleep(2)

        current_url = sb.get_current_url()
        if "server" not in current_url.lower():
            result["status"] = "failed"
            result["detail"] = "未进入详情页"
            print(f"❌ 未进入详情页，当前 URL: {current_url}")
            return result

        print(f"📄 当前页面: {current_url}")

        # ---------- 基于 HTML 结构精准定位 "Renew Server" 按钮 ----------
        renew_btn = None

        # 首选 XPath：找到包含 "Server last renewed" 的卡片，再找按钮
        try:
            renew_btn = sb.find_element(
                "//div[contains(@data-slot,'card')][.//*[contains(text(),'Server last renewed')]]"
                "//button[normalize-space()='Renew Server']",
                timeout=5
            )
            print("✅ 通过卡片 + 文本定位到按钮")
        except Exception:
            pass

        # 备选1：通过标题 "Renew" 所在的卡片找按钮
        if renew_btn is None:
            try:
                renew_btn = sb.find_element(
                    "//div[contains(@data-slot,'card')][.//*[contains(text(),'Renew') and @data-slot='card-title']]"
                    "//button[normalize-space()='Renew Server']",
                    timeout=5
                )
                print("✅ 通过 'Renew' 标题卡片定位到按钮")
            except Exception:
                pass

        # 备选2：直接找按钮文本（兼容性）
        if renew_btn is None:
            try:
                renew_btn = sb.find_element("//button[normalize-space()='Renew Server']", timeout=3)
                print("✅ 直接通过按钮文本定位")
            except Exception:
                pass

        # 备选3：遍历所有 button/a
        if renew_btn is None:
            print("⚠️ 未通过 XPath 定位，尝试遍历所有 button/a...")
            try:
                elements = sb.find_elements("button, a")
                for elem in elements:
                    if (elem.text or "").strip().lower() == "renew server":
                        renew_btn = elem
                        print("✅ 通过遍历找到按钮")
                        break
            except Exception as e:
                print(f"⚠️ 遍历失败: {e}")

        if renew_btn is None:
            print("❌ 所有定位策略均失败")
            # 保存截图并打印调试信息
            try:
                all_btns = sb.find_elements("button")
                print("页面上所有 button 的文本（前20个）:")
                for i, b in enumerate(all_btns[:20]):
                    print(f"  {i}: '{b.text}'")
            except:
                pass
            sb.save_screenshot(f"renew_button_not_found_{server_id}.png")
            result["status"] = "failed"
            result["detail"] = "未找到 Renew Server 按钮"
            return result

        # ---------- 点击按钮 ----------
        try:
            sb.scroll_to(renew_btn)
            time.sleep(0.5)
            try:
                renew_btn.click()
            except:
                sb.execute_script("arguments[0].click();", renew_btn)
            print("✅ 已点击 Renew Server 按钮")
            time.sleep(5)
        except Exception as e:
            result["status"] = "error"
            result["detail"] = f"点击按钮失败: {e}"
            print(f"❌ {result['detail']}")
            return result

        # ---------- 检查续期结果 ----------
        # 检查是否有成功提示（可能是 div.alert-success 或类似）
        try:
            success_elem = sb.find_element("div.alert-success, div.alert-info", timeout=5)
            if success_elem:
                msg = success_elem.text.strip()
                result["status"] = "success"
                result["detail"] = msg
                print(f"✅ 续期成功: {msg}")
                return result
        except Exception:
            pass

        # 检查普通 alert
        alert_text = read_alert(sb)
        if alert_text:
            print(f"📩 页面提示: {alert_text}")
            result["detail"] = alert_text
            lowered = alert_text.lower()
            if any(kw in lowered for kw in ("renewed", "success", "extended", "completed")):
                result["status"] = "success"
            elif any(kw in lowered for kw in ("can't renew", "unable", "already renewed")):
                result["status"] = "skipped"
            else:
                result["status"] = "unknown"
        else:
            print("ℹ️ 未检测到明确提示，假定续期成功")
            result["status"] = "success"
            result["detail"] = "无提示，假定成功"

        return result

    except Exception as e:
        print(f"⚠️ 处理服务器 ID={server_id} 时发生异常: {e}")
        result["status"] = "error"
        result["detail"] = str(e)
        return result

# ============================================================
# 主续期流程：遍历所有服务器 ID
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

    # 汇总通知
    total = len(results)
    success = sum(1 for r in results if r['status'] == 'success')
    skipped = sum(1 for r in results if r['status'] == 'skipped')
    failed = sum(1 for r in results if r['status'] in ('failed', 'error'))

    summary = (
        f"续期完成：共 {total} 个服务器\n"
        f"✅ 成功: {success}\n"
        f"⏭️ 跳过(已续期/未到期): {skipped}\n"
        f"❌ 失败: {failed}"
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
