#!/usr/bin/env python3
"""
WeasyPrint依赖修复和增强工具
用于解决Windows上WeasyPrint的GTK/Pango依赖问题
"""

import sys
import subprocess
import os
from pathlib import Path
import json

class WeasyPrintFixer:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.requirements_file = self.project_root / "backend" / "requirements.txt"

    def check_dependencies(self):
        """检查所有相关依赖"""
        print("=== WeasyPrint依赖检查 ===")

        results = {
            "python_version": self.check_python_version(),
            "weasyprint": self.check_package("weasyprint"),
            "markdown": self.check_package("markdown"),
            "pygobject": self.check_package("PyGObject"),
            "gtk_deps": self.check_gtk_dependencies(),
            "weasyprint_functional": self.test_weasyprint()
        }

        print("\n=== 检查结果汇总 ===")
        all_ok = True
        for name, (status, message) in results.items():
            status_symbol = "✓" if status else "✗"
            color = "green" if status else "red"
            print(f"{status_symbol} {name}: {message}")
            if not status:
                all_ok = False

        return results, all_ok

    def check_python_version(self):
        """检查Python版本"""
        try:
            version = sys.version_info
            if version.major == 3 and version.minor >= 9:
                return True, f"Python {version.major}.{version.minor}.{version.micro} (符合要求)"
            else:
                return False, f"Python {version.major}.{version.minor}.{version.micro} (建议3.9+)"
        except Exception as e:
            return False, f"Python版本检查失败: {e}"

    def check_package(self, package_name):
        """检查Python包是否安装"""
        try:
            __import__(package_name.replace("-", "_"))
            return True, "已安装"
        except ImportError:
            return False, "未安装"

    def check_gtk_dependencies(self):
        """检查GTK/Pango依赖"""
        try:
            import gi
            gi.require_version('Pango', '1.0')
            from gi.repository import Pango
            return True, "GTK/Pango依赖正常"
        except ImportError as e:
            return False, f"缺少gi模块 (PyGObject): {e}"
        except ValueError as e:
            return False, f"Pango版本问题: {e}"
        except Exception as e:
            return False, f"其他GTK错误: {e}"

    def test_weasyprint(self):
        """测试WeasyPrint功能"""
        try:
            from weasyprint import HTML, CSS
            html = HTML(string="<h1>测试</h1><p>测试PDF生成</p>")
            css = CSS(string="@page { size: A4; margin: 1cm; } body { font-family: Arial; }")
            test_pdf = Path("temp_test.pdf")
            html.write_pdf(test_pdf, stylesheets=[css])
            if test_pdf.exists():
                size = test_pdf.stat().st_size
                test_pdf.unlink()
                return True, f"PDF生成成功 ({size}字节)"
            return False, "PDF文件未创建"
        except Exception as e:
            return False, f"PDF生成失败: {e}"

    def install_missing_packages(self):
        """安装缺失的Python包"""
        print("\n=== 安装缺失的Python包 ===")

        packages_to_install = []

        # 检查并收集需要安装的包
        for package in ["weasyprint", "markdown", "PyGObject"]:
            try:
                __import__(package.replace("-", "_"))
                print(f"✓ {package} 已安装")
            except ImportError:
                packages_to_install.append(package)
                print(f"✗ {package} 需要安装")

        if not packages_to_install:
            print("所有Python包已安装")
            return True

        # 安装缺失的包
        try:
            cmd = [sys.executable, "-m", "pip", "install"] + packages_to_install
            print(f"执行: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print("安装成功")
            return True
        except subprocess.CalledProcessError as e:
            print(f"安装失败: {e}")
            print(f"错误输出: {e.stderr}")
            return False

    def create_msys2_install_guide(self):
        """创建MSYS2安装指导"""
        guide = """
=== MSYS2安装GTK依赖指南 ===

1. 安装MSYS2 (如果未安装)
   下载地址: https://www.msys2.org/
   安装到: C:\\msys64 (推荐)

2. 启动MSYS2终端 (mingw64)
   在开始菜单找到 "MSYS2 MinGW 64-bit"

3. 更新包管理器
   pacman -Syu

4. 安装GTK依赖
   pacman -S mingw-w64-x86_64-gtk3
   pacman -S mingw-w64-x86_64-pango
   pacman -S mingw-w64-x86_64-python-gobject

5. 将GTK添加到PATH环境变量
   将以下目录添加到PATH:
   C:\\msys64\\mingw64\\bin

6. 重启终端或重新加载环境变量

注意: 如果您使用不同的Python安装，可能需要:
   pip install PyGObject
        """

        guide_file = self.project_root / "msys2_gtk_install_guide.txt"
        guide_file.write_text(guide, encoding="utf-8")
        print(f"安装指南已保存到: {guide_file}")
        print(guide)

    def create_alternative_solution(self):
        """创建备选解决方案（使用reportlab）"""
        alt_py = self.project_root / "backend" / "app" / "utils" / "pdf_alternative.py"

        content = '''
"""
PDF生成备选方案（当WeasyPrint不可用时）
使用reportlab生成基本PDF
"""
from pathlib import Path
from io import BytesIO
from typing import Optional
import re

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


class PDFAlternativeGenerator:
    """PDF生成备选方案（reportlab）"""

    def __init__(self):
        self.page_width, self.page_height = A4
        self.margin = 20 * mm
        self.line_height = 5 * mm
        self.font_size = 11

    def generate_pdf(self, markdown_content: str, output_path: Path,
                     title: str = "Course Report") -> bool:
        """生成PDF文件"""
        if not HAS_REPORTLAB:
            return False

        try:
            # 清理Markdown
            plain_text = self._markdown_to_plain(markdown_content)

            # 创建PDF
            c = canvas.Canvas(str(output_path), pagesize=A4)

            # 尝试加载中文字体
            chinese_font = self._find_chinese_font()
            if chinese_font:
                pdfmetrics.registerFont(TTFont('ChineseFont', chinese_font))
                c.setFont('ChineseFont', self.font_size)
            else:
                c.setFont('Helvetica', self.font_size)

            # 设置初始位置
            x = self.margin
            y = self.page_height - self.margin

            # 添加标题
            c.setFont('Helvetica-Bold', 16)
            c.drawString(x, y, title)
            y -= self.line_height * 2

            # 设置正文字体
            if chinese_font:
                c.setFont('ChineseFont', self.font_size)
            else:
                c.setFont('Helvetica', self.font_size)

            # 添加内容
            for line in plain_text.split('\n'):
                if y < self.margin:
                    c.showPage()
                    y = self.page_height - self.margin
                    if chinese_font:
                        c.setFont('ChineseFont', self.font_size)
                    else:
                        c.setFont('Helvetica', self.font_size)

                if line.strip():
                    # 简单换行处理
                    words = line.split()
                    current_line = []
                    current_width = 0
                    max_width = self.page_width - 2 * self.margin

                    for word in words:
                        word_width = c.stringWidth(word + ' ')
                        if current_width + word_width > max_width:
                            c.drawString(x, y, ' '.join(current_line))
                            y -= self.line_height
                            current_line = [word]
                            current_width = word_width
                        else:
                            current_line.append(word)
                            current_width += word_width

                    if current_line:
                        c.drawString(x, y, ' '.join(current_line))
                        y -= self.line_height
                else:
                    y -= self.line_height  # 空行

            c.save()
            return True

        except Exception as e:
            print(f"备选PDF生成失败: {e}")
            return False

    def _markdown_to_plain(self, markdown: str) -> str:
        """将Markdown转换为纯文本"""
        # 移除图片
        text = re.sub(r'!\[.*?\]\(.*?\)', '', markdown)
        # 移除链接
        text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
        # 移除标题标记
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
        # 移除粗体和代码标记
        text = text.replace('**', '').replace('`', '')
        # 移除列表标记
        text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)

        return text.strip()

    def _find_chinese_font(self) -> Optional[Path]:
        """查找中文字体"""
        font_paths = [
            'C:/Windows/Fonts/simhei.ttf',  # 黑体
            'C:/Windows/Fonts/simsun.ttc',  # 宋体
            'C:/Windows/Fonts/msyh.ttc',    # 微软雅黑
        ]

        for path in font_paths:
            if Path(path).exists():
                return Path(path)

        return None


# 导出函数
def generate_pdf_alternative(markdown_content: str, output_path: Path, title: str = "Course Report") -> bool:
    """使用备选方案生成PDF"""
    generator = PDFAlternativeGenerator()
    return generator.generate_pdf(markdown_content, output_path, title)
'''

        alt_py.parent.mkdir(parents=True, exist_ok=True)
        alt_py.write_text(content, encoding="utf-8")
        print(f"备选方案已创建: {alt_py}")

    def update_requirements(self):
        """更新requirements.txt确保包含必要包"""
        try:
            current_content = self.requirements_file.read_text()

            # 确保需要的包都在
            required_packages = [
                "weasyprint>=68.0",
                "markdown>=3.7",
                "PyGObject>=3.48",  # GTK绑定
                "reportlab>=4.2",   # 备选方案
            ]

            for package in required_packages:
                pkg_name = package.split('>')[0].split('<')[0].split('=')[0].strip()
                if pkg_name not in current_content.lower():
                    current_content += f"\n{package}"

            self.requirements_file.write_text(current_content)
            print(f"已更新: {self.requirements_file}")
            return True
        except Exception as e:
            print(f"更新requirements.txt失败: {e}")
            return False

    def run(self):
        """运行修复工具"""
        print("WeasyPrint依赖修复工具")
        print("=" * 50)

        # 检查当前状态
        results, all_ok = self.check_dependencies()

        if all_ok:
            print("\n✅ 所有依赖检查通过！WeasyPrint应该可以正常工作。")
            return

        print("\n⚠️  发现依赖问题，正在尝试修复...")

        # 1. 安装缺失的Python包
        self.install_missing_packages()

        # 2. 更新requirements.txt
        self.update_requirements()

        # 3. 创建MSYS2安装指南
        self.create_msys2_install_guide()

        # 4. 创建备选方案
        self.create_alternative_solution()

        # 5. 重新检查
        print("\n=== 修复完成后重新检查 ===")
        results, all_ok = self.check_dependencies()

        if all_ok:
            print("\n✅ 修复成功！现在可以生成美观的PDF了。")
        else:
            print("\n⚠️  仍有问题，请按照MSYS2安装指南操作。")
            print("   备选方案已准备就绪，即使GTK不可用也能生成基本PDF。")

        print("\n=== 下一步 ===")
        print("1. 如果使用MSYS2，请按照指南安装GTK依赖")
        print("2. 重启终端或重新加载环境变量")
        print("3. 运行测试: python -c \"from weasyprint import HTML; print('OK')\"")
        print("4. 重新启动课件学习助手")


if __name__ == "__main__":
    fixer = WeasyPrintFixer()
    fixer.run()