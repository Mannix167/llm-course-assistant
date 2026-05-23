# install_gtk_deps.ps1
# WeasyPrint GTK依赖安装脚本（Windows MSYS2方案）

Write-Host "=== WeasyPrint GTK依赖安装程序 ===" -ForegroundColor Cyan
Write-Host ""

# 检查当前目录
$currentDir = Get-Location
Write-Host "当前目录: $currentDir" -ForegroundColor Green

# 1. 检查MSYS2是否已安装
$msys2Paths = @(
    "C:\msys64",
    "C:\msys",
    "D:\msys64",
    "$env:USERPROFILE\msys64",
    "$env:LOCALAPPDATA\Programs\MSYS2"
)

$msys2Found = $false
$msys2Path = ""

foreach ($path in $msys2Paths) {
    if (Test-Path $path) {
        $msys2Path = $path
        $msys2Found = $true
        Write-Host "找到MSYS2安装: $path" -ForegroundColor Green
        break
    }
}

if (-not $msys2Found) {
    Write-Host "未找到MSYS2安装。" -ForegroundColor Yellow
    Write-Host "请从以下地址下载并安装MSYS2：" -ForegroundColor Yellow
    Write-Host "https://www.msys2.org/" -ForegroundColor Blue
    Write-Host ""
    Write-Host "安装步骤：" -ForegroundColor Cyan
    Write-Host "1. 下载msys2-x86_64-xxxx.exe" -ForegroundColor White
    Write-Host "2. 运行安装程序，默认安装到C:\msys64" -ForegroundColor White
    Write-Host "3. 安装完成后重启终端" -ForegroundColor White
    Write-Host ""
    $installChoice = Read-Host "是否继续安装GTK依赖？(y/n)"
    if ($installChoice -ne "y") {
        Write-Host "安装已取消。" -ForegroundColor Red
        exit 1
    }

    # 如果用户继续，尝试常见路径
    if (Test-Path "C:\msys64") {
        $msys2Path = "C:\msys64"
    } else {
        Write-Host "请先安装MSYS2，然后重新运行此脚本。" -ForegroundColor Red
        exit 1
    }
}

# 2. 检查WeasyPrint是否已安装
Write-Host ""
Write-Host "=== 检查Python环境 ===" -ForegroundColor Cyan
$pythonVersion = python --version 2>$null
if ($?) {
    Write-Host "Python版本: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "Python未找到，请确保Python已安装并添加到PATH。" -ForegroundColor Red
    exit 1
}

# 检查WeasyPrint
$weasyprintCheck = python -c "try: import weasyprint; print('WeasyPrint已安装') except ImportError as e: print(f'WeasyPrint未安装: {e}')"
Write-Host "WeasyPrint状态: $weasyprintCheck" -ForegroundColor Green

# 3. 检查GTK依赖
Write-Host ""
Write-Host "=== 检查GTK/Pango依赖 ===" -ForegroundColor Cyan
$gtkCheck = python -c "
try:
    import gi
    gi.require_version('Pango', '1.0')
    from gi.repository import Pango
    print('GTK/Pango依赖正常')
except ImportError as e:
    print(f'缺少gi模块: {e}')
except ValueError as e:
    print(f'Pango版本问题: {e}')
except Exception as e:
    print(f'其他GTK错误: {e}')
"
Write-Host "GTK依赖状态: $gtkCheck" -ForegroundColor Green

if ($gtkCheck -like "*正常*") {
    Write-Host "GTK依赖已正常安装！" -ForegroundColor Green
    Write-Host "现在可以生成美观的PDF了。" -ForegroundColor Green
    exit 0
}

# 4. 提供安装指导
Write-Host ""
Write-Host "=== GTK依赖安装指导 ===" -ForegroundColor Cyan
Write-Host "需要安装GTK运行时库才能使用WeasyPrint。" -ForegroundColor Yellow
Write-Host ""
Write-Host "安装方法：" -ForegroundColor White
Write-Host ""
Write-Host "方法1：使用MSYS2安装（推荐）" -ForegroundColor Green
Write-Host "1. 打开MSYS2终端" -ForegroundColor White
Write-Host "2. 运行以下命令：" -ForegroundColor White
Write-Host "   pacman -Syu" -ForegroundColor Cyan
Write-Host "   pacman -S mingw-w64-x86_64-gtk3 mingw-w64-x86_64-pango mingw-w64-x86_64-python-gobject" -ForegroundColor Cyan
Write-Host ""
Write-Host "方法2：使用预编译的GTK运行时" -ForegroundColor Green
Write-Host "1. 下载GTK运行时：" -ForegroundColor White
Write-Host "   https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer" -ForegroundColor Blue
Write-Host "2. 运行安装程序" -ForegroundColor White
Write-Host "3. 将GTK的bin目录添加到PATH环境变量" -ForegroundColor White
Write-Host ""
Write-Host "方法3：使用Chocolatey包管理器" -ForegroundColor Green
Write-Host "1. 安装Chocolatey：" -ForegroundColor White
Write-Host "   Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))" -ForegroundColor Cyan
Write-Host "2. 安装GTK运行时：" -ForegroundColor White
Write-Host "   choco install gtk-runtime" -ForegroundColor Cyan

# 5. 创建测试脚本
Write-Host ""
Write-Host "=== 创建依赖测试脚本 ===" -ForegroundColor Cyan
$testScript = @'
#!/usr/bin/env python3
"""WeasyPrint依赖测试脚本"""

import sys
import os
from pathlib import Path

def check_weasyprint_deps():
    """检查WeasyPrint依赖"""
    print("=== WeasyPrint依赖检查 ===")

    # 检查Python模块
    try:
        import weasyprint
        print("✓ WeasyPrint模块已安装")
    except ImportError as e:
        print(f"✗ WeasyPrint模块未安装: {e}")
        return False

    # 检查GTK/Pango依赖
    try:
        import gi
        gi.require_version('Pango', '1.0')
        from gi.repository import Pango
        print("✓ GTK/Pango依赖正常")
    except ImportError as e:
        print(f"✗ 缺少gi模块 (PyGObject): {e}")
        print("  请安装: pip install PyGObject")
        return False
    except ValueError as e:
        print(f"✗ Pango版本问题: {e}")
        print("  请确保GTK运行时正确安装")
        return False
    except Exception as e:
        print(f"✗ 其他GTK错误: {e}")
        return False

    print("")
    print("=== 测试PDF生成 ===")
    try:
        from weasyprint import HTML, CSS
        html = HTML(string="<h1>测试PDF</h1><p>如果能看到这个PDF，说明WeasyPrint正常工作。</p>")
        css = CSS(string="@page { size: A4; margin: 1cm; } body { font-family: Arial; }")
        test_pdf = Path("test_weasyprint.pdf")
        html.write_pdf(test_pdf, stylesheets=[css])
        print(f"✓ PDF生成成功: {test_pdf}")
        if test_pdf.exists():
            print(f"  文件大小: {test_pdf.stat().st_size} 字节")
            test_pdf.unlink()  # 删除测试文件
        return True
    except Exception as e:
        print(f"✗ PDF生成失败: {e}")
        return False

if __name__ == "__main__":
    success = check_weasyprint_deps()
    sys.exit(0 if success else 1)
'@

Set-Content -Path "D:\course learn agent\test_weasyprint.py" -Value $testScript
Write-Host "已创建测试脚本: test_weasyprint.py" -ForegroundColor Green
Write-Host "运行: python test_weasyprint.py" -ForegroundColor Cyan

Write-Host ""
Write-Host "=== 安装完成后 ===" -ForegroundColor Cyan
Write-Host "1. 重启终端或重新加载环境变量" -ForegroundColor White
Write-Host "2. 运行测试脚本验证安装" -ForegroundColor White
Write-Host "3. 重新启动课件学习助手" -ForegroundColor White

Write-Host ""
Write-Host "提示：如果使用MSYS2安装，请确保将MSYS2的mingw64\bin目录添加到PATH" -ForegroundColor Yellow
Write-Host "     例如: C:\msys64\mingw64\bin" -ForegroundColor White