import os
import sqlite3
import shutil
import platform
import subprocess
import sys
import time
from datetime import datetime

# --- 配置 ---
BROWSERS = {
    "chrome": {
        "name": "谷歌 Chrome", 
        "exe_windows": "chrome.exe",
        "path_windows": os.path.join("Google", "Chrome", "User Data", "Default", "History"),
    },
    "edge": {
        "name": "微软 Edge", 
        "exe_windows": "msedge.exe",
        "path_windows": os.path.join("Microsoft", "Edge", "User Data", "Default", "History"),
    }
}

# --- 辅助函数 ---

def get_history_path(browser_key):
    """获取指定浏览器的 History 文件路径。"""
    if platform.system() == "Windows":
        base_path = os.getenv('LOCALAPPDATA')
        if not base_path:
            print("错误：无法确定 LOCALAPPDATA 环境变量。") 
            return None
        browser_path_segment = BROWSERS[browser_key].get("path_windows")
        if browser_path_segment:
            return os.path.join(base_path, browser_path_segment)
        else:
            print(f"错误：未为 {browser_key} 定义 Windows 路径") 
            return None
    # 可在此处为 macOS 或 Linux 添加 elif
    else:
        print(f"错误：不支持的操作系统: {platform.system()}") 
        return None

def close_browser(browser_key):
    """尝试强制关闭指定的浏览器 (仅限 Windows)。"""
    if platform.system() == "Windows":
        browser_exe = BROWSERS[browser_key].get("exe_windows")
        if not browser_exe:
            print(f"警告：未为 {browser_key} 定义 Windows 可执行文件名。") 
            return False
        print(f"正在尝试关闭 {BROWSERS[browser_key]['name']} ({browser_exe})...") 
        try:
            result = subprocess.run(['taskkill', '/F', '/IM', browser_exe, '/T'],
                                    capture_output=True, text=True, check=False, encoding='gbk', errors='ignore') # 尝试 gbk 编码读取 taskkill 输出
            if result.returncode == 0:
                print(f"{BROWSERS[browser_key]['name']} 进程已成功终止。") 
                return True
            elif result.returncode == 128:
                print(f"{BROWSERS[browser_key]['name']} 进程未找到 (可能已关闭?)。") 
                return True
            else:
                print(f"警告：无法终止 {browser_exe}。返回码: {result.returncode}") 
                # 尝试解码中文输出，如果失败则显示原始信息
                stdout_decoded = result.stdout.strip()
                stderr_decoded = result.stderr.strip()
                print(f"         输出: {stdout_decoded}") 
                print(f"         错误: {stderr_decoded}") 
                print("         请在继续前手动确保浏览器已关闭。") 
                return False
        except FileNotFoundError:
            print("错误：未找到 'taskkill' 命令。无法自动关闭浏览器。") 
            return False
        except Exception as e:
            print(f"错误：尝试关闭浏览器时出错: {e}") 
            return False
    else:
        print("警告：自动关闭浏览器功能仅在 Windows 上实现。") 
        print("         请手动确保浏览器已关闭。") 
        return False

def backup_history_file(history_path):
    """创建历史记录文件的时间戳备份。"""
    if not os.path.exists(history_path):
        print(f"警告：在 {history_path} 未找到历史记录文件。无法创建备份。") 
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{history_path}_backup_{timestamp}"
    try:
        shutil.copy2(history_path, backup_path)
        print(f"成功：历史记录文件已备份至: {backup_path}") 
        return backup_path
    except Exception as e:
        print(f"错误：创建历史记录文件备份失败: {e}") 
        return None

def delete_domain_history(db_path, domain_to_delete):
    """连接到 SQLite 数据库并删除指定域名的历史记录。"""
    if not os.path.exists(db_path):
        print(f"错误：在 {db_path} 未找到数据库文件") 
        return False, 0, 0

    conn = None
    deleted_visits = 0
    deleted_urls = 0
    success = False
    domain_pattern = f'%{domain_to_delete}%'

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print(f"已连接到数据库: {db_path}") 

        # 1. 首先从 'visits' 表删除
        sql_delete_visits = "DELETE FROM visits WHERE url IN (SELECT id FROM urls WHERE url LIKE ?)"
        # print(f"正在执行: {sql_delete_visits.replace('?', repr(domain_pattern))}") # 保留英文或删除此调试行
        cursor.execute(sql_delete_visits, (domain_pattern,))
        deleted_visits = cursor.rowcount
        print(f"已从 'visits' 表中删除 {deleted_visits} 条记录。") 

        # 2. 然后从 'urls' 表删除 (仅当不再被引用时)
        sql_delete_urls = "DELETE FROM urls WHERE url LIKE ? AND id NOT IN (SELECT url FROM visits)"
        # print(f"正在执行: {sql_delete_urls.replace('?', repr(domain_pattern))}") # 保留英文或删除此调试行
        cursor.execute(sql_delete_urls, (domain_pattern,))
        deleted_urls = cursor.rowcount
        print(f"已从 'urls' 表中删除 {deleted_urls} 条记录。") 

        conn.commit()
        print("成功：更改已提交到数据库。") 
        success = True

    except sqlite3.OperationalError as e:
        print(f"错误：数据库操作失败: {e}") 
        print("       这通常意味着浏览器仍在运行并锁定了文件。") 
    except sqlite3.DatabaseError as e:
        print(f"错误：数据库错误: {e}") 
    except Exception as e:
        print(f"错误：数据库操作期间发生意外错误: {e}") 
    finally:
        if conn:
            conn.close()
            print("数据库连接已关闭。") 

    return success, deleted_visits, deleted_urls

# --- 主执行逻辑 ---
def main():
    print("--- 特定域名浏览器历史记录删除器 ---") 
    print("警告：此脚本将修改您的浏览器历史记录数据库。") 
    print("         强烈建议确保浏览器已完全关闭。") 
    print("         脚本将尝试备份 History 文件。") 
    print("-" * 55)

    # 1. 选择浏览器
    print("选择浏览器:") 
    browser_options = list(BROWSERS.keys())
    for i, key in enumerate(browser_options):
        print(f"{i+1}. {BROWSERS[key]['name']}") # name 已经是中文

    choice = ""
    selected_browser_key = None
    while not selected_browser_key:
        try:
            choice = input(f"请输入选项 (1-{len(browser_options)}): ") 
            index = int(choice) - 1
            if 0 <= index < len(browser_options):
                selected_browser_key = browser_options[index]
            else:
                print("无效选项。") 
        except ValueError:
            print("输入无效，请输入数字。") 

    print(f"已选择: {BROWSERS[selected_browser_key]['name']}") 

    # 2. 获取域名
    domain = ""
    while not domain:
        domain = input("请输入要删除历史记录的域名 (例如 example.com): ").strip() 
        if not domain:
            print("域名不能为空。") 

    print(f"目标域名: {domain}") 
    print("-" * 55)

    # 3. 获取历史记录路径
    history_path = get_history_path(selected_browser_key)
    if not history_path:
        sys.exit(1)

    if not os.path.exists(history_path):
        print(f"错误：在预期位置未找到历史记录文件:") 
        print(f"       {history_path}")
        print( "       也许浏览器尚未使用，或者配置文件名称不同？") 
        sys.exit(1)

    print(f"找到历史记录文件: {history_path}") 

    # 4. 确认操作
    confirm = input(f"确定要从 {BROWSERS[selected_browser_key]['name']} 中删除 '{domain}' 的历史记录吗? (y/N): ").lower() 
    if confirm != 'y':
        print("操作已取消。") 
        sys.exit(0)

    # 5. 尝试关闭浏览器
    close_browser(selected_browser_key)
    print("暂停几秒钟以允许文件句柄释放...") 
    time.sleep(3)

    # 6. 备份历史文件
    print("-" * 55)
    backup_file = backup_history_file(history_path)
    if not backup_file:
        confirm_no_backup = input("警告：创建备份失败。仍然继续吗? (y/N): ").lower() 
        if confirm_no_backup != 'y':
            print("因备份失败，操作已取消。") 
            sys.exit(1)
        else:
            print("在没有备份的情况下继续...") 

    # 7. 删除历史记录
    print("-" * 55)
    print(f"正在尝试删除域名 '{domain}' 的条目...") 
    success, visits_count, urls_count = delete_domain_history(history_path, domain)

    print("-" * 55)
    if success:
        print("操作完成。") 
        print(f"   已删除 {visits_count} 条访问记录。") 
        print(f"   已删除 {urls_count} 条 URL 记录 (如果不再被引用)。") 
        if backup_file:
             print(f"   备份创建于: {backup_file}") 
    else:
        print("操作失败或遇到错误。") 
        print("   请检查上面的错误消息。") 
        print("   请确保浏览器已完全关闭。") 
        if backup_file:
            print(f"   您可能需要恢复备份: {backup_file}") 

    print("-" * 55)


if __name__ == "__main__":
    main()
    input("按 Enter 键退出...") 