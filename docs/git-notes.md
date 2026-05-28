# Git常用指令

---

## 一、常用的 Git 指令

1. 查看状态

**git status**

查看哪些文件：
- 被修改
- 已暂存
- 未跟踪
- 即将提交

---

2. 添加文件到暂存区

**git add .**   把当前目录所有变化加入暂存区
包括：
- 新文件
- 修改
- 删除

**git add app/main.py**     添加单个文件"main.py"

---

3. 提交git

**git commit -m "feat: add pgvector schema"**   创建一次版本记录,"feat: add pgvector schema"为该版内容简介

---

4. 推送到 GitHub

**git push**    上传到远程仓库

---

5. 查看提交记录

**git log**

显示内容：
- commit id
- 作者
- 时间
- 提交信息

---

6. 撤销暂存（撤销 **git add** ）

**git restore --staged 文件名**     取消 git add,但不删除文件

---

7. 撤销文件修改（危险）

**git restore 文件名**  恢复到上一次 commit 状态

---

8. 查看分支

**git branch**

---

9. 创建分支

**git branch feature/login**

---

10. 切换分支

**git checkout feature/login**
或
**git switch feature/login**

---

11. 创建并切换

**git switch -c feature/login**

---

12. 拉取 GitHub 最新代码

**git pull**    同步远程仓库最新内容

---

13. 查看修改内容

**git diff**    查看你改了什么

**git diff --cached**   查看已暂存内容

---

14. Git 删除文件

**git rm 文件名**

---

15. 初始化 Git

**git init**    把普通文件夹变成 Git 仓库

---

## 十、连接 GitHub

---

16. 添加远程仓库

**git remote add origin 仓库地址**

---

## 二、AI工程开发最重要的两个文件

### **.gitignore**
作用：告诉 Git 哪些文件不要提交
一般内容：
- venv/
- .env
- __pycache__/
- *.pyc

### **.gitattributes**
作用：统一换行符

Git 的换行符（LF/CRLF）警告，不会影响 git add 或项目运行。当使用的系统和项目开发倾向转行符有矛盾时，会出现警告，如：`warning: in the working copy of '.env.example', LF will be replaced by CRLF the next time Git touches it`

- LF = \n = Linux/macOS 换行
- CRLF = \r\n = Windows 换行

通常通过：
1. 配置 Git
`git config --global core.autocrlf input`

作用：
- 提交时自动转 LF
- Windows 本地不强制改 CRLF
- 最适合 Python/Docker 开发

2. 统一使用 LF
IDE右下角切换，将CRLF切换至LF后保存文件。

3. 项目根目录创建`.gitattributes`
`
* text=auto eol=lf
*.bat text eol=crlf
`

作用：
- 默认所有文件统一 LF
- 只有 Windows bat 文件使用 CRLF

这在：Docker\Python\FastAPI\Linux 部署里非常重要

---

**控制 Git：“检出文件”和“提交文件”时是否自动转换换行**

- `git config --global core.autocrlf true`  
    - Git 下载文件 → 自动变 CRLF（Windows）
    - Git 提交文件 → 自动转回 LF
    适合 纯 Windows 开发\Office 文档项目

- `git config --global core.autocrlf input` 符。
    - Git 下载文件 → 不改
    - Git 提交文件 → 强制转 LF
    Linux/Docker/Python 开发最推荐配置

- `git config --global core.autocrlf false`
    - Git 完全不管换行符
    团队开发容易混乱
    