---
name: "link-capture-md"
description: "抓取 URL（网页/X 帖子）并写入仓库为 Markdown（摘要 + 中文翻译版）。当用户要求抓取链接/帖子并生成 .md 文件时调用。"
---

# 链接抓取并落地 Markdown

## 目标

给定一个 URL，提取页面标题与主要可读内容，生成中文要点摘要，并将摘要 + 中文翻译版正文写入当前仓库中的 `.md` 文件。

如果当前客户端已接入 `mcp-chrome`，优先复用用户本机 Chrome 的现有会话与登录态抓取；只有在 `mcp-chrome` 不可用时，才回退到 `playwright-cli`。

## 何时调用

当用户提出以下诉求时调用：

- 抓取某个链接/帖子/网页内容
- 总结主要内容
- 把抓取结果落地为 `.md` 文件存到仓库里

## 入参

- `url`（必填）：需要抓取的链接
- `output_path`（可选）：输出 `.md` 文件的仓库相对路径
  - 默认：`captures/<host>-<title>-<YYYYMMDD-HHMMSS>.md`
- `summary_language`（可选）：默认 `zh-CN`
- `translation_language`（可选）：默认 `zh-CN`
- `include_translation`（可选）：默认 `true`
- `include_artifacts`（可选）：默认 `true`（如有可用的快照/控制台日志路径则一并写入）

## 工作流

### 1）浏览器抓取（优先 `mcp-chrome`，回退 `playwright-cli`）

优先级：

1. 若客户端已接入 `mcp-chrome`，优先复用用户当前 Chrome 标签页或登录态抓取内容。
2. 若 `mcp-chrome` 不可用，再使用 `playwright-cli` 打开目标页面并抽取可读内容。

#### 优先方案：`mcp-chrome`

适用场景：

- 页面需要登录后才能访问
- 用户明确要求“用当前 Chrome 页面”或“复用浏览器登录态”
- 需要读取当前标签页内容、截图或顺手抓取控制台 / 网络信息

抓取时优先读取：

- 当前页面标题
- 主要正文（优先 `article`，其次 `main`，最后 `document.body.innerText`）
- 当前 URL
- 如用户要求保留证据，可附带截图路径

执行要求：

- 优先复用当前活动标签页；如果给了 `url` 且当前标签不是目标页，再导航到目标页。
- 不做与抓取无关的点击。
- 不输出或持久化 token、cookie、账号密码等敏感信息。

#### 回退方案：`playwright-cli`

当 `mcp-chrome` 不可用时，使用 `playwright-cli`：

```bash
playwright-cli open "<URL>"
playwright-cli snapshot
playwright-cli eval "document.title"
playwright-cli eval "document.querySelector('article')?.innerText || document.querySelector('main')?.innerText || document.body.innerText"
playwright-cli close
```

注意事项：

- 非必要不要依赖持久化 profile，优先使用默认会话以减少沙箱限制问题。
- 若站点需要登录，优先建议切到 `mcp-chrome` 方案复用用户现有登录态；不要尝试绕过付费墙或认证。
- 不要在输出 Markdown 中打印或保存 token、cookie、账号密码等敏感信息。

### 2）生成摘要

- 生成 4–6 条中文要点，重点覆盖：
  - 宣布/主张了什么
  - 关键特性/变化
  - 取舍与限制
  - 如何体验/复现（命令、环境变量、链接）

### 3）生成中文翻译版正文

- 将抽取到的可读内容翻译为中文正文。
- 仅保留中文翻译版，不在输出 Markdown 中写入原文。
- 不要在输出 Markdown 中打印或保存 token、cookie、账号密码等敏感信息。

### 4）生成标题与文件名

- 根据“主要内容摘要”生成一个简短标题（建议 10–30 字），用于 `.md` 文件名。
- 标题应能概括页面核心信息，避免带时间、计数、纯口号。
- 文件名清洗规则：
  - 将空白字符替换为 `-`
  - 移除或替换不适合作为文件名的字符（例如 `/ \\ : * ? \" < > |`）
  - 连续的 `-` 合并为一个
  - 长度建议截断到约 60 字符
  - 若清洗后为空，则回退到从 URL 推导的 `<slug>`

### 5）写入仓库 Markdown 文件

生成 `.md` 文件，结构建议如下：

- 标题（优先用页面标题）
- 元信息：
  - URL
  - 抓取时间（本地）
  - 来源（host）
- 摘要要点
- 中文翻译版正文（如开启，使用 fenced code block 写入）
- 附件信息（如可用）：
  - `mcp-chrome` 或 `.playwright-cli/` 产出的截图 / Snapshot 路径
  - `.playwright-cli/` 下的 Console log 路径

模板：

```md
# <Title>

- URL: <url>
- Captured At: <YYYY-MM-DD HH:mm:ss>
- Source: <host>

## Summary

- ...

## Translation

```text
<translated text in zh-CN>
```

## Artifacts

- Snapshot: <path>
- Console: <path>
```

## 输出命名

如果未提供 `output_path`：

- 默认写入 `captures/` 目录。
- `<host>`：hostname 小写，`.` 替换为 `-`。
- `<title>`：根据“主要内容摘要”生成的标题，按“文件名清洗规则”处理后使用。
- 若 `<title>` 为空，则回退为 `<slug>`：从 URL path 推导，仅保留字母数字与 `-`，长度截断到约 60 字符。

## 执行原则

- 用户已在浏览器中打开页面时，优先复用现有 Chrome 会话，不重复开新浏览器。
- 读取类任务优先 `mcp-chrome`，无人机式冷启动抓取才回退 `playwright-cli`。
- 如网页正文明显依赖登录态、地域态或本地存储状态，优先使用 `mcp-chrome`，避免抓到访客视角内容。
- 如用户额外要求截图、网络日志或控制台报错，可与抓取流程一并完成，但输出仍以正文摘要为主。

## 示例

输入：

- `url=https://x.com/bcherny/status/2039421575422980329`

输出：

- `captures/x-com-终端-no-flicker-渲染器模式-20260402-031657.md`
