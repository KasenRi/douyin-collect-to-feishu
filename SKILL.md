---
name: douyin-collect-to-feishu
description: >-
  按关键词采集抖音视频：在已登录的浏览器里搜索 → 按点赞筛选 → 随机挑选 → 取详情 → 下载并校验 → 分段转写 → 在飞书知识库父节点下为每条视频建一篇子文档（含可播放视频）。用户给出抖音关键词或视频链接、并要求存进飞书时使用。
---
# 抖音关键词采集 → 转写 → 飞书知识库

**输入**
- 关键词
- 取前 N 条（默认 50）
- 点赞阈值（默认 >500）
- 挑几条（默认 2，随机）
- 飞书知识库父节点 `<WIKI_PARENT_URL>`
- 是否需要时间戳（默认不要）

**合规**：只采集公开内容，只读不互动。绝不点赞、评论、关注、私信；遵守抖音和飞书的平台条款，控制频率。转写和视频仅供个人或团队内部学习归档，不要二次分发。绝不打印 Cookie、Token、API Key。

## 0. 环境
- 抖音搜索要从中国大陆网络发起，在一台国内机器 `<CN_VPS>` 上完成（小内存机器建议开 swap）。
- 该机器上运行一个**由你本人手动登录过抖音**的 Chromium（持久 profile，例如 `<CHROME_PROFILE_DIR>`），并开启 `--remote-debugging-port=9222`，只监听 127.0.0.1。需要人工介入时用 VNC/noVNC 远程桌面操作这个浏览器（`<VNC_URL>`）。
- **只驱动这个真实浏览器**：用 Playwright `connect_over_cdp('http://127.0.0.1:9222')`。导出 Cookie 给签名接口，或另开无头浏览器，通常会触发验证码。
- 不要 kill 或重启这个浏览器；需要重启时先 `cp -a` 备份 profile。监控 `free -m`，可用内存 <200MB 就停。

## 0.5 前置条件检查（开跑前检查，缺一项立即报错停下）
- `ffmpeg`、`ffprobe`、`python3`、Playwright 可用；运行目录所在分区剩余空间 > 视频预计大小 ×3。
- 转写：环境变量 `GEMINI_BASE_URL`、`GEMINI_API_KEY` 已设置（只检查是否存在，不打印值）。`GEMINI_MODEL` 可选。
- 飞书：`lark-cli auth status` 显示 brand=feishu，且 user 身份可用。`lark-cli wiki +node-get --as user --node-token <WIKI_PARENT_URL>` 能读到父节点。
- 抖音：CDP 能连上，并且有 `sessionid` Cookie（见第 1 步）。

## 1. 登录检查
CDP 连上后，检查 `sessionid` Cookie 存在，且页面上没有「登录」按钮。掉线或出现验证码就停下，请用户在远程桌面里手动登录或完成验证，然后再继续。**不要自动破解验证码。**

## 2. 搜索
打开 `https://www.douyin.com/search/<URL编码关键词>?type=video`，监听 `/aweme/v1/web/search/item/` 或 `/general/search/` 的 JSON 响应，慢速随机滚动，直到 ≥N 条或没有更多。保存原始结果。
脚本：`python3 scripts/douyin_search.py search "<关键词>" 50 > search.json`

## 3. 筛选与挑选
保留 `statistics.digg_count` > 阈值的条目，随机挑 K 条（用户指定「第 X 条」或要排除已做过的 aweme_id 时照做）。
每条取这些字段：
- aweme_id、desc、作者昵称
- 点赞、收藏、评论、转发数
- create_time（换算成目标时区）
- 分享链接 `https://www.douyin.com/video/<aweme_id>`

搜索结果缺字段时，用 `scripts/douyin_search.py detail <aweme_id>` 抓 `/aweme/v1/web/aweme/detail/` 补全。
脚本：`python3 scripts/pick.py search.json 500 2 > picked.json`

## 4. 下载与校验
- 用 `play_urls` 下载，最高码率优先。带桌面 Chrome UA 和 `Referer: https://www.douyin.com/`，在国内机器上 `curl` 下载 mp4。播放地址带签名，会过期，拿到后尽快下载。
- 播放地址只用于下载，**不写进文档**。
- 完整性校验，三项都过才算下载成功，否则重下：
  1. 文件大小 = `Content-Length`，且量级合理（10 分钟原画通常是几百 MB，只有几十 MB 多半是断了）。
  2. 最后一个音频包的时间戳接近总时长。mp4 头里声明的时长在截断时仍是完整值，不可信。
  3. `ffmpeg -v error -i f.mp4 -f null -` 没有 `partial file` 之类的报错。

  脚本：`scripts/check_video.sh f.mp4 <Content-Length>`
- 视频太大不便内嵌时，转一份 540p 的低码率副本（几十 MB）用于上传，原画留在本地。

## 5. 转写（Gemini 兼容接口）
- 接口：`POST {GEMINI_BASE_URL}/v1beta/models/<URL编码的模型名>:generateContent`。
  - 模型名用 `urllib.parse.quote(model, safe='-._~')` 编码，否则模型名里有非 ASCII 字符时会出错。
  - 鉴权头 `x-goog-api-key`。
  - 模型由 `GEMINI_MODEL` 配置，例如 `gemini-2.5-flash` 一类的 flash 模型。
- 音频内联，字段名用 camelCase：`{"inlineData":{"mimeType":"audio/mp3","data":<base64>}}`。部分代理会拒绝 snake_case 的 `inline_data`。不要用 chat/completions 的音频输入：有的代理会丢掉音频，模型就会编造内容。
- 用 ffmpeg 抽 16kHz 单声道 mp3。**默认 5 分钟一段；游戏类长视频 120 秒一段**。
- 某段返回 400、`prompt_blocked` 或被安全拦截时，自动对半切重试（例如 120→60→30→15 秒，下界约 7 秒），并换中性提示词（说明这是公开视频的语音转写归档）。
- 按接口限额控速（例如 10 次/分钟）；403、429、5xx 指数退避重试。
- 默认提示词：逐字转写为简体中文，**不要时间戳**，整理成普通文章段落，不要标题、代码块或额外说明。用户明确要求时才带时间戳。口语和术语照原样保留。
- 校验：内容和视频描述的主题一致，覆盖到结尾；没有残留「拦截/无法转写」的占位。对不上就重转，绝不编造。
- 脚本：`python3 scripts/transcribe.py audio.mp3 120 > transcript.txt`

## 6. 写飞书（lark-cli，`--as user`）
用官方 `lark-cli`，brand=feishu。不要用浏览器 Cookie 调内部接口；应用身份（tenant_access_token）需要另外开通 wiki、docx、drive 权限，并被加进知识库，否则会失败。

**文档模板（标准格式）**：doc.md 写成下面这样，文档标题用 `--title` 传。
- 转写每段一个普通段落，段与段之间空一行。
- 不要时间戳，不要代码块，**不要写播放地址**。
- 「## 视频」放在最后，视频由 `+media-insert` 追加到它下面。

```markdown
## 基本信息

- **标题/描述**：<视频描述原文，含话题标签>
- **作者**：<作者昵称>
- **发布时间**：<YYYY-MM-DD HH:MM 时区>
- **点赞**：<n>｜**收藏**：<n>｜**评论**：<n>｜**分享**：<n>
- **分享链接**：https://www.douyin.com/video/<aweme_id>
- **搜索关键词**：<关键词>
- **采集日期**：<YYYY-MM-DD>

## 完整转写

第一段转写正文……

第二段转写正文……

## 视频
```

**命令**（文件路径要相对当前目录）：
1. `cd <运行目录>`
2. `lark-cli docs +create --as user --parent-token <WIKI_PARENT_TOKEN> --title "抖音｜<简短标题>｜<aweme_id>" --doc-format markdown --content @doc.md`，从返回中取 document_id。
3. `lark-cli docs +media-insert --as user --doc <document_id> --type file --file-view preview --file <aweme_id>.mp4`
4. `lark-cli wiki +node-get --as user --node-token <document_id>`，取 wiki 链接。

**视频必须是可播放块**：正确的结构是预览视图块（block_type 33，`view.view_type=2`）包着文件块（block_type 23）。`--file-view preview` 会自动建出这个结构。只有一个裸文件块时，页面上显示为附件卡片，不能直接播放。

**重做已有文档（链接不变）**：`lark-cli docs +update --as user --doc <document_id> --command overwrite --doc-format markdown --content @doc.md`，会清掉旧内容和旧视频块，然后再执行一次 `+media-insert --file-view preview`。

## 6.5 清理
不用 `rm -rf`。中间切片放在运行目录的 `tmp/` 下，确认结果后逐个 `rm -- <文件>`，或移到回收目录。不要删原视频、转写和 doc.md。

## 7. 验证并汇报
读回每篇文档验证，任何一项不过都要修好再汇报：
- `lark-cli docs +fetch --as user --doc <链接>` 的结果里：
  - 二级标题依次是「基本信息」「完整转写」「视频」。
  - 字段名有 `<b>` 加粗，并且都在 `<ul>` 列表里。
  - 没有 douyinvod、play_addr 之类的播放地址。
  - 没有 `<pre>`、`<code>`，也没有 `[00:00]` 这类时间戳。
- `lark-cli api GET /open-apis/docx/v1/documents/<document_id>/blocks --params '{"page_size":500}' --as user` 的结果里，只有一个 23 块，它的父块是 33，且 `view_type=2`。

汇报内容：
- 搜索条数、过阈值条数
- 挑中的视频（标题链接、作者、点赞）
- 每篇飞书文档链接
- 转写字数和一句话概要
- 所有失败或偏差
