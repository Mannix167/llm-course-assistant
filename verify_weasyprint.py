#!/usr/bin/env python3
"""
WeasyPrint验证脚本
检查是否已正确安装并可以生成PDF
"""

import sys
import os
from pathlib import Path
import tempfile

def check_weasyprint():
    """检查WeasyPrint状态"""
    print("=" * 50)
    print("WeasyPrint验证脚本")
    print("=" * 50)

    results = []

    # 检查Python版本
    try:
        version = sys.version_info
        results.append(("Python版本", True, f"{version.major}.{version.minor}.{version.micro}"))
    except Exception as e:
        results.append(("Python版本", False, str(e)))

    # 检查WeasyPrint导入
    try:
        from weasyprint import HTML, CSS
        results.append(("WeasyPrint模块", True, "导入成功"))
    except ImportError as e:
        results.append(("WeasyPrint模块", False, f"导入失败: {e}"))
        return results, False

    # 检查GTK/Pango依赖
    try:
        import gi
        gi.require_version('Pango', '1.0')
        from gi.repository import Pango
        results.append(("GTK/Pango依赖", True, "正常"))
    except Exception as e:
        results.append(("GTK/Pango依赖", False, f"失败: {e}"))

    # 尝试生成PDF
    try:
        # 创建测试PDF
        html = HTML(string="""<!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                @page { size: A4; margin: 2cm; }
                body { font-family: Arial, sans-serif; font-size: 12pt; line-height: 1.6; }
                h1 { color: #333; text-align: center; }
                .success { color: green; font-weight: bold; }
            </style>
        </head>
        <body>
            <h1>WeasyPrint测试</h1>
            <p>这是一个测试PDF，用于验证WeasyPrint是否正常工作。</p>
            <p class="success">✓ 如果能看到此PDF，说明安装成功！</p>
            <p>生成时间：2026-04-28</p>
        </body>
        </html>""")

        test_file = Path(tempfile.gettempdir()) / "weasyprint_test.pdf"
        html.write_pdf(test_file)

        if test_file.exists():
            file_size = test_file.stat().st_size
            results.append(("PDF生成", True, f"成功 ({file_size}字节)"))
            print(f"\n测试PDF已保存到: {test_file}")

            # 询问是否打开PDF
            if sys.platform == "win32":
                choice = input("\n是否打开测试PDF文件？(y/n): ")
                if choice.lower() == 'y':
                    os.startfile(test_file)
        else:
            results.append(("PDF生成", False, "文件未创建"))
    except Exception as e:
        results.append(("PDF生成", False, f"失败: {e}"))

    return results, all(status for _, status, _ in results)

def check_project_pdf_function():
    """检查项目中的PDF生成功能"""
    print("\n" + "=" * 50)
    print("检查项目PDF功能")
    print("=" * 50)

    project_root = Path(__file__).parent

    # 检查后端PDF相关文件
    pdf_files = [
        project_root / "backend" / "app" / "routers" / "reports.py",
        project_root / "backend" / "app" / "utils" / "markdown_utils.py",
    ]

    for pdf_file in pdf_files:
        if pdf_file.exists():
            print(f"✓ {pdf_file.relative_to(project_root)} 存在")
        else:
            print(f"✗ {pdf_file.relative_to(project_root)} 不存在")

    # 检查requirements.txt
    req_file = project_root / "backend" / "requirements.txt"
    if req_file.exists():
        content = req_file.read_text()
        if "weasyprint" in content.lower():
            print("✓ WeasyPrint在requirements.txt中")
        else:
            print("✗ WeasyPrint不在requirements.txt中")

def main():
    """主函数"""
    # 检查WeasyPrint
    results, all_ok = check_weasyprint()

    # 打印结果
    print("\n" + "=" * 50)
    print("验证结果")
    print("=" * 50)

    for name, status, message in results:
        symbol = "✓" if status else "✗"
        color_code = 32 if status else 31  # 绿色/红色
        print(f"\033[{color_code}m{symbol}\033[0m {name}: {message}")

    print("\n" + "=" * 50)

    if all_ok:
        print("\033[32m✅ 恭喜！WeasyPrint已正确安装并可以生成PDF。\033[0m")
        print("现在您可以在前端界面下载美观的PDF报告了！")
    else:
        print("\033[31m❌ 存在问题，WeasyPrint无法正常工作。\033[0m")
        print("\n请参考以下解决方案：")
        print("1. 查看安装指南: docs/weasyprint_windows_guide.md")
        print("2. 运行安装脚本: install_gtk_deps.ps1")
        print("3. 使用MSYS2安装GTK依赖（推荐）")

    # 检查项目功能
    check_project_pdf_function()

    print("\n" + "=" * 50)
    print("下一步：")
    if all_ok:
        print("1. 重新启动课件学习助手")
        print("2. 在前端上传PDF并生成报告")
        print("3. 点击'下载PDF'测试功能")
    else:
        print("1. 按照指南安装GTK依赖")
        print("2. 重启终端并重新运行此验证脚本")
        print("3. 成功后重启课件学习助手")

    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())