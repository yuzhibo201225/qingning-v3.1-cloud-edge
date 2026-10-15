# 青柠食光 · 树莓派屏幕收银台 + 手机打印桌码扫码点餐（V3 独立完整版：菜单图片管理与手机自动更新）

> 适合：树莓派 3B+（外接显示器，可 SSH）+ 1 部手机 + 你已有的阿里云北京轻量应用服务器 Ubuntu 22.04（CLOUD_PUBLIC_IP）。
>
> **本项目是独立版本**，不修改任何旧项目文件夹、数据库和容器；原树莓派 80/8080、原云端 5000 不受干扰。新版树莓派 `18080`，阿里云 `15001`。如果这两个端口已经被占用，请不要硬启动，先排查或调整端口和配置。

## 0. 最终成功效果（先理解，再执行）

```text
打印一张真正可以用相机识别的1号桌二维码
                   ↓
手机相机扫码：http://树莓派真实局域网IP:18080/?table=1
                   ↓
看到12张初始食物照片（商家可新增） + 菜品价格 → 加购物车 → 确认下单
                   ↓ 只走店内 Wi-Fi/局域网
树莓派本地 SQLite 数据库写入，立刻返回下单成功
                   ↓
树莓派 HDMI 外接屏幕的收银台 /cashier 每3秒刷新新订单
                   ↓
商家可查看桌号、明细、金额、来源、修改状态、手动下单
                   ↓
后台同步服务每5秒尝试推送阿里云
                   ↓
阿里云 SQLite 存储 + 网页统计
```

**断网范围**是“失去通向阿里云的互联网连接”，不是让店内无线局域网消失。手机、树莓派还必须处在互相可访问的网络内。断开外网后，手机仍然能扫二维码、查看图片、下单、收银台接单；恢复后再同步。

**非真实支付系统**。页面中的金额是订单应付金额/订单金额，尚不代表实际收到的营业收入；客流时段统计实际上是订单时段统计。


## V3 新增：商家菜单管理和顾客价格实时同步

1. 树莓派外接屏幕收银台 `/cashier`，菜单管理页面 `/manage`：上传 JPG/PNG/WebP 菜品图片（浏览器自动压缩为 WebP）、新增菜品、编辑菜名/分类/说明/标签、改价、更换图片、上下架。图片和菜单先存入树莓派 `edge/data`，无需外网。
2. 顾客手机菜单会**每 3 秒轻量检查 `/api/menu-revision`**；只有版本变化才重新获取 `/api/menu`，原页面不会整页重载，购物车、桌号和备注保留。新菜品自动展示；已下架菜品自动隐藏并从购物车移除；改价后购物车立即按新价格计算，同时展示提示。页面后台挂起时受手机浏览器定时器节流影响，返回前台时会立刻重新检查。
3. 收银台手动下单也会同步更新菜单版本。后台接口 `/api/orders` 再次验证每项菜单单价；如果恰逢改价或下架，返回 HTTP 409，不会暗中按不同价格成交，前端获取最新菜单提示顾客核对后再提交。
4. 已保存订单会写入订单明细的菜名、单价和总价**历史快照**，以后调价不修改旧订单。
5. 后台同步每 5 秒将菜单数据及 WebP 图片按版本复制至阿里云。云端 `/` 管理看板增加**只读菜单镜像**，可以在另一个设备查看在售情况，云端不反向编辑本地菜品。

**测试流程：** 手机点餐页不关闭，在树莓派收银台点击「菜单」→ 直接将任意菜品从 ¥24.90 改为 ¥25.90 并保存。观察手机菜单价签、购物车总价无需手动刷新地变动；接着上传一个菜品图片新增菜品、下架一个原有菜品，查看手机更新。建议不要把刷新间隔理解为严格 3 秒的送达承诺（无线网络/浏览器后台节流会造成延迟）。

## 1. 先检查你的设备，不要破坏旧版本

### 1.1 Windows 电脑上 SSH 登录树莓派

打开 Windows PowerShell：

```powershell
ssh 你的树莓派用户名@EDGE_LOCAL_IP
```

`pi` 不一定是用户名；先用你之前成功登录的账户。`EDGE_LOCAL_IP` 是先前使用的示例地址，**一定要实际验证**。

在树莓派终端执行：

```bash
whoami
hostname -I
cat /etc/os-release | head -5
uname -m
free -h
df -h /
docker --version
docker compose version
sudo docker ps --format 'table {{.Names}}\t{{.Ports}}'
ss -lnt | grep -E ':18080\b|:15001\b' || true
pgrep -a labwc || true
pgrep -a lxsession || true
command -v chromium || command -v chromium-browser || true
```

重点记录：①真实 IP；②Docker Compose 是否存在；③系统有无图形桌面/Chromium。如果树莓派安装的是 **Raspberry Pi OS Lite 纯命令行版**，仅插屏幕无法自动显示收银台，需要安装/启用图形桌面；建议先确认系统，避免盲目安装大量 GUI 软件。

### 1.2 阿里云同样先检查旧应用和端口

在阿里云控制台点击右上角“远程连接”，进 Ubuntu 终端：

```bash
whoami
cat /etc/os-release | head -5
uname -m
free -h
df -h /
docker --version
docker compose version
sudo docker ps --format 'table {{.Names}}\t{{.Ports}}'
ss -lnt | grep -E ':5000\b|:15001\b' || true
```

不要执行 `docker stop $(docker ps -q)`、`docker system prune -a`、`sudo rm -rf /var/lib/docker`，不要重装 Ubuntu。若 cloud Docker 尚未安装，看文末附录 A；如果旧项目已在使用 Docker，绝不可先删除/卸载旧 Docker。

## 2. 在 Windows 解压项目、生成安全密钥

下载 `pi_cafe_v3_complete.zip` 后解压，例如 `C:\Users\yourname\Downloads\pi_cafe_v3_complete`。**不要直接在压缩包里编辑 `.env`。**

Windows PowerShell 示例：

```powershell
cd "$HOME\Downloads\pi_cafe_v3_complete"
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

它只会创建当前项目的两个新文件：`edge/.env` 与 `cloud/.env`，并设置一对完全相同的云同步密钥（不会覆盖已存在的 `.env`）。若 Windows 上有 Python，也可运行 `py scripts\init_env.py`，**两个方法只选一个**。

查看但不要公开这些私密口令：

```powershell
notepad .\edge\.env
```

重点检查这两行，使用实际获取的地址：

```ini
CLOUD_URL=http://CLOUD_PUBLIC_IP:15001
PUBLIC_EDGE_URL=http://EDGE_LOCAL_IP:18080
```

如果 `hostname -I` 返回的真实地址不是 `EDGE_LOCAL_IP`，例如是 `192.168.1.88`，就应修改为 `PUBLIC_EDGE_URL=http://192.168.1.88:18080`。否则印出的二维码会指向错误位置。

你的阿里云公网 IP 从截图确认是 `CLOUD_PUBLIC_IP`。`edge/.env` 和 `cloud/.env` 的 `SYNC_TOKEN` 必须一致，其余 PIN/密钥可不同。不要把 `.env` 上传到公共 GitHub。

## 3. 部署阿里云（Ubuntu 22.04，建议先部署）

阿里云的 SSH 用户名使用你实际能够登录的账户：常见为 `root` 或 `ubuntu`。**不能仅凭控制台截图判断用户名**。如果只有阿里云网页终端能进但 PowerShell 不能 SSH，则先配置该账号允许 SSH 登录/密钥认证；不要把密码发给其他人。

Windows PowerShell 中，把以下示例的 `root` 换成真实账号：

```powershell
# 当前位置是 pi_cafe_v3_complete 根目录
ssh root@CLOUD_PUBLIC_IP "mkdir -p ~/pi-cafe-classroom"
scp -r .\cloud root@CLOUD_PUBLIC_IP:~/pi-cafe-classroom/
ssh root@CLOUD_PUBLIC_IP
```

进入云服务器 Ubuntu SSH：

```bash
cd ~/pi-cafe-classroom/cloud
ls -la
# 确认 app.py、compose.yaml、.env 均存在
# 如果本机需要 sudo 来操作 Docker，就统一在下列 docker 命令前加 sudo
docker compose -p pi-cafe-classroom-cloud up -d --build
docker compose -p pi-cafe-classroom-cloud ps
docker compose -p pi-cafe-classroom-cloud logs --tail=50 cafe-cloud
curl -fsS http://127.0.0.1:15001/health
```

看到 `"ok":true` 等字段代表云端应用本机正常。**如果 `15001` 被其他进程占用，切勿停止旧程序来抢端口；先停在这里检查。**

### 3.1 在阿里云轻量应用服务器放行 15001

你的控制台：**服务器 → Ubuntu-hock → 防火墙 → 添加规则**。规则：入方向 TCP，目的端口 `15001`。优先仅允许当前树莓派所在网络的公网出口 IPv4（/32）。如果课堂测试时网络出口可能变化，可临时放宽进行验证，但这属于教学演示用途，演示完立即撤销。SSH 的 `22` 和旧项目 `5000` 规则不要改。

从树莓派网络测试云端：

```bash
curl -m 7 -i http://CLOUD_PUBLIC_IP:15001/health
```

连接成功应返回 HTTP 200 和 JSON。阿里云控制台“远程连接”页面本身**不是** API 地址。

**安全提醒：** 当前示例使用 HTTP 明文传输云同步令牌和管理登录，不要在真实商用场景将它直接暴露在公网；生产需要 HTTPS/专用加密隧道、限制 IP、独立账号等。课堂演示时务必把开放范围降到最低。外网防火墙和主机 `ufw` 是不同层，且 Docker published ports 与 `ufw` 有特殊相互作用。

## 4. 通过 SSH 部署树莓派

### 4.1 Windows PowerShell 上传（先退出树莓派 SSH）

在 PowerShell、项目根目录下：

```powershell
# 替换为第1步看到的树莓派用户名及IP
ssh pi@EDGE_LOCAL_IP "mkdir -p ~/pi-cafe-classroom"
scp -r .\edge .\ops pi@EDGE_LOCAL_IP:~/pi-cafe-classroom/
ssh pi@EDGE_LOCAL_IP
```

注意：项目根目录的 `edge/.env` 必须已经生成并上传；`scp -r .\edge` 会复制 `edge` 目录及其子文件，**包括其中的 `.env`**。此方式无需全局复制旧项目，不会改旧目录。

### 4.2 启动两容器

```bash
cd ~/pi-cafe-classroom/edge
ls -la
# 必须检查 app.py、compose.yaml、.env、static/images/都存在
sudo docker compose -p pi-cafe-classroom up -d --build
sudo docker compose -p pi-cafe-classroom ps
sudo docker compose -p pi-cafe-classroom logs --tail=80 cafe-web
sudo docker compose -p pi-cafe-classroom logs --tail=80 cafe-sync
curl -fsS http://127.0.0.1:18080/health
```

第一次 build 需要拉 Docker 镜像和安装少量 Python 包，需联网。树莓派 3B+ 只有 1GB RAM，等待几分钟不等于卡死。如果提示 Docker daemon 权限错误，树莓派命令都可保持 `sudo docker ...`；如果旧项目使用无 `sudo` 的 Docker，则以它的配置为准。

**此时项目和外接屏幕是两个独立事情：**容器在后台提供服务，浏览器负责把收银台显示在外接屏幕上。因此仅 SSH 登录看到后台运行，并不代表屏幕已经打开收银台。

### 4.3 再做一次 Pi 上的自测

```bash
hostname -I
curl -fsS http://127.0.0.1:18080/api/menu
```

用 Windows 浏览器访问（电脑必须同局域网）：

```text
http://EDGE_LOCAL_IP:18080/
```

应看到有本地真实图片和价格的菜单。手机同一 Wi-Fi 上打开也应看到，否则先排查局域网，再打印二维码。

## 5. 让树莓派 HDMI 屏幕成为真正的收银台

### 5.1 先手动验证屏幕

如果树莓派外接屏幕上已经有桌面图标/任务栏，直接在树莓派 **图形桌面** 打开 Chromium：

```text
http://127.0.0.1:18080/cashier
```

首次会跳转登录页面，输入 `edge/.env` 的 `STAFF_PIN`。登录后显示 **“实时接单”** 和 **“柜台代客下单”** 两个模块。可以按 `F11` 全屏。

如果屏幕只有黑底文字终端，没有图形桌面，这不是网页服务故障，需要补装/启用桌面系统；请先确认 OS，**不要在 SSH 里盲目运行 `startx` 或重装系统**。

### 5.2 可选：设置下次进入桌面自动打开收银台

确认上一步手动成功、Chromium 可打开之后，从树莓派 SSH 执行：

```bash
cd ~/pi-cafe-classroom
python3 ops/install_kiosk.py
```

脚本只在**当前用户**下设置启动项：如果正在使用 labwc，追加到 `~/.config/labwc/autostart`，并在首次创建用户文件时保留可用的系统默认内容；否则写 `~/.config/autostart/pi-cafe-classroom.desktop`。这个方法针对 Raspberry Pi OS 的常见桌面环境；其他桌面可能需要另行设置。labwc 方案参考 Raspberry Pi 官方 kiosk 教程。

下次**登录桌面会话**时，将自动通过 Chromium 全屏打开：

```text
http://127.0.0.1:18080/cashier
```

如果希望通电后无人操作就显示，树莓派还需要设置**自动登录到桌面**；请先确认 `raspi-config` 的 Boot/Auto Login 设置是否可用，不要影响你正在运行的 SSH。

取消自动启动（不会卸载后端）：

```bash
cd ~/pi-cafe-classroom
python3 ops/remove_kiosk.py
```

如果你已打开了普通 Chromium，测试自动模式时先退出普通窗口，避免两份 Chromium 同时占用树莓派 3B+ 的内存。不能从纯 SSH 会话随意 `sudo python3 ops/install_kiosk.py`：这样修改的可能是 root 用户，而不是外接屏幕登录用户。

## 6. 生成一张“真正能扫”的桌码并打印成纸质二维码

**这是课堂演示的核心步骤。** 在手机和树莓派仍处于同一 Wi-Fi、且已确定 IP 正确时，在 Windows 电脑上打开：

```text
http://EDGE_LOCAL_IP:18080/qr
```

1. 如果跳转 `/login`，输入新项目 `edge/.env` 的 `STAFF_PIN`，登录。
2. 在 **餐桌二维码** 页面把“生成桌数”改成 `1`，点击“生成二维码”。
3. 页面上出现黑白二维码、`01 号桌`，下方应显示实际 `PUBLIC_EDGE_URL` 前缀。浏览器 `Ctrl + P` → 选择实体打印机打印到 A4，也可选择“另存为 PDF”稍后再打印。
4. **把打印出来的纸摆到桌面上**，使用手机系统相机识别。手机应该显示 `http://树莓派实际IP:18080/?table=1`；进入后页面顶部显示 **1号桌**。
5. **打印前先测试：**手机不用扫描，先在手机浏览器手动输入 `http://树莓派实际IP:18080/?table=1`，确保网页可以访问。

项目另带 `examples/table_01_QR_example_IP_EDGE_LOCAL_IP.png`，是经过 QR 解码检查的真实 PNG 二维码样张；**只在树莓派实际 IP 恰好为 EDGE_LOCAL_IP 时才可直接打印使用，其他 IP 必须通过 `/qr` 重新生成**。项目的 `/api/qr.svg?table=1` 提供真正可解码的 SVG 二维码，也可在浏览器中直接打开并保存。二维码由 `segno` 程序编码，**不是装饰性二维码截图**。

**关键限制：** 校园 Wi-Fi 如果开启“AP隔离 / 客户端隔离”，即使手机、树莓派都显示同一 SSID，也可能无法互访。可以改用允许局域网设备互访的路由器；部分手机热点也可以，但需事先测试。二维码只能包含地址，无法解决错误 IP 和被隔离的局域网。课堂前如果网络换了，树莓派 IP 可能变化，**必须重新生成、重新打印**。

## 7. 第一次真实下单 / 屏幕接单验证

1. 手机扫描 `1号桌` 纸质二维码。
2. 点击菜品图片卡片旁 `+`，加入例如“宫保鸡丁饭 ×1”和“柠檬气泡水 ×2”。
3. 手机底部点 **查看餐篮**，确认价格和桌号，点“确认下单”。
4. 手机出现“下单成功”和订单号，表示树莓派 SQLite 已完成本地写入。
5. 看树莓派大屏 `/cashier` 顶部“实时接单”，**一般不超过3秒**出现新订单（浏览器运行、局域网正常的前提下）。来源为 **扫码**，桌号 1，金额与手机一致。
6. 大屏点击“开始制作”“完成制作”“已取餐”展示状态流转；或在下方“柜台代客下单”区域自己选菜、填桌号、确认柜台下单。
7. 此时树莓派已经是“顾客点单 + 店员收银/接单”的完整局域网系统，**不需要后厨第二块屏幕**。源码仍保留可选 `/kitchen`，但不是演示必要环节。

若提交成功却不见大屏订单：检查浏览器是否处于 `/cashier`、有没有登录店员、刷新后是否加载成功；通过 `sudo docker compose -p pi-cafe-classroom logs --tail=100 cafe-web` 查看后端。

## 8. 离线演示（强烈建议用这一种：不会把 SSH 断掉）

⚠️ **不要**通过 SSH 运行 `sudo ifconfig wlan0 down`、`nmcli networking off`、断 Pi 网线等操作；否则你控制树莓派的 SSH 通道可能直接断掉。

**推荐模拟“阿里云无法连接”的真实业务故障：**在阿里云的 SSH 终端执行：

```bash
cd ~/pi-cafe-classroom/cloud
sudo docker compose -p pi-cafe-classroom-cloud stop cafe-cloud
```

此时云端订单接收服务停止，树莓派仍在线、屏幕仍可使用。手机扫码下新订单，大屏立即接单，本地数据库不会因为云端故障丢失。树莓派上可以观察同步代理日志：

```bash
cd ~/pi-cafe-classroom/edge
sudo docker compose -p pi-cafe-classroom logs --tail=30 cafe-sync
```

应能看到云端不可达/同步失败重试的日志（注意这属于云服务断开场景，不是物理断开整个互联网）。

再在阿里云 SSH 执行：

```bash
cd ~/pi-cafe-classroom/cloud
sudo docker compose -p pi-cafe-classroom-cloud start cafe-cloud
```

等待 5–20 秒后，在树莓派收银台上刷新订单；“等待云同步”字样应变为“已同步云端”。打开云端看板 `http://CLOUD_PUBLIC_IP:15001/`，输入 `cloud/.env` 的 `DASHBOARD_PIN`，可看到同步过来的订单及统计。云端按订单 ID + 状态版本去重，不会因重试而出现多个同 ID 订单。

## 9. 常用页面网址速查

| 页面 | 作用 | 地址（示例 IP） |
|---|---|---|
| 顾客扫码点餐 | 手机打开，带桌号 | `http://EDGE_LOCAL_IP:18080/?table=1` |
| 收银台 | 树莓派外接屏显示，查看扫码订单+柜台下单 | `http://127.0.0.1:18080/cashier` |
| 桌贴二维码 | 电脑访问并打印 | `http://EDGE_LOCAL_IP:18080/qr` |
| 菜单管理 | 价格/上架状态 | `http://EDGE_LOCAL_IP:18080/manage` |
| 本地统计 | 本地销量/待同步 | `http://EDGE_LOCAL_IP:18080/dashboard` |
| 云端看板 | 云端订单统计 | `http://CLOUD_PUBLIC_IP:15001/` |
| 本地存活检测 | 健康检查 | `http://EDGE_LOCAL_IP:18080/health` |

**如果 IP 不是 EDGE_LOCAL_IP，请替换所有相应局域网网址。**

## 10. 快捷命令、常见问题

树莓派检查：

```bash
cd ~/pi-cafe-classroom/edge
sudo docker compose -p pi-cafe-classroom ps
sudo docker compose -p pi-cafe-classroom logs -f cafe-web
sudo docker compose -p pi-cafe-classroom logs -f cafe-sync
```

正常更新代码后只重建新项目：

```bash
cd ~/pi-cafe-classroom/edge
sudo docker compose -p pi-cafe-classroom up -d --build
```

仅停止新项目（旧项目保持不动）：

```bash
cd ~/pi-cafe-classroom/edge
sudo docker compose -p pi-cafe-classroom stop
```

恢复：

```bash
cd ~/pi-cafe-classroom/edge
sudo docker compose -p pi-cafe-classroom start
```

**不要删除** `~/pi-cafe-classroom/edge/data` 或 `~/pi-cafe-classroom/cloud/data`，里面保存 SQLite 数据库。

- 手机扫不出来：先检查二维码内容是否 `http://真实Pi IP:18080/?table=1`，再手动输网址验证；若手输也打不开，检查同一 LAN、Wi-Fi 客户端隔离、Pi 防火墙、容器端口。
- 树莓派屏幕只有命令行：你可能装了 Pi OS Lite；需要图形桌面 + 浏览器，后端仍可单独运行。
- 显示器没有触摸屏：若想用收银台点单，需要树莓派外接鼠标/键盘；普通 HDMI 显示器不会自动支持触摸。也可以从 Windows 浏览器打开 `/cashier` 控制收银台。
- 浏览器登录后再次弹登录：检查系统时钟、cookie、`SESSION_SECRET` 和是否中途改了 `edge/.env`。
- 二维码可以扫码但网站打不开：二维码图案本身没有问题，属于 IP/网络互通问题。
- 图片不显示：检查 `edge/static/images/` 上传是否完整；`curl -I http://127.0.0.1:18080/static/images/tomato_egg.webp`。
- 云端连接失败：树莓派尝试 `curl -m 7 -i http://CLOUD_PUBLIC_IP:15001/health`；若不通检查轻量应用服务器防火墙，若 HTTP 401 同步检查两个 `.env` 的 `SYNC_TOKEN`，不要在聊天中公开密钥。
- CPU/内存不足：Pi 3B+ 1GB，别同时开很多 Chromium 标签。检查 `free -h`、`sudo docker stats --no-stream`，不用为了新项目停止原系统。

## 11. 源码目录与你可以修改的部分

```text
pi_cafe_v3_complete/
├── README.md                    # 本手册
├── DEMO_SCRIPT.md               # 课堂口播与操作脚本
├── setup_windows.ps1            # Windows自动生成两个环境密钥
├── edge/                        # 只上传树莓派
│   ├── app.py                   # Flask：菜单、订单、店员接口、真实二维码接口
│   ├── db.py                    # SQLite WAL / 事务 / 订单模型
│   ├── sync_agent.py            # 5秒定期同步云端
│   ├── menu_seed.py             # 菜品/价格（以分为单位）
│   ├── static/
│   │   ├── index.html + customer.js     # 手机顾客端
│   │   ├── cashier.html + cashier.js    # 屏幕实时接单+柜台手动下单
│   │   ├── qr.html + qr.js              # 可打印真实二维码
│   │   ├── style.css                    # 美观响应式设计
│   │   └── images/*.webp                # 12张本地食物图片
│   ├── Dockerfile + compose.yaml
│   └── .env.example             # 密钥配置模板
├── cloud/                       # 只上传阿里云
│   ├── app.py                   # 订单去重、SQLite、统计 API
│   ├── static/                  # 云端统计看板
│   └── Dockerfile + compose.yaml + .env.example
├── ops/
│   ├── cashier_kiosk.sh         # 外接屏幕浏览器自动打开收银台
│   ├── install_kiosk.py         # 安装当前用户图形桌面的开机自启动
│   └── remove_kiosk.py          # 撤销自启动
├── scripts/init_env.py         # 备选Python密钥生成器
└── tests/                      # SQLite/订单/云同步/二维码/页面测试
```

**怎么修改菜单价格：**如果是第一次运行前可修改 `edge/menu_seed.py`。启动后菜单已存入 SQLite，之后改 `menu_seed.py` 不会覆盖已经存在的数据；应通过 `/manage` 后台管理页面修改价格或上架状态。图片是 `edge/static/images/` 下的 WebP 文件，菜单中的 `image` 字段会关联图片名。

## 附录 A：如果阿里云 Ubuntu 尚未安装 Docker Compose

**先运行第 1 步检测。** 如果云端既没有 Docker Engine 也没有 Compose，并确认不会与旧 Docker 安装冲突，参照 Docker 官方 Ubuntu 22.04 文档部署：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: jammy
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker compose version
```

如发现先前已有 `docker.io` / `containerd` 版本或包冲突，**停下来确认，不要卸载旧 Docker 后盲装**。Docker 官方指南：https://docs.docker.com/engine/install/ubuntu/

## 附录 B：重要边界和安全

- 本项目是课堂教育演示，并非商家正式营业/收款方案。没有在线支付、退款、账务对账、个人隐私管理和订单跨设备冲突合并。
- 本地 LAN 若整体瘫痪，手机就无法连接树莓派，不是本项目所宣称的“断网仍可用”。
- 云端 HTTP 直接公网开放的令牌存在窃听风险；演示后关闭公网放行，正式应用需 HTTPS 或私有加密网络。
- 树莓派本地 SQLite 采用事务与 WAL，在正常供电条件下降低数据丢失风险；如果直接拔电、SD 卡损坏仍有风险，需 UPS/备份。
- 如果换了树莓派 IP，一定要改 `PUBLIC_EDGE_URL` 并重新部署新服务，**重印纸质二维码**。

