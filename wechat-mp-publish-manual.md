# 微信公众号发布 CLI / Skill 接入说明书

## 1. 当前到底是什么

当前实现不是“只有 Skill”或者“只有浏览器脚本”，而是 **`Skill + 本地 CLI` 的组合**：

- **Skill 定义**：`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/SKILL.md`
- **本地 CLI**：`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py`
- **后台自动化脚本**：`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/scripts/publish_wechat_mp_web.spec.js`

建议理解为：

- Agent 侧通过 Skill 决定“什么时候调用公众号发布能力”
- 真实执行入口是 Python CLI
- 个人主体公众号默认走后台浏览器自动化，不依赖官方发布 API

所以回答你的问题：**是的，我已经写了一个可直接调用的 CLI，同时也给它包了一层 Skill。**

---

## 2. 现在已经支持的能力

### 2.1 输入侧

- 直接指定一篇 `.md` 文件
- 自动识别 `markdown/html/text`
- 如果是 Markdown：自动转公众号可接受的 HTML
- 如果 Markdown 里有一级标题 `# 标题`：自动把它当文章标题
- 如果没传作者：默认作者是 `繁漪`

### 2.2 发布侧

- `web + draft`：打开公众号后台并保存到草稿箱
- `web + publish`：打开公众号后台并直接发表
- `api + publish`：仅对仍有接口权限的账号可用

### 2.3 登录态

- 浏览器自动化使用持久化目录保存登录态
- 第一次需要扫码登录公众号后台
- 第二次默认复用登录态，通常不需要再次扫码

---

## 3. 最推荐的使用方式

对于你的场景：**个人主体公众号**，推荐只用下面这一条链路：

`Markdown 文件 -> Python CLI -> 浏览器自动化 -> 公众号后台 -> 草稿 / 发表`

也就是说，真正推荐落地的是：

- 不走微信发布 API
- 不要求手工准备 `thumb_media_id`
- 优先尝试后台的 AI 生图入口生成封面

---

## 4. CLI 直接怎么用

先安装依赖：

```bash
cd /Users/bytedance/code/skills
npm install
```

### 4.1 保存到草稿箱

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action draft \
  --content-file "/absolute/path/to/article.md"
```

### 4.2 直接发表

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action publish \
  --content-file "/absolute/path/to/article.md"
```

### 4.3 指定封面提示词

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action draft \
  --content-file "/absolute/path/to/article.md" \
  --cover-prompt "极简科技感公众号封面，蓝白配色，带标题关键词"
```

### 4.4 手动指定登录态目录

```bash
python3 .trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action draft \
  --content-file "/absolute/path/to/article.md" \
  --user-data-dir "$HOME/.wechat-mp-profile"
```

说明：

- 不传 `--title` 时，会优先从 Markdown 第一条 `# 标题` 提取
- 不传 `--author` 时，默认作者为 `繁漪`
- `--action draft` 更适合日常使用，风险最低
- `--action publish` 会尝试直接点发布按钮，适合你已经确认内容没问题时使用

---

## 5. 给 Coco 配置的方法

## 5.1 Skill 怎么让 Coco 识别

如果你是直接在这个仓库里工作，`coco` 进入该仓库后就能看到 `.trae/skills/` 下的 Skill。

关键目录：

- Skill：`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/SKILL.md`
- 脚本：`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py`

如果你要把这个 Skill 用到别的项目里，最简单的方式是把整个目录复制过去：

```bash
cp -R /Users/bytedance/code/skills/.trae/skills/wechat-mp-publish /path/to/your-project/.trae/skills/
```

然后在目标项目里启动 `coco` 即可。

## 5.2 Coco 本身的 MCP 配置能力

我已经确认 `coco` 支持 MCP 管理：

- `coco mcp add-json`
- `coco mcp enable`
- `coco mcp disable`
- `coco mcp remove`

你可以先看帮助：

```bash
coco -h
coco mcp --help
coco mcp add-json --help
```

## 5.3 给 Coco 配 `mcp-chrome`

如果你希望 Coco 以后直接复用你当前打开的 Chrome，而不是让脚本自己拉起一个持久化浏览器，可以给 Coco 接 `mcp-chrome`。

### 步骤 1：安装 bridge

```bash
npm install -g mcp-chrome-bridge
```

### 步骤 2：安装浏览器扩展

- 打开 `chrome://extensions/`
- 开启开发者模式
- 从 `https://github.com/hangwin/mcp-chrome/releases` 下载扩展并“加载已解压的扩展程序”
- 点击扩展图标执行 `connect`

### 步骤 3：给 Coco 添加 MCP

```bash
coco mcp add-json chrome-mcp-server '{"type":"streamableHttp","url":"http://127.0.0.1:12306/mcp"}'
```

如果已经存在但被禁用，可执行：

```bash
coco mcp enable chrome-mcp-server
```

### 步骤 4：在 Coco 中这样用

进入你的项目目录后，直接提需求即可，例如：

```bash
coco "读取 /absolute/path/to/article.md，调用 wechat-mp-publish，把它保存到公众号草稿箱"
```

或者：

```bash
coco "复用我当前 Chrome 登录态，把 /absolute/path/to/article.md 发布成公众号文章，先检查标题和封面再执行"
```

## 5.4 Coco 下的推荐组合

最推荐的 Coco 组合是：

1. 项目里放 `.trae/skills/wechat-mp-publish`
2. 本机执行一次 `npm install`
3. 给 Coco 配上 `mcp-chrome`
4. 平时让 Agent 直接读取 `.md` 文件并调用 Skill

这样 Coco 既能识别 Skill，又能在需要时复用你当前浏览器登录态。

---

## 6. 给 AIME 配置的方法

### 6.1 先说结论

当前机器上 **没有 `aime` 命令**，所以我没法像 `coco` 一样直接跑 `aime -h` 去验证它的本地 CLI 参数。

因此下面给你的 AIME 说明，分成两类：

- **可以直接用的部分**：本地 CLI 命令本身
- **通用配置模板**：如果 AIME 支持 MCP / 自定义脚本 / 本地技能目录，就按下面接

### 6.2 最稳的接法：AIME 调本地 CLI

无论 AIME 的插件机制是什么，只要它支持“执行本地命令”，就可以把下面这条命令注册成工具：

保存草稿：

```bash
python3 /Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action draft \
  --content-file "$ARTICLE_MD"
```

直接发表：

```bash
python3 /Users/bytedance/code/skills/.trae/skills/wechat-mp-publish/scripts/publish_wechat_mp.py \
  --publish-mode web \
  --action publish \
  --content-file "$ARTICLE_MD"
```

这里的 `$ARTICLE_MD` 可以由 AIME 在运行时替换成用户选中的 Markdown 文件绝对路径。

### 6.3 如果 AIME 支持 MCP

如果 AIME 有 MCP 配置入口，可以直接复用和 Coco 一样的配置：

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

这样 AIME 侧也可以复用你当前 Chrome 的登录态。

### 6.4 如果 AIME 支持本地 Skills / Prompt Packs

如果 AIME 支持从本地目录加载技能，建议把下面这个目录挂进去：

`/Users/bytedance/code/skills/.trae/skills/wechat-mp-publish`

如果 AIME 不支持直接读 `.trae/skills` 结构，也可以只把它当“说明文件 + 命令模板”来用。

---

## 7. 推荐的实际接入方案

如果你是自己长期使用，我建议分两层：

### 方案 A：Coco 侧

- 把 Skill 留在 `.trae/skills/wechat-mp-publish`
- 配上 `mcp-chrome`
- 让 Coco 直接通过自然语言调用 Skill

### 方案 B：AIME 侧

- 不纠结 Skill 目录格式
- 直接把 Python CLI 注册成一个自定义命令工具
- 输入参数只保留：`md 文件路径`、`draft/publish`、`cover_prompt`

这样最稳定，因为 AIME 就算不理解 `.trae/skills`，也照样能调用 CLI。

---

## 8. 推荐给最终用户的使用口令

### 8.1 存草稿

“把 `/absolute/path/to/article.md` 转成公众号文章并保存到草稿箱。”

### 8.2 直接发表

“把 `/absolute/path/to/article.md` 转成公众号文章并直接发表。”

### 8.3 带封面提示词

“把 `/absolute/path/to/article.md` 转成公众号文章，封面走 AI 生成，提示词是‘极简、科技、蓝白配色’，先保存到草稿箱。”

---

## 9. 当前限制

- 个人主体账号不应再优先走微信发布 API
- 后台页面文案如果改版，浏览器自动化选择器可能需要调整
- “后台 AI 生成封面”是页面能力，能否稳定命中取决于当前后台 UI 是否保持一致
- 如果你要做到“100% 接管当前已打开的真实 Chrome”，下一步最适合把当前 Playwright web 流程改成 `mcp-chrome` 驱动

---

## 10. 一句话建议

**现在就能用的落地方式是：让 Coco / AIME 最终都调用这份 Python CLI；Coco 再额外接上 `mcp-chrome`，这样体验最好。**
