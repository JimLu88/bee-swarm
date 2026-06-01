# 群晖 DS923+ 部署指南（H-SEMAS 智囊团）

一句话：**一个后端容器(8100)同时提供 API + 网页**，手机/电脑浏览器直接开就能用；爬虫(8003)、向量库(6333)为辅助容器。C 档（本地离线大模型）已默认关闭（NAS 无 GPU）。

---

## 0. 前提
- DSM 7.2+，已安装 **Container Manager**（套件中心可装）。
- DS923+ 是 x86_64，能直接跑标准 amd64 镜像。建议内存加到 **16–32GB**。
- SSH 已开启（控制面板 → 终端机和 SNMP → 启用 SSH）。

## 1. 放代码（两个仓库并排）
在 NAS 上建目录（示例 `/volume1/docker/`），把**两个仓库并排克隆**：
```
/volume1/docker/
├── h-semas/          # 主仓库（本项目）
└── AI 数据爬虫/       # 爬虫仓库（bee-scraper）
```
```sh
cd /volume1/docker
git clone <你的 h-semas 仓库地址> h-semas
git clone <你的 数据爬虫 仓库地址> "AI 数据爬虫"
```

## 2. 配 .env（密钥/开关）
```sh
cd /volume1/docker/h-semas
cp .env.example .env
vi .env     # 填 AMAP_KEY、LLM 聚合 Key 等；HSEMAS_DISABLE_LOCAL_TIER 已在 compose 里强制=1
```
> `.env` 不进 git，安全。AMAP_KEY = 高德 Web 服务 Key（地图钉店用）。

## 3. 起服务
```sh
cd /volume1/docker/h-semas
docker compose up -d --build      # 首次构建较久（要装 Python 依赖 + 构建前端）
docker compose ps                 # 看三个容器是否 healthy
```
- 内网访问：手机/电脑同 WiFi 打开 **http://<NAS内网IP>:8100**（如 http://192.168.1.20:8100）。
- iOS Safari / 安卓 Chrome → 「添加到主屏幕」即可像 App 一样全屏打开（PWA）。

## 4. 外网访问 + HTTPS（你选了「也要在外面用」）
推荐用群晖自带能力，零额外成本：
1. **DDNS**：控制面板 → 外部访问 → DDNS → 新增，选 Synology 免费域名（`xxx.synology.me`）。
2. **路由器端口转发**：把外网 443 → NAS 443（或用群晖 QuickConnect，但反代更稳）。
3. **反向代理**：控制面板 → 登录门户 → 高级 → 反向代理 → 新增：
   - 来源：`https`，主机名 `xxx.synology.me`，端口 `443`
   - 目标：`http`，主机名 `localhost`，端口 `8100`
   - 勾选自定义标头 → 「WebSocket」（决策流式输出要用 WS）。
4. **证书**：控制面板 → 安全性 → 证书 → 用 Let's Encrypt 给该域名签发，绑定到上面反代。
→ 之后手机在外网开 **https://xxx.synology.me** 即可，全程 HTTPS（PWA 安装体验也更完整）。

> 安全提醒：对外暴露务必只走 443+证书；如需更稳，在反代前加群晖防火墙规则限制来源地区。

## 5. 定时自动更新（你选了「定时自动更新」）
代码已带 `deploy/update.sh`（拉主仓库 + 爬虫仓库 → `docker compose up -d --build`）。
设置群晖定时任务：
1. 控制面板 → **任务计划** → 新增 → **计划的任务 → 用户定义的脚本**。
2. 用户选 `root`；计划：每天 **04:00**（避开 02:00 演化器跑的时段）。
3. 运行命令：
   ```sh
   sh "/volume1/docker/h-semas/deploy/update.sh" >> "/volume1/docker/h-semas/deploy/update.log" 2>&1
   ```
→ 每天自动拉取你电脑端推上去的更新（含 p12 自更新合并的提交），重建容器，**Web 与手机端一起联动更新**。
> 注意：自动更新生效的前提是你把本地改动 **push 到了 NAS 能 `git pull` 到的远端**。若纯本机开发未推远端，改成手动执行 update.sh 即可。

## 6. 数据与备份
- 决策历史/记忆/知识库持久化在 `./backend/data`（已挂载卷，重建容器不丢）。
- 向量库在 `./qdrant_storage`。
- 建议把 `/volume1/docker/h-semas/backend/data` 纳入群晖 Hyper Backup。

## 7. 常用运维
```sh
docker compose logs -f backend         # 看后端日志
docker compose restart backend         # 只重启后端
docker compose down                    # 停服务
docker compose up -d --build           # 重建+起（= update.sh 第3步）
```

## 8. 档位说明（C 档为何关）
- A 档（旗舰）/ B 档（便宜云）：算力在云端，NAS 只转发请求，毫无压力。
- **C 档（本地 ollama）**：需 GPU，DS923 无显卡纯 CPU 跑 7B 模型约 1–3 token/s，不可用 → 已用 `HSEMAS_DISABLE_LOCAL_TIER=1` 自动降级到 B 档。
