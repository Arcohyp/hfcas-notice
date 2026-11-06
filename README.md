# hfcas-notice

定时抓取研究生通知页面并通过钉钉群机器人推送新增条目，防止错过奖学金、评优、毕业、学位等关键通知。

默认监控 9 个频道，全部推送、不做关键词过滤：

| 站点 | 频道 |
| --- | --- |
| 合肥物质院研究生处 (hf.cas.cn) | 通知公告、**奖助学金**、公示公开、毕业离校、学籍管理、开题考核、项目申报 |
| 中科大研究生院 (gradschool.ustc.edu.cn) | 通知公告 (column/9) |
| 安光所 (aiofm.cas.cn) | 通知公告 |

新纳入监控的栏目会自动收录既有条目作为基线（不推送），最近 7 天内的条目仍会照常推送（大概率还在有效期内），之后每次运行只推送 diff。

## 依赖

- Python 3.10+，仅依赖 `requests`

```bash
pip install requests
```

## 配置

钉钉机器人凭据二选一：

1. 环境变量 `DINGTALK_WEBHOOK` / `DINGTALK_SECRET`（机器人需开启"加签"安全设置）
2. 复制 `secrets.example.json` 为 `secrets.json` 并填入凭据（该文件已被 gitignore）

## 运行

```bash
python3 monitor.py            # 正常执行：抓取、diff、推送、写状态
python3 monitor.py --dry-run  # 只打印结果，不推送、不写状态
python3 dingtalk_notify.py    # 单独测试钉钉推送
```

首次运行会把所有频道标记为基线并推送一条"监控已启动"消息；第二次起只推送新条目。

## 定时（cron）

每小时整点运行一次，输出追加到日志：

```
0 * * * * /usr/bin/python3 /path/to/hfcas_notice/monitor.py >> /path/to/hfcas_notice/logs/cron.log 2>&1
```

## 自定义频道

在 `monitor.py` 的 `CHANNELS` 字典里加一行即可。页面解析支持两种格式：

- `hf`：hf.cas.cn 系静态列表（`<a href="./YYYYMMDD/t*.html" title="...">` + 日期在条目尾部）
- `ustc`：gradschool.ustc.edu.cn 文章列表（`/article/ID` + `<time>` 标签）
- `aiofm`：安光所列表（链接文本为标题，日期 `YYYY.MM.DD`）

## 文件说明

```
monitor.py            # 主脚本：抓取、去重、推送
dingtalk_notify.py    # 钉钉 markdown 推送（加签）
secrets.example.json  # 凭据模板
data/seen.json        # 已收录条目状态（自动生成，gitignore）
logs/                 # 运行日志（gitignore）
```
