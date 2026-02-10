import subprocess
import sys
import os

def check_playwright_installation():
    """检查 Playwright 安装状态"""
    try:
        import playwright
        return True, "Playwright Python 包已安装"
    except ImportError:
        return False, "Playwright Python 包未安装\n请运行: pip install playwright"


def check_playwright_browsers():
    """检查 Playwright 浏览器是否已安装"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(result.stdout.lower())

        if "chromium" in result.stdout.lower():
            return True, "Playwright 浏览器已安装"
        else:
            return False, "Playwright 浏览器未安装\n请运行: playwright install chromium"
    except Exception as e:
        return False, f"检查浏览器时出错: {e}"


def ensure_playwright_ready():
    """确保 Playwright 准备就绪"""
    print("[info] 检查 Playwright 安装状态...")

    # 检查 Python 包
    pkg_ok, pkg_msg = check_playwright_installation()
    if not pkg_ok:
        print(f"[error] {pkg_msg}")
        return False

    print(f"[info] ✓ {pkg_msg}")

    # 检查浏览器
    browser_ok, browser_msg = check_playwright_browsers()
    if not browser_ok:
        print(f"[warning] ⚠️  {browser_msg}")
        # 不阻止运行，让用户决定是否继续
        choice = input("[input] 浏览器未安装，是否安装? (y/n): ").lower().strip()
        if choice != 'y':
            return False
        else:
            os.system("ls")
            return True
    else:
        return True