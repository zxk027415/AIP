# 双机同步手动命令清单（无需脚本）

仓库：`https://github.com/zxk027415/AIP.git`  
分支：`main`

---

## 1) Windows 离开前（推送到远端）

```powershell
cd "C:\Users\xiaokang.zhao\project\AIP-3-2026.4.22\AIP-2-2026.4.20"
git checkout main
git pull --rebase origin main
git add .
git commit -m "sync: windows YYYY-MM-DD HH:mm"
git push origin main
git status
```

> 如果没有改动，`git commit` 会提示 nothing to commit，直接继续 `git push` 即可。

---

## 2) Mac 接手后（从远端拉取）

```bash
cd ~/project/AIP
git checkout main
git pull --rebase origin main
git status
```

---

## 3) Mac 离开前（推送到远端）

```bash
cd ~/project/AIP
git checkout main
git pull --rebase origin main
git add .
git commit -m "sync: mac $(date '+%Y-%m-%d %H:%M')"
git push origin main
git status
```

---

## 4) ---Windows 接手后（从远端拉取）

```powershell
cd "C:\Users\xiaokang.zhao\project\AIP-3-2026.4.22\AIP-2-2026.4.20"
git checkout main
git pull --rebase origin main
git status
```

## 5) 临时不想提交时（先切机）

### Windows
```powershell
git stash -u
git pull --rebase origin main
git stash pop
```

### Mac
```bash
git stash -u
git pull --rebase origin main
git stash pop
```

---

## 6) 写到一半但要换电脑（推荐：WIP 提交并推送）

> 适用：另一台电脑也要继续这段“半成品”代码。

### Windows
```powershell
cd "C:\Users\xiaokang.zhao\project\AIP-3-2026.4.22\AIP-2-2026.4.20"
git checkout main
git pull --rebase origin main
git add .
git commit -m "wip: switch device YYYY-MM-DD HH:mm"
git push origin main
git status
```

### Mac
```bash
cd ~/project/AIP
git checkout main
git pull --rebase origin main
git add .
git commit -m "wip: switch device $(date '+%Y-%m-%d %H:%M')"
git push origin main
git status
```

---

## 7) Cursor 上下文同步（你当前可用）

你目前菜单可见 `Export Transcript`，切机前建议导出一份。  
切到另一台后，把导出的内容和 `docs_zxk` 文档一起作为上下文继续。

建议固定开场语：

```text
继续 AIP 仓库 main 分支任务，请先读取 docs_zxk 下最新文档和 transcript 摘要。
```

---

## 8) WIP 回来后整理成正式提交（推荐）

> 适用：你之前为了切机推了 `wip:` 提交，现在要整理成干净的正式提交。

### Windows / Mac 通用

```bash
git checkout main
git pull --rebase origin main
git log --oneline -n 8
```

先看最近提交，定位你的 `wip:` 提交是否还在最新几条里。  
如果你只是继续开发，不需要改历史，直接再补一个正式提交即可：

```bash
git add .
git commit -m "feat: <正式功能说明>"
git push origin main
```

如果你非常确定要把最近那条 `wip` 改成正式信息（仅限该提交尚未被他人基于其开发）：

```bash
git commit --amend -m "feat: <正式功能说明>"
git push --force-with-lease origin main
```

> 注意：`--force-with-lease` 会改远端历史，只有你确认安全时再用。  
> 日常建议：保留 `wip`，再追加一条正式提交，最稳。

