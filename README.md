# douyin-collect-to-feishu

一个给 AI Agent（Claude Code / Cursor / Hermes 等）用的 Skill：用关键词搜索抖音视频，按点赞筛选后随机挑几条，下载、校验完整性，再分段转写成文字。每条视频在飞书知识库指定节点下建一篇子文档，包含基本信息、完整转写和可直接播放的视频。

> ⚠️ **合规声明**：仅采集公开内容，只读不互动（不点赞、不评论、不关注、不私信）。请遵守抖音和飞书的用户协议，控制频率。内容仅供个人或团队内部学习归档。本项目**不包含**任何验证码破解代码。遇到验证码请人工处理。

## 流程

```
关键词
  │
  ▼
已登录 Chromium（国内机器，CDP 9222）──► 抓搜索接口 JSON（scripts/douyin_search.py）
  │
  ▼
按点赞阈值筛选 → 随机挑 K 条（scripts/pick.py）
  │
  ▼
下载 mp4 → 三项完整性校验（scripts/check_video.sh）
  │
  ▼
ffmpeg 抽音频 → Gemini generateContent 分段转写，被拦截时对半切（scripts/transcribe.py）
  │
  ▼
lark-cli docs +create（模板）→ +media-insert --file-view preview（可播放视频）
  │
  ▼
读回验证（标题结构 / 加粗 / 无播放地址 / 视频块类型）→ 汇报链接
```

## 依赖

| 组件 | 用途 |
|---|---|
| Chromium / Chrome | 你本人手动登录抖音，以 `--remote-debugging-port=9222` 启动 |
| Python 3.9+ 和 Playwright（`pip install playwright`） | 通过 CDP 连接已登录的浏览器 |
| ffmpeg / ffprobe | 校验下载、抽音频、切段 |
| [lark-cli](https://www.npmjs.com/package/@larksuite/cli)（`npm i -g @larksuite/cli`） | 以用户身份写飞书文档，brand=feishu |
| Gemini 兼容接口 | 音频转写（官方 API 或兼容代理均可） |

抖音搜索通常需要中国大陆网络。建议在一台国内 VPS 上跑浏览器，用 VNC/noVNC 登录和处理验证码。

## 配置

复制 `.env.example` 为 `.env` 并填写（`.env` 已被 `.gitignore` 忽略）：

```bash
GEMINI_BASE_URL=https://<your-gemini-compatible-endpoint>
GEMINI_API_KEY=<your-api-key>
GEMINI_MODEL=gemini-2.5-flash   # 任意支持音频输入的 flash 模型
GEMINI_RPM=10                   # 每分钟请求上限
CDP_URL=http://127.0.0.1:9222
WIKI_PARENT_URL=https://<your-tenant>.feishu.cn/wiki/<WIKI_PARENT_TOKEN>
```

飞书授权：`lark-cli auth login`（选 feishu），确认 `lark-cli auth status` 正常，且你的账号对父节点有编辑权限。

## 单独使用脚本

```bash
set -a; . ./.env; set +a
python3 scripts/douyin_search.py search "关键词" 50 > search.json
python3 scripts/pick.py search.json 500 2 > picked.json
curl -L -A "Mozilla/5.0 ..." -e https://www.douyin.com/ -o <id>.mp4 "<play_url>"
scripts/check_video.sh <id>.mp4
ffmpeg -i <id>.mp4 -vn -ac 1 -ar 16000 -b:a 48k <id>.mp3
python3 scripts/transcribe.py <id>.mp3 300 > transcript.txt   # 游戏类用 120
```

## 安装到 Agent

把整个目录复制到对应 Agent 的 skills 目录：

- **Claude Code**：`~/.claude/skills/douyin-collect-to-feishu/`（或项目内 `.claude/skills/`）
- **Cursor**：项目内 `.cursor/skills/douyin-collect-to-feishu/`（或 Cursor 识别的全局 skills 目录）
- **Hermes**：`~/.hermes/skills/media/douyin-collect-to-feishu/`

```bash
git clone <this-repo> ~/.claude/skills/douyin-collect-to-feishu
```

然后对 Agent 说：「用 douyin-collect-to-feishu 搜『XXX』，前 50 条里点赞超过 500 的随机挑 2 条，存到 <飞书知识库链接> 下面」。

## 飞书文档长什么样

标题：`抖音｜<简短标题>｜<aweme_id>`

- **基本信息**（二级标题）：标题/描述、作者、发布时间、点赞｜收藏｜评论｜分享、分享链接、搜索关键词、采集日期。字段名加粗，排成无序列表。
- **完整转写**（二级标题）：去掉时间戳的普通段落，没有代码块。
- **视频**（二级标题）：页内可直接播放的视频（预览视图块包着文件块），不是附件卡片。

文档里不出现带签名的播放地址。

## License

MIT
