<!-- @AI_GENERATED -->
# Git 基础使用教程

> 面向日常开发场景，结合本项目（AIP）的实际操作整理。

---

## 核心概念：三个区域

Git 管理代码有三个"层级"，理解了这个，后面的命令就全通了：

```
工作区（你的文件夹）  →  暂存区（准备提交的）  →  本地仓库（已保存的历史）  →  远程仓库（服务器）
    你改文件               git add               git commit               git push
```

| 区域 | 比喻 | 对应操作 |
|------|------|---------|
| 工作区 | 你桌上的草稿纸 | 直接编辑文件 |
| 暂存区 (staging) | 你挑出来准备交的作业 | `git add` |
| 本地仓库 | 你自己柜子里存的档案 | `git commit` |
| 远程仓库 | 公司的档案室 | `git push` |

---

## commit 和 push 的区别

**`git commit`** = 把改动保存到**本地**的历史记录里

- 只影响你自己的电脑
- 可以断网操作
- 相当于"存档"

**`git push`** = 把本地的 commit 上传到**远程服务器**

- 别人才能看到你的改动
- 需要网络
- 相当于"把存档上传到云端"

```
commit 是"我确认了这个改动"
push   是"我把确认的改动分享给团队"
```

你可以 commit 很多次再一次性 push，也可以每次 commit 后立即 push。

---

## 日常工作流（最常用的 5 个命令）

### 1. 查看状态：我改了什么？

```bash
git status
```

输出会告诉你：
- 红色文件 = 改了但没 add
- 绿色文件 = 已 add，等待 commit
- 什么都没有 = 干干净净

简洁版：

```bash
git status --short
```

- `M` = modified（改了）
- `A` = added（新增）
- `D` = deleted（删了）
- `??` = untracked（新文件，git 还不管它）

### 2. 暂存改动：我要提交这些文件

```bash
# 暂存单个文件
git add backend-service/main.py

# 暂存整个目录
git add backend-service/

# 暂存所有改动（慎用，可能带上不想要的文件）
git add .
```

**小技巧**：不确定时先 `git status` 看看有哪些文件，再有选择地 add。

### 3. 提交：保存到本地历史

```bash
git commit -m "描述你做了什么"
```

commit message 写法建议：

```bash
# 好的写法（动词开头，说清楚做了什么）
git commit -m "fix: 修复前端端口绑定问题"
git commit -m "feat: 添加 Linux 启动脚本"
git commit -m "docs: 添加端口排查教程"

# 差的写法
git commit -m "改了一些东西"
git commit -m "update"
git commit -m "111"
```

### 4. 推送：上传到远程

```bash
# 推到远程的 aip-zxk 分支（本项目的用法）
git push origin main:aip-zxk
```

解释：`git push origin 本地分支:远程分支`

如果本地和远程分支同名，可以简写：

```bash
git push origin main
```

### 5. 拉取：下载远程的最新代码

```bash
git pull origin aip-zxk
```

---

## 分支（Branch）

分支就是一条独立的开发线。本项目里：

```
master     ← 远程默认主分支（别人的，不要动）
aip-zxk    ← 你的开发分支
dev-v260313 ← 另一个开发分支
```

### 常用分支操作

```bash
# 查看所有分支（本地 + 远程）
git branch -a

# 创建新分支
git branch feature-xxx

# 切换分支
git checkout feature-xxx

# 创建并切换（一步到位）
git checkout -b feature-xxx

# 删除本地分支
git branch -d feature-xxx
```

### 什么时候用新分支？

- 要做一个比较大的新功能，怕搞坏现有代码 → 开新分支
- 多人协作，每个人各自分支，最后合并
- 想实验性地改东西，改完不满意可以直接删分支

---

## Tag（标签）：锁定版本快照

Tag 是给某个 commit 贴标签，用来标记版本号。和分支不同，tag 不会变。

```bash
# 给当前版本打标签
git tag v1.0

# 带说明的标签
git tag -a v1.0 -m "第一个稳定版本"

# 推标签到远程
git push origin v1.0

# 推所有标签
git push origin --tags

# 查看所有标签
git tag -l

# 回到某个标签版本查看
git checkout v1.0

# 回到最新
git checkout main
```

**场景**：你跑了一次成功的 50 轮实验，打个 tag `v1.0-50round-passed`，以后不管怎么改代码，这个版本永远在那里。

---

## 查看历史

```bash
# 查看提交历史（简洁版）
git log --oneline

# 查看最近 5 条
git log --oneline -5

# 查看某个文件的历史
git log --oneline backend-service/main.py

# 图形化查看分支合并历史
git log --oneline --graph --all
```

---

## 撤销操作（后悔药）

### 改了文件但还没 add，想恢复原样

```bash
# 恢复单个文件
git checkout -- backend-service/main.py

# 恢复所有（危险！会丢失所有未暂存的改动）
git checkout -- .
```

### 已经 add 了，想从暂存区撤回（文件改动保留）

```bash
git reset HEAD backend-service/main.py
```

### 已经 commit 了，想撤回（改动保留，commit 取消）

```bash
# 撤回最近一次 commit，改动回到工作区
git reset --soft HEAD~1
```

### 已经 push 了，想撤回

这比较麻烦，最安全的方式是做一个新 commit 来"反向修改"：

```bash
# 创建一个反向 commit
git revert HEAD
git push origin main:aip-zxk
```

---

## .gitignore：告诉 Git 忽略哪些文件

项目根目录的 `.gitignore` 文件里写不需要跟踪的文件：

```gitignore
# Python
__pycache__/
*.pyc
.env

# Node.js
node_modules/
dist/

# IDE
.vscode/
.idea/

# 系统文件
.DS_Store
Thumbs.db

# 日志和临时文件
logs/
*.log
.pids/
```

已经被 git 跟踪的文件加到 .gitignore 不会自动取消跟踪。需要：

```bash
git rm --cached 文件名
```

---

## 本项目的具体操作速查

### 日常改代码后提交

```bash
# 1. 看改了什么
git status --short

# 2. 暂存
git add .

# 3. 提交
git commit -m "feat: 你做了什么"

# 4. 推送到 aip-zxk
git push origin main:aip-zxk
```

### 服务器上拉取最新代码

```bash
cd /data1/jxn/AIP
git pull origin aip-zxk
```

### 打标签锁定稳定版本

```bash
git tag -a v1.0 -m "描述这个版本"
git push origin v1.0
```

### 查看远程某个版本

在 GitLab 页面上切换分支/标签即可查看任何历史版本的代码。

---

## 常见问题

### Q: push 被拒绝了（rejected）

原因：远程有你本地没有的 commit。

```bash
# 先拉取远程改动合并
git pull origin aip-zxk --rebase
# 再推送
git push origin main:aip-zxk
```

如果你确定要用本地覆盖远程（丢弃远程的改动）：

```bash
git push origin main:aip-zxk --force
```

⚠️ `--force` 会覆盖远程历史，只有在你确定远程那些 commit 不需要时才用。

### Q: 切换分支时提示"本地有未提交改动"

```bash
# 方法 1：先提交
git add . && git commit -m "wip: 临时保存"

# 方法 2：暂存到 stash（不 commit，临时放起来）
git stash
git checkout 其他分支
# 回来时取出
git checkout main
git stash pop
```

### Q: commit 了错误的文件怎么办？

```bash
# 撤回最近一次 commit（改动保留）
git reset --soft HEAD~1
# 重新选择要提交的文件
git add 正确的文件
git commit -m "正确的描述"
```

### Q: 怎么看两个版本之间的差异？

```bash
# 工作区和上次 commit 的差异
git diff

# 两个 commit 之间的差异
git diff commit1 commit2

# 和远程的差异
git diff main origin/aip-zxk
```

---

## 一图总结

```
你改文件
    │
    ▼
git add          选择要提交的文件
    │
    ▼
git commit       保存到本地历史（可以离线）
    │
    ▼
git push         上传到远程服务器（需要网络）
    │
    ▼
远程仓库          别人可以看到 / 服务器可以拉取
```

```
想回退？

还没 add     → git checkout -- 文件
已 add 没 commit → git reset HEAD 文件
已 commit 没 push → git reset --soft HEAD~1
已 push     → git revert HEAD + git push
```
<!-- @AI_GENERATED: end -->
