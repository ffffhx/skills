---
name: "link-capture-md"
description: "抓取 URL（网页/X 帖子）并写入仓库为 Markdown（摘要 + 中文翻译版）。当用户要求抓取链接/帖子并生成 .md 文件时调用。"
---

# 链接抓取并落地 Markdown

## 目标

给定一个 URL，提取页面标题与主要可读内容，生成中文要点摘要，并将摘要 + 中文翻译版正文写入当前仓库中的 `.md` 文件。

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

### 1）浏览器自动化抓取（Playwright CLI）

使用 `playwright-cli` 加载页面并抽取可读内容。

推荐命令序列：

```bash
playwright-cli open "<URL>"
playwright-cli snapshot
playwright-cli eval "document.title"
playwright-cli eval "document.querySelector('article')?.innerText || document.querySelector('main')?.innerText || document.body.innerText"
playwright-cli close
```

注意事项：

- 非必要不要依赖持久化 profile，优先使用默认会话以减少沙箱限制问题。
- 若站点需要登录，只抓取无需凭证也能访问的内容，不尝试绕过付费墙或认证。
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
  - `.playwright-cli/` 下的 Snapshot 路径
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

## 示例

输入：

- `url=https://x.com/bcherny/status/2039421575422980329`

输出：

- `captures/x-com-终端-no-flicker-渲染器模式-20260402-031657.md`
