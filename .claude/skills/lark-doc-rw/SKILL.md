---
name: lark-doc-rw
description: "飞书文档读写工具：读取、创建、更新飞书云文档（支持 wiki 链接自动解析）。当用户要求读取/写入/编辑飞书文档、操作飞书知识库文档时使用。"
---

# 飞书文档读写工具 (lark-doc-rw)

统一封装飞书云文档的**读取**和**写入**操作，支持直接传入 URL 或 token，自动处理 Wiki 链接解析。

## 前置条件

首次使用前需确保 `lark-cli` 已完成认证配置：
- Bot 身份：只需 appId + appSecret
- User 身份：需执行 `lark-cli auth login --scope "wiki:node:read docx:document:readonly docx:document:write"`

## 核心流程

### 1. 读取文档

#### 支持的输入格式

| 格式 | 示例 | 说明 |
|------|------|------|
| Wiki URL | `https://xxx.feishu.cn/wiki/LwxPwE80IixXDQkkTEqcK2o9ntc` | 知识库链接 |
| Docx URL | `https://xxx.feishu.cn/docx/LQUzdQ7YPoHn2sxdsV0cjBSCnzb` | 文档直链 |
| Token | `LQUzdQ7YPoHn2sxdsV0cjBSCnzb` | 直接传 token |

#### 读取命令

```bash
# 读取文档（自动识别 URL 类型）
lark-cli docs +fetch --doc "<URL或token>"

# 人类可读格式
lark-cli docs +fetch --doc "<URL或token>" --format pretty
```

#### Wiki 链接自动解析

当输入为 `/wiki/` 链接时，内部自动执行：
1. 调用 `wiki.spaces.get_node` 解析节点信息
2. 提取 `obj_type` 和 `obj_token`
3. 根据 `obj_type` 调用对应 API

支持的文档类型：
- `docx` → 云文档 ✅
- `sheet` → 电子表格 ⚠️ 需切换到 lark-sheets
- `bitable` → 多维表格 ⚠️ 需切换到 lark-base

### 2. 创建文档

```bash
# 创建简单文档
lark-cli docs +create --title "文档标题" --markdown "# 内容"

# 创建到指定文件夹
lark-cli docs +create --title "文档标题" --folder-token fldcnXXXX --markdown "内容"

# 创建到知识库节点下
lark-cli docs +create --title "文档标题" --wiki-node wikcnXXXX --markdown "内容"
```

### 3. 更新文档

#### 追加内容（推荐）

```bash
lark-cli docs +update --doc "<doc_id>" --mode append --markdown "## 新章节\n\n内容"
```

#### 定位替换

```bash
# 按内容范围定位替换
lark-cli docs +update --doc "<doc_id>" --mode replace_range \
  --selection-with-ellipsis "旧开头...旧结尾" --markdown "新内容"

# 按标题定位替换整个章节
lark-cli docs +update --doc "<doc_id>" --mode replace_range \
  --selection-by-title "## 章节名" --markdown "## 章节名\n\n新内容"
```

#### 其他模式

| 模式 | 用途 | 关键参数 |
|------|------|---------|
| `insert_before` | 在目标位置前插入 | `--selection-with-ellipsis` 或 `--selection-by-title` |
| `insert_after` | 在目标位置后插入 | 同上 |
| `replace_all` | 全文替换所有匹配 | `--selection-with-ellipsis` |
| `delete_range` | 删除指定内容 | 不需要 `--markdown` |
| `overwrite` | 完全覆盖重写 | ⚠️ 会丢失图片、评论等 |

### 4. 搜索文档

```bash
lark-cli docs +search --query "关键词"
```

---

## 使用示例

### 示例 1：读取 Wiki 文档并展示内容

用户：`帮我读一下 https://bytedance.larkoffice.com/wiki/LwxPwE80IixXDQkkTEqcK2o9ntc`

执行：
```bash
lark-cli docs +fetch --doc "https://bytedance.larkoffice.com/wiki/LwxPwE80IixXDQkkTEqcK2o9ntc" --format pretty
```

### 示例 2：创建文档并追加内容

用户：`帮我创建一个项目计划文档`

执行：
```bash
lark-cli docs +create --title "项目计划" --markdown "## 项目概述\n\n这是一个新项目。"

# 获取返回的 doc_id 后继续追加
lark-cli docs +update --doc "<doc_id>" --mode append --markdown "\n## 目标\n\n- 目标 1\n- 目标 2"
```

### 示例 3：修改文档特定章节

用户：`把文档 xxx 的「功能说明」章节改成新的内容`

执行：
```bash
lark-cli docs +update --doc "<doc_id>" --mode replace_range \
  --selection-by-title "功能说明" --markdown "## 功能说明\n\n更新后的内容..."
```

---

## 注意事项

### 写入安全原则

1. **优先局部更新**：使用 `append` / `replace_range` / `insert_before` / `insert_after`
2. **慎用 overwrite**：会清空整个文档，可能丢失图片、评论等不可恢复内容
3. **精确定位**：`--selection-with-ellipsis` 范围越大越唯一，避免误改
4. **保护媒体内容**：图片、画板以 token 形式存储，无法读出后原样写入

### Markdown 格式

支持 Lark-flavored Markdown 扩展语法：

```html
<!-- 高亮块 -->
<callout emoji="💡" background-color="light-blue">提示内容</callout>

<!-- 分栏 -->
<grid cols="2">
<column>左栏</column>
<column>右栏</column>
</grid>

<!-- 表格 -->
<lark-table column-widths="200,250" header-row="true">
<lark-tr><lark-td>列1</lark-td><lark-td>列2</lark-td></lark-tr>
</lark-table>

<!-- 图片 -->
<image url="https://example.com/img.png" width="800" height="600"/>
```

### 图片与文件处理

- **读取**：图片以 `<image token="xxx"/>` 形式出现，需用 `docs +media-download` 单独下载
- **写入**：使用 `<image url="..."/>` 系统自动下载上传；本地文件用 `docs +media-insert`

---

## 错误处理

### 权限不足

```
permission_violations: ["wiki:node:read"]
```

解决方案：
- Bot 身份：去飞书开发者后台开通对应 scope
- User 身份：执行 `lark-cli auth login --scope "缺失的scope"`

### Wiki 类型不支持

当 `obj_type` 为 `sheet` 或 `bitable` 时，告知用户需切换到对应 skill：
- `sheet` → `lark-sheets`
- `bitable` → `lark-base`

---

## 快速参考

| 操作 | 命令 |
|------|------|
| 读取 | `lark-cli docs +fetch --doc <URL>` |
| 创建 | `lark-cli docs +create --title "标题" --markdown "内容"` |
| 追加 | `lark-cli docs +update --doc <id> --mode append --markdown "内容"` |
| 替换 | `lark-cli docs +update --doc <id> --mode replace_range --selection-by-title "标题" --markdown "新内容"` |
| 删除 | `lark-cli docs +update --doc <id> --mode delete_range --selection-by-title "标题"` |
| 搜索 | `lark-cli docs +search --query "关键词"` |
