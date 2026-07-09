<!-- @AI_GENERATED -->
# Linux 服务器端口访问排查教程

> 基于一次真实调试经历整理。场景：本地 Windows 电脑访问远程 Ubuntu 服务器上的 Web 服务（前端 3001 / 后端 8080），浏览器报 `ERR_CONNECTION_TIMED_OUT`。

---

## 排查思路（从近到远）

遇到"访问不到远程端口"时，按以下顺序从服务端 → 网络层逐层排查：

```
服务是否在跑？ → 监听地址对不对？ → 服务器防火墙放行了吗？ → 中间网络设备拦了吗？
```

---

## 第一步：确认服务是否在运行

```bash
# 查看某个端口是否有进程在监听
ss -tlnp | grep 3001
ss -tlnp | grep 8080
```

正常输出（说明服务在跑）：

```
LISTEN  0  511  0.0.0.0:3001  0.0.0.0:*  users:(("node",pid=977941,fd=29))
LISTEN  0  2048 0.0.0.0:8080  0.0.0.0:*  users:(("uvicorn",pid=977863,fd=8))
```

**关键看 `0.0.0.0:端口`**：
- `0.0.0.0:3001` → 监听所有网卡，外部可访问 ✅
- `127.0.0.1:3001` → 只监听本地回环，外部访问不到 ❌

### 如果是 127.0.0.1 怎么办？

这是最常见的"服务跑了但访问不到"的原因。

| 框架 | 解决方法 |
|------|---------|
| Vite (前端) | 启动时加 `--host 0.0.0.0`，如 `npm run dev -- --host 0.0.0.0 --port 3001` |
| uvicorn (FastAPI) | 启动时加 `--host 0.0.0.0`，如 `uvicorn main:app --host 0.0.0.0 --port 8080` |
| Node.js (Express) | `app.listen(3001, '0.0.0.0')` |
| Django | `python manage.py runserver 0.0.0.0:8000` |

---

## 第二步：检查服务器防火墙

Ubuntu 上常见两套防火墙：`ufw`（简单）和 `iptables`（底层）。

### 2.1 检查 ufw

```bash
sudo ufw status
```

| 输出 | 含义 |
|------|------|
| `Status: inactive` | ufw 没开，不是它的问题 |
| `Status: active` | ufw 在工作，需要放行端口 |

放行端口：

```bash
sudo ufw allow 3001
sudo ufw allow 8080
```

### 2.2 检查 iptables（重点！）

即使 ufw 是 inactive，iptables 可能仍有规则在拦。

```bash
sudo iptables -L INPUT -n --line-numbers
```

典型输出：

```
Chain INPUT (policy ACCEPT)
num  target     prot opt source       destination
1    ACCEPT     all  --  0.0.0.0/0    0.0.0.0/0    ctstate RELATED,ESTABLISHED,DNAT
2    ACCEPT     all  --  0.0.0.0/0    0.0.0.0/0
3    INPUT_direct  all  --  0.0.0.0/0 0.0.0.0/0
4    INPUT_ZONES   all  --  0.0.0.0/0 0.0.0.0/0
5    DROP       all  --  0.0.0.0/0    0.0.0.0/0    ctstate INVALID
6    REJECT     all  --  0.0.0.0/0    0.0.0.0/0    reject-with icmp-host-prohibited  ← 拦截所有未放行流量
```

**关键规则解读：**

- `ACCEPT ... ctstate RELATED,ESTABLISHED,DNAT`：已建立的连接放行（SSH 能连就是靠这条）
- `REJECT all ... icmp-host-prohibited`：**兜底拒绝规则**，所有没被前面明确放行的流量都被拒绝

### 2.3 在 REJECT 之前插入放行规则

规则是按序号从上往下匹配的，必须插在 REJECT 那条**之前**：

```bash
# 假设 REJECT 在第 6 条，我们插在第 5 的位置
sudo iptables -I INPUT 5 -p tcp --dport 3001 -j ACCEPT
sudo iptables -I INPUT 5 -p tcp --dport 8080 -j ACCEPT
```

验证：

```bash
sudo iptables -L INPUT -n --line-numbers | head -10
```

应该看到：

```
5    ACCEPT     tcp  --  0.0.0.0/0    0.0.0.0/0    tcp dpt:8080
6    ACCEPT     tcp  --  0.0.0.0/0    0.0.0.0/0    tcp dpt:3001
7    DROP       all  --  0.0.0.0/0    0.0.0.0/0    ctstate INVALID
8    REJECT     all  --  0.0.0.0/0    0.0.0.0/0    reject-with icmp-host-prohibited
```

### 2.4 持久化 iptables 规则

iptables 规则重启后会丢失！持久化方法：

```bash
sudo apt install iptables-persistent -y
sudo netfilter-persistent save
```

之后重启也会自动加载。

---

## 第三步：从本地验证连通性

在你的 Windows 电脑上打开 PowerShell：

```powershell
# 测试端口是否可达
Test-NetConnection 10.230.66.34 -Port 22    # SSH，应该通
Test-NetConnection 10.230.66.34 -Port 3001  # 前端
Test-NetConnection 10.230.66.34 -Port 8080  # 后端
```

输出关键字段：
- `TcpTestSucceeded: True` → 端口通了 ✅
- `TcpTestSucceeded: False` → 还是不通 ❌

---

## 第四步：如果服务器防火墙开了还是不通

说明是**你和服务器之间的网络设备**在拦（交换机 ACL、安全组、VPN 策略等）。

这时候有两个选择：

### 方案 A：找网管开端口

让网络管理员在网关/交换机上放行 3001、8080 到你的 IP。

### 方案 B：SSH 隧道绕过（不需要开端口）

在本地 PowerShell 执行：

```powershell
ssh -N -L 3001:localhost:3001 -L 8080:localhost:8080 ends@10.230.66.34
```

- `-N`：不打开远程 shell，只做转发
- `-L 3001:localhost:3001`：把本地 3001 转发到远程 localhost:3001

保持窗口开着，然后浏览器访问 `http://localhost:3001`。

**原理**：流量走 SSH 隧道（端口 22 已经是通的），不需要额外开放任何端口。

---

## 常见坑总结

| 症状 | 原因 | 解决 |
|------|------|------|
| 服务在跑，`ss` 看到监听 `127.0.0.1` | 没绑定 `0.0.0.0` | 启动命令加 `--host 0.0.0.0` |
| 服务监听 `0.0.0.0`，本地还是超时 | iptables 有 REJECT 兜底 | 在 REJECT 之前插入 ACCEPT 规则 |
| iptables 开了还是不通 | 中间网络设备拦截 | SSH 隧道 或 找网管 |
| 重启服务器后又不通了 | iptables 规则没持久化 | `sudo netfilter-persistent save` |
| ufw 显示 inactive 以为没防火墙 | iptables 独立于 ufw 存在 | 必须额外检查 iptables |
| 之前能访问现在不行 | 有人重置了 iptables 规则 | 重新添加 ACCEPT 规则 |

---

## 速查命令清单

```bash
# 看端口监听
ss -tlnp | grep <端口号>

# 看 iptables 规则
sudo iptables -L INPUT -n --line-numbers

# 放行端口（插在 REJECT 之前，编号看实际情况调整）
sudo iptables -I INPUT 5 -p tcp --dport <端口号> -j ACCEPT

# 删除某条规则（按编号）
sudo iptables -D INPUT <编号>

# 持久化
sudo netfilter-persistent save

# ufw 状态
sudo ufw status

# 本地测试连通性（Windows PowerShell）
Test-NetConnection <IP> -Port <端口号>

# SSH 隧道（本地 PowerShell）
ssh -N -L <本地端口>:localhost:<远程端口> user@server
```

---

## 一图流排查路径

```
浏览器访问不到
    │
    ▼
ss -tlnp 看端口 ──── 没监听 → 服务没启动或启动失败，看日志
    │
    │ 有监听
    ▼
监听地址是 0.0.0.0？ ── 是 127.0.0.1 → 加 --host 0.0.0.0
    │
    │ 是 0.0.0.0
    ▼
iptables -L INPUT ──── 有 REJECT 兜底 → 插入 ACCEPT 规则
    │
    │ 没有拦截
    ▼
本地 Test-NetConnection ── 不通 → 中间网络拦了 → SSH 隧道或找网管
    │
    │ 通了
    ▼
✅ 浏览器应该能打开了
```
<!-- @AI_GENERATED: end -->
