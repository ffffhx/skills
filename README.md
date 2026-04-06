# Skills 仓库

这是一个共享的 AI Agent Skills 仓库，收录可复用的工具技能，供多个 AI 客户端（Claude Code、Trae、Codex 等）共同使用。

## 目录结构

```
skills/                  ← 所有 skill 的唯一来源（Single Source of Truth）
  link-capture-md/       ← 抓取网页/X 帖子并生成 Markdown
  lark-doc-rw/           ← 飞书文档读写
  mcp-chrome/            ← 通过 mcp-chrome 接管本机 Chrome
  playwright-cli/        ← 浏览器自动化（Playwright）
  repo-source-analysis-md/ ← 读取仓库源码并生成解析文档
  wechat-mp-publish/     ← 微信公众号文章发布

.claude/skills/          ← 软链接 → skills/（供 Claude Code 使用）
.trae/skills/            ← 软链接 → skills/（供 Trae 使用）
.agents/skills/          ← 软链接 → skills/（供 Codex 等使用）

captures/                ← 由 link-capture-md skill 生成的网页/帖子抓取存档
```

> **注意**：`.claude/skills/`、`.trae/skills/`、`.agents/skills/` 均是指向 `skills/` 子目录的软链接，**不要直接修改这些目录下的文件**。

## 如何新增 Skill

1. 在 `skills/` 下新建目录，如 `skills/my-new-skill/`
2. 在其中创建 `SKILL.md`（参考已有 skill 的格式）
3. 提交 PR，三个工具目录的软链接会自动生效

## 如何更新 Skill

直接编辑 `skills/<skill-name>/SKILL.md`，所有工具目录立即生效（软链接）。

## 本地配置

`.claude/settings.local.json` 为本地个人配置，已被 `.gitignore` 忽略，**不要提交**。每个人可按需在本地配置自己的权限白名单。

## 依赖

```bash
npm install   # 安装 Playwright 等测试依赖
```
