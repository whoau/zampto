```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import requests
from seleniumbase import SB


# ============================================================
# 环境变量
# ============================================================

EMAIL = os.environ.get("ZAM_PTO_EMAIL", "").strip()
PASSWORD = os.environ.get("ZAM_PTO_PASSWORD", "").strip()

TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()

IS_PROXY = (
    os.environ.get("IS_PROXY", "true").strip().lower() == "true"
)

PROXY_SERVER = os.environ.get(
    "PROXY_SERVER",
    "http://127.0.0.1:1081"
).strip()

BASE_URL = "https://dash.zampto.net"


# ============================================================
# Telegram 通知
# ============================================================

def send_tg_message(
    status_icon: str,
    status_text: str,
    detail: str = ""
):
    """发送 Telegram 通知。未配置时自动跳过。"""

    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print(
            "ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，"
            "跳过 Telegram 推送。"
        )
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time = time.strftime(
        "%Y-%m-%d %H:%M:%S",
        local_time
    )

    # 邮箱脱敏
    if "@" in EMAIL:
        name, domain = EMAIL.split("@", 1)

        if len(name) > 4:
            masked_email = (
                f"{name[:2]}****{name[-2:]}@{domain}"
            )
        else:
            masked_email = f"{name}@{domain}"

    else:
        masked_email = (
            EMAIL[:2] + "****"
            if EMAIL
            else "未配置"
        )

    text = (
        "🇫🇷 ZamPTO 续期通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 续期账户: {masked_email}\n"
        f"⏱️ 操作时间: {current_time}"
    )

    if detail:
        text += f"\n📝 详情: {detail[:800]}"

    url = (
        f"https://api.telegram.org/"
        f"bot{TG_BOT_TOKEN}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            json={
                "chat_id": TG_CHAT_ID,
                "text": text
            },
            timeout=10,
        )

        if response.ok:
            print("📩 Telegram 通知发送成功！")
        else:
            print(
                "⚠️ Telegram 通知发送失败: "
                f"HTTP {response.status_code}"
            )

    except requests.RequestException as exc:
        print(
            f"⚠️ Telegram 通知发送异常: {exc}"
        )


# ============================================================
# JS 设置输入框
# ============================================================

def js_fill_input(
    sb,
    selector: str,
    text: str
) -> bool:
    """
    安全设置输入框值，并触发 input/change 事件。
    """

    try:
        return bool(
            sb.execute_script(
                """
                const selector = arguments[0];
                const value = arguments[1];

                const el = document.querySelector(selector);

                if (!el) {
                    return false;
                }

                const setter =
                    Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype,
                        "value"
                    ).set;

                setter.call(el, value);

                el.dispatchEvent(
                    new Event("input", {
                        bubbles: true
                    })
                );

                el.dispatchEvent(
                    new Event("change", {
                        bubbles: true
                    })
                );

                return true;
                """,
                selector,
                text,
            )
        )

    except Exception as exc:
        print(
            f"⚠️ 设置输入框失败 "
            f"{selector}: {exc}"
        )
        return False


# ============================================================
# Cloudflare / 人机验证检测
# ============================================================

def has_challenge(sb) -> bool:
    """
    仅检测验证组件，不尝试绕过。
    """

    try:
        return bool(
            sb.execute_script(
                """
                return Boolean(
                    document.querySelector(
                        'input[name="cf-turnstile-response"]'
                    ) ||
                    document.querySelector(
                        'iframe[src*="challenges.cloudflare.com"]'
                    ) ||
                    document.querySelector(
                        'altcha-widget'
                    ) ||
                    document.querySelector(
                        '[class*="altcha"]'
                    )
                );
                """
            )
        )

    except Exception:
        return False


def wait_for_challenge_to_clear(
    sb,
    timeout: int = 30
) -> bool:
    """
    等待网站自行完成或用户合法完成验证。
    不执行自动绕过。
    """

    if not has_challenge(sb):
        return True

    print(
        "⚠️ 页面出现人机验证，"
        "等待其正常完成……"
    )

    for _ in range(timeout):
        time.sleep(1)

        try:
            solved = sb.execute_script(
                """
                const cf =
                    document.querySelector(
                        'input[name="cf-turnstile-response"]'
                    );

                if (
                    cf &&
                    cf.value &&
                    cf.value.length > 20
                ) {
                    return true;
                }

                const altcha =
                    document.querySelector(
                        'input[name*="altcha" i], '
                        + 'input[name*="captcha" i]'
                    );

                if (
                    altcha &&
                    altcha.value &&
                    altcha.value.length > 20
                ) {
                    return true;
                }

                return !document.querySelector(
                    'iframe[src*="challenges.cloudflare.com"], '
                    + 'altcha-widget'
                );
                """
            )

            if solved:
                print("✅ 验证已正常完成")
                return True

        except Exception:
            pass

    print(
        "❌ 人机验证未在限定时间内完成"
    )

    return False


# ============================================================
# 读取页面 Alert
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
# 登录
# ============================================================

def login(sb) -> bool:

    print("\n" + "#" * 25)
    print("   开始 ZamPTO 登录")
    print("#" * 25)

    login_urls = [
        f"{BASE_URL}/auth/login",
        f"{BASE_URL}/login",
    ]

    loaded = False

    # --------------------------------------------------------
    # 打开登录页面
    # --------------------------------------------------------

    for login_url in login_urls:

        print(
            f"🌐 打开登录页面: {login_url}"
        )

        try:

            sb.uc_open_with_reconnect(
                login_url,
                reconnect_time=8
            )

            time.sleep(5)

            current_url = sb.get_current_url()

            print(
                f"📄 当前 URL: {current_url}"
            )

            if sb.is_element_present(
                'input[name="email"]'
            ):
                loaded = True

                print(
                    "✅ 登录表单加载成功"
                )

                break

        except Exception as exc:

            print(
                f"⚠️ 页面打开失败: {exc}"
            )

    # --------------------------------------------------------
    # 登录页面没有正常加载
    # --------------------------------------------------------

    if not loaded:

        print(
            "❌ 登录页面未加载成功"
        )

        print(
            f"当前 URL: "
            f"{sb.get_current_url()}"
        )

        print(
            f"当前标题: "
            f"{sb.get_title() or ''}"
        )

        # 再检查一次验证
        if has_challenge(sb):

            print(
                "⚠️ 检测到人机验证"
            )

            if not wait_for_challenge_to_clear(
                sb,
                timeout=30
            ):

                sb.save_screenshot(
                    "login_challenge.png"
                )

                return False

        try:
            sb.wait_for_element(
                'input[name="email"]',
                timeout=15
            )

            loaded = True

        except Exception:

            print(
                "❌ 页面未加载出登录表单"
            )

            sb.save_screenshot(
                "login_load_fail.png"
            )

            return False

    # --------------------------------------------------------
    # Cookie
    # --------------------------------------------------------

    try:

        for button in sb.find_elements("button"):

            text = (
                button.text or ""
            ).strip().lower()

            if text in {
                "accept",
                "accept all",
                "同意",
                "接受"
            }:

                print(
                    "🍪 点击 Cookie 同意按钮"
                )

                button.click()

                time.sleep(0.5)

                break

    except Exception:
        pass

    # --------------------------------------------------------
    # 填写邮箱
    # --------------------------------------------------------

    print("📧 填写邮箱……")

    if not EMAIL:

        print(
            "❌ ZAM_PTO_EMAIL 未配置"
        )

        return False

    if not js_fill_input(
        sb,
        'input[name="email"]',
        EMAIL
    ):

        print(
            "❌ 邮箱输入框不存在"
        )

        sb.save_screenshot(
            "email_input_fail.png"
        )

        return False

    # --------------------------------------------------------
    # 填写密码
    # --------------------------------------------------------

    print("🔑 填写密码……")

    if not PASSWORD:

        print(
            "❌ ZAM_PTO_PASSWORD 未配置"
        )

        return False

    if not js_fill_input(
        sb,
        'input[name="password"]',
        PASSWORD
    ):

        print(
            "❌ 密码输入框不存在"
        )

        sb.save_screenshot(
            "password_input_fail.png"
        )

        return False

    time.sleep(1)

    # --------------------------------------------------------
    # Cloudflare 验证
    # --------------------------------------------------------

    if has_challenge(sb):

        print(
            "🛡️ 检测到人机验证"
        )

        if not wait_for_challenge_to_clear(
            sb,
            timeout=30
        ):

            sb.save_screenshot(
                "login_challenge.png"
            )

            return False

    else:

        print(
            "ℹ️ 未检测到人机验证组件"
        )

    # --------------------------------------------------------
    # 点击 Login
    # --------------------------------------------------------

    print(
        "🖱️ 查找 Login 按钮……"
    )

    clicked = False

    try:

        buttons = sb.find_elements(
            "button"
        )

        for button in buttons:

            text = (
                button.text or ""
            ).strip().lower()

            print(
                f"   🔘 按钮: {text}"
            )

            if text == "login":

                sb.execute_script(
                    """
                    arguments[0]
                    .scrollIntoView({
                        block: 'center'
                    });
                    """,
                    button
                )

                time.sleep(0.5)

                button.click()

                clicked = True

                print(
                    "✅ 已点击 Login 按钮"
                )

                break

    except Exception as exc:

        print(
            f"⚠️ 点击 Login 按钮失败: {exc}"
        )

    # --------------------------------------------------------
    # 如果没找到 Login 按钮
    # --------------------------------------------------------

    if not clicked:

        print(
            "❌ 没找到 Login 按钮"
        )

        sb.save_screenshot(
            "login_button_fail.png"
        )

        return False

    # --------------------------------------------------------
    # 等待登录结果
    # --------------------------------------------------------

    print(
        "⏳ 等待登录结果……"
    )

    login_page_urls = {
        f"{BASE_URL}/auth/login",
        f"{BASE_URL}/auth/login/",
        f"{BASE_URL}/login",
        f"{BASE_URL}/login/",
    }

    for i in range(30):

        time.sleep(1)

        current_url = (
            sb.get_current_url()
        )

        page_title = (
            sb.get_title() or ""
        )

        normalized_url = (
            current_url
            .split("?", 1)[0]
            .rstrip("/")
            .lower()
        )

        print(
            f"   [{i + 1}/30] "
            f"URL: {current_url} | "
            f"Title: {page_title}"
        )

        # ----------------------------------------------------
        # 检查页面错误
        # ----------------------------------------------------

        alert_text = read_alert(sb)

        if alert_text:

            print(
                f"   📩 页面提示: "
                f"{alert_text}"
            )

            lowered = alert_text.lower()

            if any(
                word in lowered
                for word in (
                    "invalid",
                    "incorrect",
                    "wrong password",
                    "invalid credentials",
                    "authentication failed",
                    "login failed",
                )
            ):

                print(
                    "❌ 检测到登录失败提示"
                )

                sb.save_screenshot(
                    "login_failed.png"
                )

                return False

        # ----------------------------------------------------
        # 判断是否已经离开登录页
        #
        # 不再要求必须出现 dashboard
        # ----------------------------------------------------

        if normalized_url not in {
            url.rstrip("/").lower()
            for url in login_page_urls
        }:

            print(
                "✅ 登录成功！"
            )

            print(
                f"📄 登录后 URL: "
                f"{current_url}"
            )

            print(
                f"📄 登录后 Title: "
                f"{page_title}"
            )

            return True

    # --------------------------------------------------------
    # 超时
    # --------------------------------------------------------

    print(
        "❌ 登录失败，"
        "30 秒内没有离开登录页面。"
    )

    print(
        f"最终 URL: "
        f"{sb.get_current_url()}"
    )

    print(
        f"最终标题: "
        f"{sb.get_title() or ''}"
    )

    sb.save_screenshot(
        "login_failed.png"
    )

    return False


# ============================================================
# 查找服务器详情
# ============================================================

def goto_server_detail(sb) -> bool:

    print(
        "\n🖥️ 正在查找服务器详情入口……"
    )

    time.sleep(4)

    alert_text = read_alert(sb)

    if (
        alert_text
        and "can't renew"
        in alert_text.lower()
    ):

        print(
            f"ℹ️ 页面提示: "
            f"{alert_text}"
        )

        send_tg_message(
            "ℹ️",
            "未到续期时间",
            alert_text
        )

        return False

    selectors = [
        'a[href*="/server/"]',
        'a[href*="/servers/"]',
        'a[href*="server"]',
    ]

    for selector in selectors:

        try:

            elements = sb.find_elements(
                selector
            )

            for element in elements:

                text = (
                    element.text or ""
                ).strip().lower()

                if any(
                    word in text
                    for word in (
                        "view server",
                        "server",
                        "view",
                        "see"
                    )
                ):

                    print(
                        f"✅ 找到服务器入口: "
                        f"{text or selector}"
                    )

                    sb.execute_script(
                        """
                        arguments[0]
                        .scrollIntoView({
                            block: 'center'
                        });
                        """,
                        element
                    )

                    time.sleep(0.5)

                    element.click()

                    time.sleep(5)

                    print(
                        f"📄 当前页面: "
                        f"{sb.get_current_url()}"
                    )

                    return True

        except Exception:
            continue

    # --------------------------------------------------------
    # 备用：遍历所有 a / button
    # --------------------------------------------------------

    try:

        for element in sb.find_elements(
            "a, button"
        ):

            text = (
                element.text or ""
            ).strip().lower()

            if text in {
                "view server",
                "view",
                "see"
            }:

                print(
                    f"✅ 点击服务器入口: "
                    f"{text}"
                )

                element.click()

                time.sleep(5)

                return True

    except Exception:
        pass

    print(
        "❌ 未找到服务器详情入口"
    )

    sb.save_screenshot(
        "servers_page_fail.png"
    )

    return False


# ============================================================
# 打开续期窗口
# ============================================================

def open_renew_dialog(sb) -> bool:

    print(
        "\n🔄 查找续期按钮……"
    )

    try:

        for element in sb.find_elements(
            "button, a"
        ):

            text = (
                element.text or ""
            ).strip().lower()

            if text in {
                "renew server",
                "renew",
                "confirm renewal"
            }:

                sb.execute_script(
                    """
                    arguments[0]
                    .scrollIntoView({
                        block: 'center'
                    });
                    """,
                    element
                )

                time.sleep(0.5)

                element.click()

                time.sleep(3)

                print(
                    f"✅ 已点击续期按钮: "
                    f"{text}"
                )

                return True

    except Exception as exc:

        print(
            f"⚠️ 查找续期按钮时出错: "
            f"{exc}"
        )

    print(
        "❌ 未找到续期按钮"
    )

    sb.save_screenshot(
        "renew_button_fail.png"
    )

    return False


# ============================================================
# 提交续期
# ============================================================

def submit_renew(sb) -> bool:

    if has_challenge(sb):

        if not wait_for_challenge_to_clear(
            sb,
            timeout=30
        ):

            sb.save_screenshot(
                "renew_challenge.png"
            )

            print(
                "❌ 续期验证未完成，停止提交"
            )

            return False

    print(
        "🖱️ 点击确认续期按钮……"
    )

    selectors = [
        "div.modal.show button.btn-primary",
        "div.modal.show button[type='submit']",
        "button[type='submit']",
    ]

    for selector in selectors:

        try:

            buttons = sb.find_elements(
                selector
            )

            for button in buttons:

                text = (
                    button.text or ""
                ).strip().lower()

                if (
                    not text
                    or any(
                        word in text
                        for word in (
                            "renew",
                            "confirm",
                            "submit"
                        )
                    )
                ):

                    button.click()

                    time.sleep(4)

                    print(
                        "✅ 续期确认按钮已点击"
                    )

                    return True

        except Exception:
            continue

    print(
        "❌ 未找到确认续期按钮"
    )

    sb.save_screenshot(
        "renew_submit_fail.png"
    )

    return False


# ============================================================
# 检查续期结果
# ============================================================

def check_renew_result(sb):

    print(
        "\n📋 检查续期结果……"
    )

    time.sleep(2)

    alert_text = read_alert(sb)

    if not alert_text:

        print(
            "ℹ️ 未检测到明确的续期结果"
        )

        send_tg_message(
            "ℹ️",
            "续期操作已执行",
            "页面没有明确提示"
        )

        return

    print(
        f"📩 页面提示: "
        f"{alert_text}"
    )

    lowered = alert_text.lower()

    if any(
        word in lowered
        for word in (
            "can't renew",
            "unable",
            "already renewed"
        )
    ):

        send_tg_message(
            "⏳",
            "未到续期时间或已续期",
            alert_text
        )

    elif any(
        word in lowered
        for word in (
            "renewed",
            "success",
            "extended",
            "completed"
        )
    ):

        send_tg_message(
            "✅",
            "续期成功",
            alert_text
        )

    else:

        send_tg_message(
            "ℹ️",
            "续期操作已执行",
            alert_text
        )


# ============================================================
# 续期流程
# ============================================================

def renew_server(sb):

    print(
        "\n" + "#" * 25
    )

    print(
        "  开始 ZamPTO 自动续期流程"
    )

    print(
        "#" * 25
    )

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

    print(
        "#" * 25
    )

    print(
        "   ZamPTO 自动登录续期"
    )

    print(
        "#" * 25
    )

    # --------------------------------------------------------
    # 检查账号环境变量
    # --------------------------------------------------------

    if not EMAIL or not PASSWORD:

        print(
            "❌ 未配置 "
            "ZAM_PTO_EMAIL 或 "
            "ZAM_PTO_PASSWORD"
        )

        send_tg_message(
            "❌",
            "账号环境变量未配置"
        )

        raise SystemExit(1)

    # --------------------------------------------------------
    # SeleniumBase
    # --------------------------------------------------------

    sb_kwargs = {
        "uc": True,
        "headless": False,
    }

    # --------------------------------------------------------
    # 代理
    # --------------------------------------------------------

    if IS_PROXY:

        print(
            f"🔗 使用 sing-box 本地代理: "
            f"{PROXY_SERVER}"
        )

        sb_kwargs["proxy"] = PROXY_SERVER

    else:

        print(
            "🌐 未启用代理，使用直连"
        )

    # --------------------------------------------------------
    # 启动浏览器
    # --------------------------------------------------------

    try:

        with SB(**sb_kwargs) as sb:

            # ------------------------------------------------
            # 获取出口 IP
            # ------------------------------------------------

            try:

                sb.open(
                    "https://api.ip.sb/ip"
                )

                exit_ip = (
                    sb.get_text("body")
                    .strip()
                )

                print(
                    f"📍 当前出口 IP: "
                    f"{exit_ip}"
                )

            except Exception as exc:

                print(
                    f"⚠️ 无法获取出口 IP: "
                    f"{exc}"
                )

                if IS_PROXY:

                    send_tg_message(
                        "❌",
                        "代理连接失败",
                        str(exc)
                    )

                    raise SystemExit(1)

            # ------------------------------------------------
            # 登录
            # ------------------------------------------------

            if login(sb):

                print(
                    "\n🎉 登录流程成功"
                )

                # ------------------------------------------------
                # 续期
                # ------------------------------------------------

                renew_server(sb)

            else:

                print(
                    "\n❌ 登录失败，"
                    "终止续期操作。"
                )

                send_tg_message(
                    "❌",
                    "登录失败"
                )

                raise SystemExit(1)

    # --------------------------------------------------------
    # SystemExit
    # --------------------------------------------------------

    except SystemExit:
        raise

    # --------------------------------------------------------
    # 其他异常
    # --------------------------------------------------------

    except Exception as exc:

        print(
            f"❌ 程序运行异常: "
            f"{exc}"
        )

        send_tg_message(
            "❌",
            "程序运行异常",
            str(exc)
        )

        raise SystemExit(1)


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":
    main()
```
