# WeasyPrint Windows安装指南
# ===========================

## 问题描述
在Windows上使用WeasyPrint生成PDF时，缺少`libgobject-2.0-0`库，导致WeasyPrint无法正常工作。

## 解决方案（三选一）

### 方案一：使用MSYS2安装GTK依赖（推荐）

#### 步骤1：安装MSYS2
1. 下载MSYS2：https://www.msys2.org/
2. 运行安装程序，默认安装到`C:\msys64`

#### 步骤2：启动MSYS2终端
在开始菜单找到 "MSYS2 MinGW 64-bit"

#### 步骤3：安装GTK依赖
在MSYS2终端中运行以下命令：
```bash
# 更新包管理器
pacman -Syu

# 安装GTK3和Pango
pacman -S mingw-w64-x86_64-gtk3
pacman -S mingw-w64-x86_64-pango
pacman -S mingw-w64-x86_64-python-gobject

# 如果需要，安装其他依赖
pacman -S mingw-w64-x86_64-libffi
```

#### 步骤4：配置环境变量
将以下目录添加到系统的PATH环境变量：
- `C:\msys64\mingw64\bin`

#### 步骤5：重启终端并测试
重启命令行终端，然后运行：
```bash
python -c "from weasyprint import HTML; print('成功导入WeasyPrint')"
```

### 方案二：使用GTK运行时安装程序

#### 步骤1：下载GTK运行时
下载地址：https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases

#### 步骤2：安装运行时
运行下载的安装程序，选择"Complete"安装

#### 步骤3：配置环境变量
将GTK的bin目录添加到PATH：
- 通常安装到：`C:\Program Files\GTK3-Runtime Win64\bin`

#### 步骤4：测试
重启终端并测试WeasyPrint

### 方案三：使用Docker（高级用户）

如果不想在本地安装GTK，可以使用Docker容器：

```dockerfile
# Dockerfile
FROM python:3.11-slim

# 安装依赖
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "app/main.py"]
```

## 验证安装

运行验证脚本：
```bash
python verify_weasyprint.py
```

## 备选方案

如果无法安装GTK依赖，系统会自动回退到使用PyMuPDF生成基本PDF。

## 故障排除

### 常见问题

1. **错误：cannot load library 'libgobject-2.0-0'**
   - 解决方案：确保GTK运行时已安装并添加到PATH

2. **错误：找不到gi模块**
   - 解决方案：`pip install PyGObject`

3. **字体显示问题**
   - 确保系统中安装了中文字体
   - 在CSS中指定字体：`font-family: "Microsoft YaHei", "SimSun"`

### 测试命令

```python
# test_weasyprint.py
try:
    from weasyprint import HTML
    html = HTML(string='<h1>测试</h1><p>WeasyPrint工作正常</p>')
    html.write_pdf('test.pdf')
    print("✅ WeasyPrint工作正常")
except Exception as e:
    print(f"❌ WeasyPrint失败: {e}")
```

## 联系方式

如遇到问题，请参考：
- WeasyPrint文档：https://doc.courtbouillon.org/weasyprint
- MSYS2文档：https://www.msys2.org/docs/

---
*最后更新：2026-04-28*