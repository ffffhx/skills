# 微信公众号 Markdown 自动发布项目说明书

## 项目简介

这是一个面向 Agent 的微信公众号发布项目，目标是把一篇本地 Markdown 或 PDF 文件自动转换为公众号图文内容，并进一步完成：

- 保存到公众号草稿箱
- 或直接发布为公众号文章

项目默认服务于你的实际场景：**个人主体公众号账号**。

因此整体设计上优先采用：

- **后台浏览器自动化**，而不是微信开放接口发布
- **Markdown 自动转公众号 HTML**
- **自动复用登录态**，第二次默认免扫码
- **优先使用后台 AI 生成封面**，不要求手工准备 `thumb_media_id`

---

## 设计目标

希望最终达到的体验是：

1. 用户只需要给 Agent 一篇 `.md` 或 `.pdf` 文件
2. Agent 自动识别标题、作者、正文
3. 自动把 Markdown 渲染成公众号可接受的 HTML
4. 自动登录或复用已保存登录态打开公众号后台
5. 自动填写标题、作者、摘要、正文
6. 自动尝试使用后台 AI 生成封面图
7. 按需要保存到草稿箱，或者直接发布

---

## 当前实现形态

这个项目现在是 **`Skill + 本地 CLI + 浏览器自动化脚本`** 的组合。

### 1）Skill

用于让 Agent 知道“什么时候应该调用公众号发布能力”。

- Skill 文件：`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/SKILL.md`

### 2）Python CLI

这是统一执行入口，负责：

- 读取 Markdown / HTML / 纯文本
- 自动识别内容格式
- 自动提取标题
- 设置默认作者
- 在 `web` 或 `api` 模式之间分流
- 调起浏览器自动化脚本或调用微信 API

- CLI 文件：`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py`

### 3）Web 自动化脚本

用于真实操作公众号后台页面，适合个人主体账号。

- 自动打开公众号后台
- 自动复用登录态
- 自动填写文章内容
- 自动保存草稿或直接发布

- 脚本文件：`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/scripts/publish_wechat_mp_web.spec.js`

---

## 为什么优先走后台自动化

微信官方从 2025 年 7 月起，对以下账号回收了发布接口调用权限：

- 个人主体账号
- 企业主体未认证账号
- 不支持认证的账号

所以对于你的账号类型，最稳的方案不是 `draft/add + freepublish/submit`，而是：

`Markdown -> 本地 CLI -> Playwright -> 公众号后台真实页面操作`

也就是说，这个项目虽然保留了 API 模式，但**默认推荐模式是 `web`**。

---

## 目前已经支持的能力

## 输入侧

- 支持直接传 `.md` 文件
- 支持直接传 `.pdf` 文件
- 支持直接传入 HTML 内容
- 支持直接传入纯文本内容
- `--content-format auto` 时自动识别格式

## Markdown 处理侧

- 自动识别一级标题 `# 标题`
- 不传 `--title` 时优先使用 Markdown 第一条一级标题
- 如果没有一级标题，则回退到文件名
- 自动把 Markdown 转为公众号 HTML
- 支持基础标题、段落、列表、引用、代码块、链接、图片

## PDF 处理侧

- 自动识别 `.pdf` 文件
- 优先提取 PDF metadata 标题
- 若 metadata 不可用，则回退到文件名
- 自动提取每页文本并按分页结构转为公众号 HTML
- 适用于“可复制文本”的 PDF
- 纯扫描图片 PDF 当前暂不支持

## 元信息默认值

- 默认作者：`繁漪`
- 默认摘要：从渲染后的 HTML 自动提取前 120 个字符

## 发布侧

- `web + draft`：保存到草稿箱
- `web + publish`：直接发布
- `api + publish`：保留给仍然有接口权限的账号

## 登录态侧

- 第一次需要扫码登录公众号后台
- 浏览器使用持久化目录保存登录态
- 第二次默认复用登录态，通常无需再次扫码

---

## 项目目录结构

```text
skills/
├── .trae/
│   └── skills/
│       └── wechat-mp-publish/
│           ├── SKILL.md
│           └── scripts/
│               ├── publish_wechat_mp.py
│               └── publish_wechat_mp_web.spec.js
├── package.json
├── package-lock.json
└── wechat-mp-publish-manual.md
```

补充说明：

- `package.json` 用来安装 `@playwright/test`
- `publish_wechat_mp.py` 是统一入口
- `publish_wechat_mp_web.spec.js` 是个人账号的核心执行脚本

---

## 环境要求

运行这个项目需要：

- `Python 3`
- `Node.js`
- `npm`
- 本机可用的 Chrome 浏览器

建议先在项目根目录安装依赖：

```bash
cd /Users/bytedance/code/skills
npm install
```

---

## 最常用的使用方式

对于个人主体公众号，最推荐直接用 CLI。

## 1）保存 Markdown 到草稿箱

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action draft \
  --content-file "/absolute/path/to/article.md"
```

## 2）直接发布 Markdown

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action publish \
  --content-file "/absolute/path/to/article.md"
```

## 3）把 PDF 保存到草稿箱

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action draft \
  --content-file "/absolute/path/to/article.pdf"
```

## 4）把 PDF 直接发布

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action publish \
  --content-file "/absolute/path/to/article.pdf"
```

## 3）指定 AI 封面提示词

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action draft \
  --content-file "/absolute/path/to/article.md" \
  --cover-prompt "极简科技感公众号封面，蓝白配色，带标题关键词"
```

## 4）指定登录态目录

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action draft \
  --content-file "/absolute/path/to/article.md" \
  --user-data-dir "$HOME/.wechat-mp-profile"
```

---

## CLI 参数说明

CLI 帮助入口：`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py:41`

常用参数如下：

- `--content-file`：指定本地文章文件
- `--content`：直接传入内容字符串
- `--publish-mode`：`auto | web | api`
- `--action`：`draft | publish`
- `--content-format`：`auto | markdown | html | text | pdf`
- `--title`：手工指定标题；不传则自动提取
- `--author`：手工指定作者；不传默认 `繁漪`
- `--digest`：手工指定摘要
- `--cover-prompt`：后台 AI 封面提示词
- `--user-data-dir`：浏览器登录态目录
- `--keep-browser`：执行后不关闭浏览器
- `--render-only`：只把内容渲染成 HTML，不进行发布

---

## 自动化执行流程

## Step 1：读取输入

CLI 会从以下两种输入中二选一：

- `--content-file`
- `--content`

## Step 2：识别格式

如果 `--content-format=auto`，会按以下顺序判断：

1. 文件扩展名是否是 `.pdf`
2. 文件扩展名是否是 `.md/.markdown/.mdown`
3. 文件扩展名是否是 `.html/.htm`
4. 内容是否看起来像 HTML
5. 内容是否看起来像 Markdown
6. 否则按纯文本处理

## Step 3：提取标题

逻辑如下：

1. 如果传了 `--title`，直接使用
2. 否则如果是 Markdown，优先取第一条一级标题 `# 标题`
3. 否则如果是 PDF，优先取 PDF metadata 标题
4. 如果没有可用标题，则回退到文件名
5. 再不行才回退到正文第一条非空文本

## Step 4：生成摘要

如果没有显式传 `--digest`，脚本会从渲染后的 HTML 中提取前 120 个字符作为摘要。

## Step 5：选择模式

- `web`：走公众号后台真实页面自动化
- `api`：走微信接口
- `auto`：当前默认走 `web`

## Step 6：Web 模式自动操作公众号后台

Web 模式会：

- 打开公众号后台页面
- 判断是否已登录
- 若未登录，等待扫码
- 若已登录，直接进入编辑页
- 自动填写标题、作者、摘要、正文
- 若输入是 PDF，先提取文本再写入正文编辑区
- 尝试调用后台 AI 生封面
- 根据 `action` 选择保存草稿或直接发布

---

## 登录态复用说明

当前版本已经支持“第二次默认免扫码”。

原因是 Web 模式使用了 **持久化浏览器目录**。

默认逻辑：

- 第一次运行：打开浏览器并要求扫码登录
- 登录成功后，会话保存在持久化目录里
- 第二次运行：复用同一目录，通常可以直接进入后台

如果你想自己指定目录：

```bash
--user-data-dir "$HOME/.wechat-mp-profile"
```

如果不指定，脚本会使用默认持久化目录。

---

## Agent / Skill 的调用方式

如果你是在带 Agent 的环境里使用这个项目，推荐通过 Skill 间接调用。

Skill 文件：`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/SKILL.md:1`

它的职责是：

- 告诉 Agent 什么时候该调用这个能力
- 告诉 Agent 应该优先走 `web` 模式
- 告诉 Agent 对个人主体账号不要优先使用 API

也就是说：

- **Skill 决策**
- **CLI 执行**

---

## 给 Coco 使用的方法

## 1）直接在当前仓库内使用

如果你在这个仓库内运行 `coco`，它可以识别 `.trae/skills/` 下的 Skill。

你可以直接说：

```bash
coco "读取 /absolute/path/to/article.md，调用 wechat-mp-publish，把它保存到公众号草稿箱"
```

或者：

```bash
coco "读取 /absolute/path/to/article.md，调用 wechat-mp-publish，把它发布成公众号文章"
```

## 2）把 Skill 复制到别的项目

```bash
cp -R /Users/bytedance/code/skills/.trae/skills/wechat-mp-publish /path/to/your-project/.trae/skills/
```

然后进入目标项目运行 `coco` 即可。

## 3）Coco 的 MCP 能力

我已经实际确认 `coco` 支持：

- `coco mcp add-json`
- `coco mcp enable`
- `coco mcp disable`
- `coco mcp remove`

帮助入口：

- `coco -h`
- `coco mcp --help`
- `coco mcp add-json --help`

---

## 给 Coco 接入 `mcp-chrome`

如果你想让 Agent 未来直接接管“你已经打开的真实 Chrome”，而不是只用 Playwright 自己拉起浏览器，推荐额外接上 `mcp-chrome`。

## 步骤 1：安装 bridge

```bash
npm install -g mcp-chrome-bridge
```

## 步骤 2：安装扩展

- 打开 `chrome://extensions/`
- 开启开发者模式
- 从 `https://github.com/hangwin/mcp-chrome/releases` 下载扩展
- 选择“加载已解压的扩展程序”
- 点击扩展图标执行 `connect`

## 步骤 3：给 Coco 添加 MCP

```bash
coco mcp add-json chrome-mcp-server '{"type":"streamableHttp","url":"http://127.0.0.1:12306/mcp"}'
```

如果已存在但未启用：

```bash
coco mcp enable chrome-mcp-server
```

## 步骤 4：实际使用

```bash
coco "复用我当前 Chrome 登录态，把 /absolute/path/to/article.md 保存到公众号草稿箱"
```

这个接法的意义是：

- 可以直接复用你现在浏览器里的登录态
- 更贴近你真实使用的公众号后台页面
- 适合后续把当前 Web 自动化从 Playwright 进一步迁移到 `mcp-chrome`

---

## 给 AIME 使用的方法

当前机器上没有 `aime` 命令，所以我无法像 `coco` 一样实际验证本机 CLI 参数。

但就项目结构来看，**AIME 最稳的接法是直接调用本地 CLI**。

## 方案 1：把 CLI 注册成 AIME 的本地工具

保存草稿：

```bash
python3 /Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action draft \
  --content-file "$ARTICLE_MD"
```

直接发布：

```bash
python3 /Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action publish \
  --content-file "$ARTICLE_MD"
```

如果 AIME 支持变量替换，可以把 `$ARTICLE_MD` 替换为用户当前选中的 Markdown 文件路径。

## 方案 2：如果 AIME 支持 MCP

可复用与 Coco 相同的 `mcp-chrome` 配置：

```json
{
  "mcpServers": {
    "chrome-mcp-server": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:12306/mcp"
    }
  }
}
```

## 方案 3：如果 AIME 支持本地 Skill 目录

可尝试挂载目录：

`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish`

如果 AIME 不识别 `.trae/skills` 结构，也没关系，直接调用 CLI 仍然是最稳方案。

---

## 推荐的项目接入方式

如果目标是自己长期稳定使用，我推荐这样落地：

## Coco 侧

1. 保留 Skill 目录
2. 安装 Node 依赖
3. 给 Coco 配上 `mcp-chrome`
4. 平时让 Agent 直接读取 `.md` 文件并调用 Skill

## AIME 侧

1. 不强依赖 Skill 格式
2. 直接把 Python CLI 注册成一个本地工具
3. 只暴露少量参数：`md 路径`、`draft/publish`、`cover_prompt`

这样 Coco 和 AIME 都能共用同一套底层能力。

---

## 推荐给最终用户的话术

## 保存草稿

“把 `/absolute/path/to/article.md` 转成公众号文章并保存到草稿箱。”

“把 `/absolute/path/to/article.pdf` 转成公众号文章并保存到草稿箱。”

## 直接发布

“把 `/absolute/path/to/article.md` 转成公众号文章并直接发布。”

“把 `/absolute/path/to/article.pdf` 转成公众号文章并直接发布。”

## 指定 AI 封面风格

“把 `/absolute/path/to/article.md` 转成公众号文章，封面走 AI 生成，提示词是‘极简、科技、蓝白配色’，先保存到草稿箱。”

---

## 已知限制

- 个人主体账号不应优先使用微信开放接口发布
- 后台页面文案如果改版，自动化选择器可能需要更新
- “后台 AI 生成封面”属于页面能力，是否稳定命中依赖当前后台 UI
- 当前默认是 Playwright 持久化浏览器方案，不是直接接管已打开的真实 Chrome
- 如果想做到完全接管当前 Chrome，会更适合把这条链路切到 `mcp-chrome`
- 纯扫描图片 PDF 暂不支持，需先 OCR 成可提取文本的 PDF 或 Markdown

---

## 一句话总结

这个项目现在已经可以做到：**给 Agent 一篇 Markdown 或 PDF 文件，让它自动生成公众号文章，并保存为草稿或直接发布；个人主体账号默认走后台自动化，第二次默认免扫码。**
