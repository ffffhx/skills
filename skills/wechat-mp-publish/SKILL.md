---
name: "wechat-mp-publish"
description: "自动将文章发布到微信公众号：优先走公众号后台浏览器自动化，支持个人主体账号、Markdown 转 HTML、后台 AI 生成封面图；对具备权限的账号也可走 API 发布。"
---

# 微信公众号自动发布

## 目标

给定一篇 Markdown / PDF 文件或正文内容，自动完成微信公众号图文的完整发布链路，并根据账号类型自动选择模式：

1. 从 `.md` / `.pdf` 文件自动提取文章标题
2. 默认作者使用 `繁漪`
3. 个人主体账号：走公众号后台浏览器自动化
4. 自动把 Markdown 转为公众号 HTML
5. 在后台调用 AI 生成封面图
6. 自动填写标题、作者、摘要、正文并保存草稿或直接发表
7. 对具备权限的账号，仍可回退到 API 发布模式

## 何时调用

当用户提出以下诉求时调用：

- “自动发公众号文章”
- “帮我把这篇文章发布到微信公众号”
- “不要手动操作，直接把内容发到公众号”
- “把这段内容生成公众号图文并发布”

## 前置条件

- 个人主体账号优先使用后台浏览器自动化模式，不依赖发布 API。
- 若使用后台自动化模式，需要本机可运行 `npx playwright test`。
- 若使用 API 模式，需要账号具备微信公众号草稿/发布接口权限。
- 自 2025 年 7 月起，个人主体账号、企业主体未认证账号及不支持认证的账号会失去发布相关接口调用权限，因此这类账号不要优先走 API 模式。

## 入参

- `title`（可选）：文章标题；若未提供且输入是 Markdown，会优先取第一条一级标题
- `content`（必填）：文章正文
- `publish_mode`（可选）：`auto`、`web`、`api`，默认 `auto`
- `action`（可选）：`draft` 或 `publish`，默认 `draft`
- `content_format`（可选）：`auto`、`markdown`、`html`、`text` 或 `pdf`，默认 `auto`
- `thumb_media_id`（可选）：仅 API 模式需要
- `author`（可选）：作者名，默认读取 `WECHAT_MP_AUTHOR`，再回退到 `繁漪`
- `digest`（可选）：摘要
- `content_source_url`（可选）：原文链接
- `cover_prompt`（可选）：后台 AI 生成封面图时的提示词
- `need_open_comment`（可选）：`0` 或 `1`，默认 `0`
- `only_fans_can_comment`（可选）：`0` 或 `1`，默认 `0`
- `poll_interval`（可选）：轮询间隔秒数，默认 `5`
- `timeout`（可选）：总等待秒数，默认 `180`

## 环境变量

- `WECHAT_MP_ACCESS_TOKEN`：可选，已拿到 token 时直接使用
- `WECHAT_MP_APPID`：可选，与 `WECHAT_MP_APPSECRET` 配合获取 token
- `WECHAT_MP_APPSECRET`：可选，与 `WECHAT_MP_APPID` 配合获取 token
- `WECHAT_MP_AUTHOR`：可选，默认作者名
- `WECHAT_MP_TITLE`：后台自动化模式下的文章标题
- `WECHAT_MP_CONTENT` / `WECHAT_MP_CONTENT_FILE`：后台自动化模式下的正文输入
- `WECHAT_MP_CONTENT_FORMAT`：后台自动化模式下的正文格式，默认 `auto`
- `WECHAT_MP_ACTION`：后台自动化模式下的操作，`draft` 或 `publish`
- `WECHAT_MP_DIGEST`：后台自动化模式下的摘要；不传则自动从正文提取
- `WECHAT_MP_COVER_PROMPT`：后台 AI 生成封面图时的提示词
- `WECHAT_MP_KEEP_BROWSER`：设为 `1` 时发布后保留浏览器不关闭
- `WECHAT_MP_USER_DATA_DIR`：浏览器持久化登录目录；默认复用 `.trae/skills/wechat-mp-publish/scripts/.wechat-mp-browser`

## 工作流

### 1）模式选择

- 个人主体账号、未认证账号：优先走后台浏览器自动化模式。
- 有接口权限的认证账号：可走 API 模式。
- `auto` 模式下，默认按“个人账号优先后台自动化、企业可选 API”处理。

### 2）整理文章内容

- 如果拿到的是 Markdown，先自动转换成适合公众号图文的 HTML，再发布。
- 如果拿到的是 PDF，先提取文本，再按公众号文章样式转成 HTML，再发布。
- 如果拿到的是纯文本，先按段落转为安全 HTML。
- 如果拿到的是 HTML，直接使用。
- 不要把 token、secret、cookie、手机号等敏感信息写进正文。

### 3）后台自动化模式（个人账号优先）

使用 Playwright 打开公众号后台并完成真实页面操作：

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action draft \
  --content-file "/absolute/path/to/article.md" \
  --content-format auto \
  --cover-prompt "根据文章主题生成公众号封面"
```

直接发表时：

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action publish \
  --content-file "/absolute/path/to/article.md"
```

如果输入是 PDF，也可以直接这样调用：

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action draft \
  --content-file "/absolute/path/to/article.pdf"
```

底层后台自动化脚本位置：

`npx playwright test .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp_web.spec.js --headed --workers=1`

脚本会自动：

- 打开公众号后台并等待扫码登录
- 复用持久化浏览器目录，第二次起默认免扫码
- 新建图文页
- 从 Markdown 第一条一级标题自动提取标题；若没有则回退文件名
- PDF 优先取文档 metadata 标题；没有则回退文件名
- 自动把 Markdown 转成公众号 HTML
- 自动把 PDF 文本提取并按分页结构转成公众号 HTML
- 默认作者使用 `繁漪`
- 自动填写标题、作者、摘要、正文
- 尝试调用后台 AI 生图能力生成封面
- 根据 `action` 选择“保存草稿”或“直接发表”

### 4）API 模式（仅有权限账号）

优先使用仓库内脚本：

`python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py`

支持两种正文输入方式：

- 直接传 `--content`
- 或使用 `--content-file`

推荐命令（直接发布 HTML）：

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --title "<标题>" \
  --content-file "/absolute/path/to/article.html" \
  --content-format html \
  --thumb-media-id "<thumb_media_id>" \
  --author "<作者>" \
  --digest "<摘要>" \
  --content-source-url "<原文链接>"
```

如果正文是纯文本，可改为：

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --title "<标题>" \
  --content-file "/absolute/path/to/article.txt" \
  --content-format text \
  --thumb-media-id "<thumb_media_id>"
```

如果正文是 Markdown，直接这样调用：

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --title "<标题>" \
  --content-file "/absolute/path/to/article.md" \
  --content-format markdown \
  --thumb-media-id "<thumb_media_id>"
```

如果 `--content-format` 不传，脚本会自动识别：

- `.md` / `.markdown` 文件按 Markdown 处理
- `.html` / `.htm` 文件按 HTML 处理
- 明显带 HTML 标签的内联内容按 HTML 处理
- 其余内容优先按 Markdown 特征识别，否则回退为纯文本

### 5）脚本行为

API 脚本会自动：

- 优先读取 `WECHAT_MP_ACCESS_TOKEN`
- 否则调用 `https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=APPID&secret=APPSECRET` 获取 token
- 对 Markdown 自动渲染标题、段落、列表、引用、代码块、链接和图片为公众号可接受的 HTML
- 调用 `POST https://api.weixin.qq.com/cgi-bin/draft/add?access_token=ACCESS_TOKEN`
- 调用 `POST https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token=ACCESS_TOKEN`
- 调用 `POST https://api.weixin.qq.com/cgi-bin/freepublish/get?access_token=ACCESS_TOKEN` 轮询状态

### 6）成功判定

后台自动化模式成功时，输出当前发布结果页 URL。

API 模式当 `publish_status=0` 时视为成功，并输出：

- `media_id`
- `publish_id`
- `article_id`
- `article_url`

### 7）失败处理

后台自动化模式失败时，优先检查：

- 是否已完成扫码登录
- 后台页面文案是否改版，导致选择器失效
- 当前账号是否需要人工确认发表
- AI 生图入口文案是否变化

API 模式会直接失败退出，并带出微信返回的错误信息；重点关注：

- `48001`：接口未授权
- `53503`：草稿未通过发布检查
- `53504`：需到公众平台官网使用草稿
- `53505`：需先在公众平台官网手动保存成功后再发表

## 输出

API 模式成功时输出 JSON，字段示例：

```json
{
  "media_id": "MEDIA_ID",
  "publish_id": "PUBLISH_ID",
  "publish_status": 0,
  "article_id": "ARTICLE_ID",
  "article_url": "https://mp.weixin.qq.com/s/..."
}
```

## 实施约束

- 不要打印 `WECHAT_MP_ACCESS_TOKEN`、`WECHAT_MP_APPSECRET` 等敏感信息。
- 后台自动化模式下不要要求用户先提供 `thumb_media_id`；优先尝试后台 AI 生成封面图。
- 只做“创建草稿并发布文章”，不要顺手删除历史草稿/已发布文章。
- API 模式缺少 `thumb_media_id` 时直接报错，不要伪造封面。
- 不要把 Markdown 原样直接提交给微信接口；必须先经过脚本转换。
- PDF 当前只支持可提取文本的文档；纯扫描图片 PDF 暂不支持。

## 示例触发语句

- “把这篇文章自动发布到公众号，封面素材 ID 是 xxx”
- “用公众号接口发文，不要手动点后台”
- “我是个人主体账号，直接走后台自动化发布”
- “不要 `thumb_media_id`，直接用后台 AI 生成封面”
- “直接指定一个 md 文件，帮我存到公众号草稿箱”
- “直接指定一个 md 文件，帮我发成公众号文章”
- “把项目里的 PDF 转成公众号文章并保存草稿”
- “读取这个 markdown 文件并直接发布到公众号”
- “读取这个 html 文件并发布成公众号图文”
