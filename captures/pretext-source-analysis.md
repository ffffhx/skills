# Pretext 源码解析（@chenglou/pretext）

## 摘要

Pretext 是一个纯 JavaScript/TypeScript 的“多行文本测量与排版”库：在不触碰 DOM 布局测量（例如 `getBoundingClientRect`、`offsetHeight`）的前提下，给定文本、字体与容器宽度，计算文本会被换成多少行、整体高度是多少，并可选返回逐行文本与几何信息。它的目标是把“浏览器字体引擎的真实测量结果”转化为可缓存的数据结构，避免 DOM reflow 带来的性能成本，从而更稳定地支撑列表虚拟化、避免布局抖动、以及 Canvas/SVG 等自绘场景。

它主要提供两类用法：
- 高性能高度测量：`prepare()` 做一次性预处理（空白归一化、分段、应用 glue 规则、Canvas 测量与缓存），`layout()` 在 resize 等热路径只做纯算术计算高度与行数。
- 手动绘制/自定义排版：用 `prepareWithSegments()` + `layoutWithLines()` / `walkLineRanges()` / `layoutNextLine()` 获取逐行文本与游标范围，便于渲染到 Canvas/SVG/WebGL，并支持“每行宽度动态变化”的绕排等高级布局。

仓库地址：https://github.com/chenglou/pretext

本文基于仓库源码做“从入口到实现”的结构化导读，重点覆盖：
- 两阶段模型：`prepare()`（一次性分析+测量）与 `layout()`（纯算术热路径）
- 核心模块：文本分析/Canvas 测量/换行引擎/富文本行物化/Bidi 元数据
- 与浏览器行为对齐的关键细节：emoji 修正、Safari/Chromium 差异、`pre-wrap` 硬换行 chunk 等

## 1. 目录与模块分层

**库核心（发布到 dist）**
- layout.ts：公共 API（`prepare/layout/layoutWithLines/walkLineRanges/layoutNextLine/clearCache/setLocale`）与装配逻辑
- analysis.ts：文本归一化、分段、合并规则（URL/数字/标点粘连/glue/`pre-wrap` chunk）
- measurement.ts：Canvas 测量、按字体缓存、emoji 宽度修正、引擎画像（Safari/Chromium 差异）
- line-break.ts：换行引擎（fast-path 与完整路径），处理 break-word、soft hyphen、tab、`pre-wrap` chunk
- bidi.ts：富路径（rich path）用的简化 bidi embedding level 计算（fork 自 pdf.js 思路）

**演示与验证（不影响库 API，但影响稳定性/准确性保障）**
- `pages/`：demo 页面与 accuracy/benchmark/corpus/probe 等工具页面
- `scripts/`：自动化跑浏览器对照（accuracy/benchmark/corpus sweep）的脚本
- DEVELOPMENT.md：开发命令与“当前事实来源”

## 2. 对外 API 与调用链

API 在 README.md 与 src/layout.ts 中对应实现，核心是两阶段：

### 2.1 `prepare(text, font, options?) -> PreparedText`

入口：`prepare`

内部调用链：
1. prepareInternal  
2. analyzeText：文本归一化 + Intl.Segmenter 分段 + 合并规则 + `pre-wrap` chunk 编译  
3. measureAnalysis：基于 Canvas 的分段测量、CJK 细分、break-word 的 grapheme 宽度预计算、（可选）bidi segment level 计算

代码摘录（src/layout.ts:L424-L480）：

```ts
function prepareInternal(
  text: string,
  font: string,
  includeSegments: boolean,
  options?: PrepareOptions,
): InternalPreparedText | PreparedTextWithSegments {
  const analysis = analyzeText(text, getEngineProfile(), options?.whiteSpace)
  return measureAnalysis(analysis, font, includeSegments)
}

export function prepare(text: string, font: string, options?: PrepareOptions): PreparedText {
  return prepareInternal(text, font, false, options) as PreparedText
}

export function prepareWithSegments(text: string, font: string, options?: PrepareOptions): PreparedTextWithSegments {
  return prepareInternal(text, font, true, options) as PreparedTextWithSegments
}
```

### 2.2 `layout(prepared, maxWidth, lineHeight) -> { lineCount, height }`

入口：`layout`

核心特征：
- 只做“纯算术”，不做 Canvas 测量、不做 DOM 读写、不做字符串拼接
- 通过 `countPreparedLines` 计算行数，然后 `height = lineCount * lineHeight`

代码摘录（src/layout.ts:L495-L501）：

```ts
export function layout(prepared: PreparedText, maxWidth: number, lineHeight: number): LayoutResult {
  const lineCount = countPreparedLines(getInternalPrepared(prepared), maxWidth)
  return { lineCount, height: lineCount * lineHeight }
}
```

### 2.3 富路径（自绘/自定义布局）API

这些 API 需要 `prepareWithSegments`（保留 `segments[]` 结构）：
- `prepareWithSegments`
- `layoutWithLines`：返回每行 `{ text, width, start, end }`
- `walkLineRanges`：只给几何信息（宽度 + cursor），避免构造 line text
- `layoutNextLine`：按行迭代（每行可使用不同的宽度，用于绕排/float 等）

## 3. 数据模型：为什么是并行数组

Pretext 的 `PreparedText` 是刻意保持“外部不透明”的句柄（避免 API 绑定内部表示），见下方摘录中的 PreparedText brand。

内部核心结构是 `PreparedCore` 并行数组（性能友好）：
- `widths[]`：每个 segment 的基础宽度  
- `kinds[]`：break kind（`text/space/tab/soft-hyphen/...`）  
- `lineEndFitAdvances[] / lineEndPaintAdvances[]`：用于“行尾判定 vs 实际绘制宽度”的差异（完整换行路径用）  
- `breakableWidths[] / breakablePrefixWidths[]`：用于 break-word 时按 grapheme 断开  
- `discretionaryHyphenWidth`：软连字符被选作断点时额外加的 `-` 宽度  
- `tabStopAdvance`：`pre-wrap` 下 tab 的对齐步长（默认 8 个空格）  
- `chunks[]`：`pre-wrap` 下硬换行编译成的分块范围（换行引擎按 chunk 逐块走）

见下方 `PreparedCore` 摘录。

代码摘录（src/layout.ts:L81-L109）：

```ts
declare const preparedTextBrand: unique symbol

type PreparedCore = {
  widths: number[]
  lineEndFitAdvances: number[]
  lineEndPaintAdvances: number[]
  kinds: SegmentBreakKind[]
  simpleLineWalkFastPath: boolean
  segLevels: Int8Array | null
  breakableWidths: (number[] | null)[]
  breakablePrefixWidths: (number[] | null)[]
  discretionaryHyphenWidth: number
  tabStopAdvance: number
  chunks: PreparedLineChunk[]
}

export type PreparedText = {
  readonly [preparedTextBrand]: true
}

export type PreparedTextWithSegments = InternalPreparedText & {
  segments: string[]
}
```

## 4. Phase 1：文本分析（analysis.ts）

这一阶段的目标是把“原始文本”转成更贴近 CSS 换行语义的“分段流”，并记录每段在原文中的起始位置（用于 rich path 的 cursor、bidi 等）。

### 4.1 空白归一化：`normal` vs `pre-wrap`

入口：`analyzeText`

- `whiteSpace: 'normal'`：折叠空白（`[ \t\n\r\f]+` -> `' '`），并去掉首尾空格  
  - normalizeWhitespaceNormal
- `whiteSpace: 'pre-wrap'`：保留普通空格，保留硬换行；把 `\r\n`、`\r`、`\f` 统一成 `\n`  
  - normalizeWhitespacePreWrap

代码摘录（src/analysis.ts:L56-L74）：

```ts
export function normalizeWhitespaceNormal(text: string): string {
  if (!needsWhitespaceNormalizationRe.test(text)) return text

  let normalized = text.replace(collapsibleWhitespaceRunRe, ' ')
  if (normalized.charCodeAt(0) === 0x20) {
    normalized = normalized.slice(1)
  }
  if (normalized.length > 0 && normalized.charCodeAt(normalized.length - 1) === 0x20) {
    normalized = normalized.slice(0, -1)
  }
  return normalized
}

function normalizeWhitespacePreWrap(text: string): string {
  if (!/[\r\f]/.test(text)) return text.replace(/\r\n/g, '\n')
  return text
    .replace(/\r\n/g, '\n')
    .replace(/[\r\f]/g, '\n')
}
```

### 4.2 分段：Intl.Segmenter(word) + 二次切分（break kind）

主流程在 `buildMergedSegmentation`：
- 复用 `Intl.Segmenter(..., { granularity: 'word' })`（见 `getSharedWordSegmenter`/`setAnalysisLocale`）
- 对每个 word segment 再按字符切分 break kind：  
  - 分类函数 `classifySegmentBreakChar`  
  - 切分函数 `splitSegmentByBreakKind`

代码摘录（src/analysis.ts:L321-L389）：

```ts
function classifySegmentBreakChar(ch: string, whiteSpaceProfile: WhiteSpaceProfile): SegmentBreakKind {
  if (whiteSpaceProfile.preserveOrdinarySpaces || whiteSpaceProfile.preserveHardBreaks) {
    if (ch === ' ') return 'preserved-space'
    if (ch === '\t') return 'tab'
    if (whiteSpaceProfile.preserveHardBreaks && ch === '\n') return 'hard-break'
  }
  if (ch === ' ') return 'space'
  if (ch === '\u00A0' || ch === '\u202F' || ch === '\u2060' || ch === '\uFEFF') {
    return 'glue'
  }
  if (ch === '\u200B') return 'zero-width-break'
  if (ch === '\u00AD') return 'soft-hyphen'
  return 'text'
}

function splitSegmentByBreakKind(
  segment: string,
  isWordLike: boolean,
  start: number,
  whiteSpaceProfile: WhiteSpaceProfile,
): SegmentationPiece[] {
  const pieces: SegmentationPiece[] = []
  let currentKind: SegmentBreakKind | null = null
  let currentTextParts: string[] = []
  let currentStart = start
  let currentWordLike = false
  let offset = 0

  for (const ch of segment) {
    const kind = classifySegmentBreakChar(ch, whiteSpaceProfile)
    const wordLike = kind === 'text' && isWordLike

    if (currentKind !== null && kind === currentKind && wordLike === currentWordLike) {
      currentTextParts.push(ch)
      offset += ch.length
      continue
    }

    if (currentKind !== null) {
      pieces.push({
        text: joinTextParts(currentTextParts),
        isWordLike: currentWordLike,
        kind: currentKind,
        start: currentStart,
      })
    }

    currentKind = kind
    currentTextParts = [ch]
    currentStart = start + offset
    currentWordLike = wordLike
    offset += ch.length
  }

  if (currentKind !== null) {
    pieces.push({
      text: joinTextParts(currentTextParts),
      isWordLike: currentWordLike,
      kind: currentKind,
      start: currentStart,
    })
  }

  return pieces
}
```

break kind 覆盖了：
- 普通空格与保留空格：`space` vs `preserved-space`
- tab：`tab`
- 不可断空白（NBSP 等）：`glue`
- 零宽断点：`zero-width-break`
- 软连字符：`soft-hyphen`
- 硬换行（`pre-wrap`）：`hard-break`

### 4.3 合并规则：让测量/换行更像 CSS

这一部分是 Pretext “像浏览器”的关键，主要在 `buildMergedSegmentation` 的多个 pass 中实现：

- URL 合并：`mergeUrlLikeRuns` / `mergeUrlQueryRuns`
- 数字合并与特殊拆分：`mergeNumericRuns` / `splitHyphenatedNumericRuns`
- ASCII 标点链：`mergeAsciiPunctuationChains`
- 不可断空白 glue：`mergeGlueConnectedTextRuns`
- 标点粘连：`leftStickyPunctuation` 等规则驱动的合并

此外还有多语言特例处理（CJK 禁则、阿拉伯标点、缅文 glue 等），都体现在 `buildMergedSegmentation` 的条件分支里。

### 4.4 `pre-wrap`：硬换行 chunk 编译

当 `whiteSpace='pre-wrap'` 时，分析阶段把 `hard-break` 切成 chunk，供换行引擎逐块消费（`compileAnalysisChunks`）。

chunk 的三个字段语义很重要：
- `startSegmentIndex`：该块开始（包含）
- `endSegmentIndex`：该块内容结束（不含 `hard-break`）
- `consumedEndSegmentIndex`：该块结束后实际消费位置（包含 `hard-break` 本身）

代码摘录（src/analysis.ts:L958-L991）：

```ts
function compileAnalysisChunks(segmentation: MergedSegmentation, whiteSpaceProfile: WhiteSpaceProfile): AnalysisChunk[] {
  if (segmentation.len === 0) return []
  if (!whiteSpaceProfile.preserveHardBreaks) {
    return [{
      startSegmentIndex: 0,
      endSegmentIndex: segmentation.len,
      consumedEndSegmentIndex: segmentation.len,
    }]
  }

  const chunks: AnalysisChunk[] = []
  let startSegmentIndex = 0

  for (let i = 0; i < segmentation.len; i++) {
    if (segmentation.kinds[i] !== 'hard-break') continue

    chunks.push({
      startSegmentIndex,
      endSegmentIndex: i,
      consumedEndSegmentIndex: i + 1,
    })
    startSegmentIndex = i + 1
  }

  if (startSegmentIndex < segmentation.len) {
    chunks.push({
      startSegmentIndex,
      endSegmentIndex: segmentation.len,
      consumedEndSegmentIndex: segmentation.len,
    })
  }

  return chunks
}
```

## 5. Phase 2：Canvas 测量与缓存（measurement.ts + layout.ts）

### 5.1 测量上下文：OffscreenCanvas 优先

测量上下文单例化：`getMeasureContext`

策略：
- 有 `OffscreenCanvas` 用 OffscreenCanvas
- 否则用 DOM `canvas`
- 都不可用直接抛错（意味着“纯服务端无 Canvas 环境”目前不支持直接测量）

代码摘录（src/measurement.ts:L27-L41）：

```ts
export function getMeasureContext(): CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D {
  if (measureContext !== null) return measureContext

  if (typeof OffscreenCanvas !== 'undefined') {
    measureContext = new OffscreenCanvas(1, 1).getContext('2d')!
    return measureContext
  }

  if (typeof document !== 'undefined') {
    measureContext = document.createElement('canvas').getContext('2d')!
    return measureContext
  }

  throw new Error('Text measurement requires OffscreenCanvas or a DOM canvas context.')
}
```

### 5.2 按字体缓存 SegmentMetrics

缓存模型：`font -> (segmentText -> SegmentMetrics)`；对应实现：`segmentMetricCaches`、`getSegmentMetricCache`、`getSegmentMetrics`。

`SegmentMetrics` 除了 `width` 之外，还会懒计算：
- 是否包含 CJK（触发后续 CJK 细分）  
- emoji grapheme 计数（用于修正）  
- graphemeWidths / graphemePrefixWidths（用于 break-word）

### 5.3 emoji 宽度修正：用 DOM 校准 Canvas 偏差

核心函数：`getEmojiCorrection`

要点：
- 只在“文本可能含 emoji”时才做一次性校准（`textMayContainEmoji`）
- 校准方式：用 😀 测 `canvasW`，若 `canvasW` 明显大于 `DOM span` 的 `domW`，则记录 `correction = canvasW - domW`
- correction 按字体字符串缓存：`emojiCorrectionCache`
- 使用时按“emoji grapheme 个数”做扣减：  
  - 计数：`countEmojiGraphemes`  
  - 应用：`getCorrectedSegmentWidth`

代码摘录（src/measurement.ts:L123-L172）：

```ts
function getEmojiCorrection(font: string, fontSize: number): number {
  let correction = emojiCorrectionCache.get(font)
  if (correction !== undefined) return correction

  const ctx = getMeasureContext()
  ctx.font = font
  const canvasW = ctx.measureText('\u{1F600}').width
  correction = 0
  if (
    canvasW > fontSize + 0.5 &&
    typeof document !== 'undefined' &&
    document.body !== null
  ) {
    const span = document.createElement('span')
    span.style.font = font
    span.style.display = 'inline-block'
    span.style.visibility = 'hidden'
    span.style.position = 'absolute'
    span.textContent = '\u{1F600}'
    document.body.appendChild(span)
    const domW = span.getBoundingClientRect().width
    document.body.removeChild(span)
    if (canvasW - domW > 0.5) {
      correction = canvasW - domW
    }
  }
  emojiCorrectionCache.set(font, correction)
  return correction
}

export function getCorrectedSegmentWidth(seg: string, metrics: SegmentMetrics, emojiCorrection: number): number {
  if (emojiCorrection === 0) return metrics.width
  return metrics.width - getEmojiCount(seg, metrics) * emojiCorrection
}
```

### 5.4 EngineProfile：Safari/Chromium 差异参数

Pretext 把部分浏览器差异显式建模为 `EngineProfile`（`getEngineProfile`）：

其中影响换行最直接的参数：
- `lineFitEpsilon`：控制“容差”，用于缓解浮点测量误差；Safari 用更大的 `1/64`
- `preferPrefixWidthsForBreakableRuns`：Safari 倾向用“前缀累计宽”而不是“单字宽累加”来定位 grapheme 断点（见 6.2）
- `preferEarlySoftHyphenBreak`：Safari 更倾向在 soft hyphen 处提前断行（见 6.3）
- `carryCJKAfterClosingQuote`：Chromium 特例，影响分析阶段的 CJK 合并（见 4.3 与 layout.ts 中的 CJK 合并条件）

代码摘录（src/measurement.ts:L65-L101）：

```ts
export function getEngineProfile(): EngineProfile {
  if (cachedEngineProfile !== null) return cachedEngineProfile

  if (typeof navigator === 'undefined') {
    cachedEngineProfile = {
      lineFitEpsilon: 0.005,
      carryCJKAfterClosingQuote: false,
      preferPrefixWidthsForBreakableRuns: false,
      preferEarlySoftHyphenBreak: false,
    }
    return cachedEngineProfile
  }

  const ua = navigator.userAgent
  const vendor = navigator.vendor
  const isSafari =
    vendor === 'Apple Computer, Inc.' &&
    ua.includes('Safari/') &&
    !ua.includes('Chrome/') &&
    !ua.includes('Chromium/') &&
    !ua.includes('CriOS/') &&
    !ua.includes('FxiOS/') &&
    !ua.includes('EdgiOS/')
  const isChromium =
    ua.includes('Chrome/') ||
    ua.includes('Chromium/') ||
    ua.includes('CriOS/') ||
    ua.includes('Edg/')

  cachedEngineProfile = {
    lineFitEpsilon: isSafari ? 1 / 64 : 0.005,
    carryCJKAfterClosingQuote: isChromium,
    preferPrefixWidthsForBreakableRuns: isSafari,
    preferEarlySoftHyphenBreak: isSafari,
  }
  return cachedEngineProfile
}
```

## 6. 换行引擎（line-break.ts）

换行引擎是“布局热路径”的核心。它消费 `PreparedLineBreakData`（layout.ts 的 PreparedCore 子集），输出行数或逐行范围。

### 6.1 两条实现路径：fast-path 与完整路径

入口：`countPreparedLines`、`walkPreparedLines`

- fast-path：`walkPreparedLinesSimple`
  - 假设段类型更“简单”，不处理 chunk/tab/preserved-space/soft-hyphen 等复杂分支
  - 仍支持 break-word（逐 grapheme）
- 完整路径：`walkPreparedLines`
  - 支持 `pre-wrap` chunk、tab stop、soft hyphen、fit/paint 双宽度

fast-path 是否启用由 prepare 阶段决定：在测量阶段遇到非 `text/space/zero-width-break` 的 kind 会关闭 fast-path（pushMeasuredSegment 分支）。

### 6.2 break-word（按 grapheme 断开）

当某个 segment “像一个词（wordLike）且较长”时，prepare 会预计算 grapheme 宽度数组（layout.ts 里生成 `breakableWidths`）：
- 宽度来源：
  - 单 grapheme 宽：`getSegmentGraphemeWidths`
  - 前缀宽：`getSegmentGraphemePrefixWidths`（Safari 偏好）

代码摘录（src/layout.ts:L321-L357）：

```ts
const w = getCorrectedSegmentWidth(segText, segMetrics, emojiCorrection)
const lineEndFitAdvance =
  segKind === 'space' || segKind === 'preserved-space' || segKind === 'zero-width-break'
    ? 0
    : w
const lineEndPaintAdvance =
  segKind === 'space' || segKind === 'zero-width-break'
    ? 0
    : w

if (segWordLike && segText.length > 1) {
  const graphemeWidths = getSegmentGraphemeWidths(segText, segMetrics, cache, emojiCorrection)
  const graphemePrefixWidths = engineProfile.preferPrefixWidthsForBreakableRuns
    ? getSegmentGraphemePrefixWidths(segText, segMetrics, cache, emojiCorrection)
    : null
  pushMeasuredSegment(
    segText,
    w,
    lineEndFitAdvance,
    lineEndPaintAdvance,
    segKind,
    segStart,
    graphemeWidths,
    graphemePrefixWidths,
  )
} else {
  pushMeasuredSegment(
    segText,
    w,
    lineEndFitAdvance,
    lineEndPaintAdvance,
    segKind,
    segStart,
    null,
    null,
  )
}
```

换行时如果一个段 `w > maxWidth` 且 `breakableWidths[i] != null`，会进入逐 grapheme 填充逻辑：
- simple 路径：`appendBreakableSegmentFrom`
- 完整路径：`appendBreakableSegmentFrom`

代码摘录（src/line-break.ts:L457-L475）：

```ts
function appendBreakableSegmentFrom(segmentIndex: number, startGraphemeIndex: number): void {
  const gWidths = breakableWidths[segmentIndex]!
  const gPrefixWidths = breakablePrefixWidths[segmentIndex] ?? null
  for (let g = startGraphemeIndex; g < gWidths.length; g++) {
    const gw = getBreakableAdvance(
      gWidths,
      gPrefixWidths,
      g,
      engineProfile.preferPrefixWidthsForBreakableRuns,
    )

    if (!hasContent) {
      startLineAtGrapheme(segmentIndex, g, gw)
      continue
    }

    if (lineW + gw > maxWidth + lineFitEpsilon) {
      emitCurrentLine()
      startLineAtGrapheme(segmentIndex, g, gw)
    } else {
      lineW += gw
      lineEndSegmentIndex = segmentIndex
      lineEndGraphemeIndex = g + 1
    }
  }
}
```

Safari 的 “prefix widths” 偏好通过 `getBreakableAdvance` 落地：用前缀数组反推当前 grapheme 的增量，减少累加误差导致的断点漂移。

### 6.3 soft hyphen：断行才显示 `-`

prepare 对 `soft-hyphen` 的测量：段自身宽度为 0，但 `discretionaryHyphenWidth` 会用于行尾显示（见下方摘录）。

代码摘录（src/layout.ts:L250-L260）：

```ts
if (segKind === 'soft-hyphen') {
  pushMeasuredSegment(
    segText,
    0,
    discretionaryHyphenWidth,
    discretionaryHyphenWidth,
    segKind,
    segStart,
    null,
    null,
  )
  preparedEndByAnalysisIndex[mi] = widths.length
  continue
}
```

完整路径在遍历时遇到 `soft-hyphen`：
- 不直接占宽度，但设置 pending break，并把 `pendingBreakFitWidth/paintWidth` 设为 `lineW + discretionaryHyphenWidth`：  
  在 `walkPreparedLines` 的 soft-hyphen 分支中处理
- 溢出时会根据 `preferEarlySoftHyphenBreak` 与后续段可 break-word 情况，选择更接近浏览器的断行策略：  
  - `preferEarlySoftHyphenBreak` 的早断策略
  - soft hyphen 与 break-word 结合的填充逻辑：`continueSoftHyphenBreakableSegment`

### 6.4 fit vs paint：为什么要双宽度

完整路径维护两套宽度：
- **fit width**：用于判断“这行是否装得下”（某些行尾字符不该参与 fit）
- **paint width**：用于对外上报/绘制（例如保留空格、tab 的可视宽度）

更新 pending break 的逻辑在 `updatePendingBreakForWholeSegment`：

代码摘录（src/line-break.ts:L443-L451）：

```ts
function updatePendingBreakForWholeSegment(segmentIndex: number, segmentWidth: number): void {
  if (!canBreakAfter(kinds[segmentIndex]!)) return
  const fitAdvance = kinds[segmentIndex] === 'tab' ? 0 : lineEndFitAdvances[segmentIndex]!
  const paintAdvance = kinds[segmentIndex] === 'tab' ? segmentWidth : lineEndPaintAdvances[segmentIndex]!
  pendingBreakSegmentIndex = segmentIndex + 1
  pendingBreakFitWidth = lineW - segmentWidth + fitAdvance
  pendingBreakPaintWidth = lineW - segmentWidth + paintAdvance
  pendingBreakKind = kinds[segmentIndex]!
}
```

其中 `preserved-space` 的典型语义是：“不参与行尾 fit，但参与 paint”，对应 prepare 阶段的：
- `lineEndFitAdvance = 0`，但 `lineEndPaintAdvance = w`：  
  参见 layout.ts 中 fit/paint advance 的计算

这也是 `pre-wrap` 能更像 `<textarea>` 的关键支撑之一。

### 6.5 `pre-wrap` chunk：硬换行的消费方式

完整路径按 chunk 逐块处理（每个 chunk 是一个“硬换行分段”）：
- chunk 遍历入口：`walkPreparedLines` 中的 chunk 循环
- 空 chunk（连续硬换行）会 emit 一条宽度 0 的 line：`emitEmptyChunk`

代码摘录（src/line-break.ts:L539-L606）：

```ts
for (let chunkIndex = 0; chunkIndex < chunks.length; chunkIndex++) {
  const chunk = chunks[chunkIndex]!
  if (chunk.startSegmentIndex === chunk.endSegmentIndex) {
    emitEmptyChunk(chunk)
    continue
  }

  hasContent = false
  lineW = 0
  lineStartSegmentIndex = chunk.startSegmentIndex
  lineStartGraphemeIndex = 0
  lineEndSegmentIndex = chunk.startSegmentIndex
  lineEndGraphemeIndex = 0
  clearPendingBreak()

  let i = chunk.startSegmentIndex
  while (i < chunk.endSegmentIndex) {
    const kind = kinds[i]!
    const w = kind === 'tab' ? getTabAdvance(lineW, tabStopAdvance) : widths[i]!

    if (kind === 'soft-hyphen') {
      if (hasContent) {
        lineEndSegmentIndex = i + 1
        lineEndGraphemeIndex = 0
        pendingBreakSegmentIndex = i + 1
        pendingBreakFitWidth = lineW + discretionaryHyphenWidth
        pendingBreakPaintWidth = lineW + discretionaryHyphenWidth
        pendingBreakKind = kind
      }
      i++
      continue
    }

    if (!hasContent) {
      if (w > maxWidth && breakableWidths[i] !== null) {
        appendBreakableSegment(i)
      } else {
        startLineAtSegment(i, w)
      }
      updatePendingBreakForWholeSegment(i, w)
      i++
      continue
    }

    const newW = lineW + w
    if (newW > maxWidth + lineFitEpsilon) {
      const currentBreakFitWidth = lineW + (kind === 'tab' ? 0 : lineEndFitAdvances[i]!)
      const currentBreakPaintWidth = lineW + (kind === 'tab' ? w : lineEndPaintAdvances[i]!)

      if (canBreakAfter(kind) && currentBreakFitWidth <= maxWidth + lineFitEpsilon) {
        appendWholeSegment(i, w)
        emitCurrentLine(i + 1, 0, currentBreakPaintWidth)
        i++
        continue
      }
```

## 7. 行物化（layoutWithLines 等）：把 range 变成 text

rich API 需要输出每行 `text`，这意味着要把“segments + cursor ranges”重新拼回字符串。Pretext 把这部分与热路径隔离开：

- `layout()` 只走纯算术行数（见 2.2）
- `layoutWithLines()` 才会 materialize line text

为减少重复切 grapheme 的开销，rich path 使用 WeakMap 缓存：
- `sharedLineTextCaches`: `PreparedTextWithSegments -> Map<segmentIndex, graphemes[]>`
- `getLineTextCache` 管理缓存
- `buildLineTextFromRange` 会按需对某个 segment 进行 grapheme 切分并缓存（依赖 `getSegmentGraphemes`）

软连字符的“只在断行时显示 `-`”也在物化阶段处理（`lineHasDiscretionaryHyphen` 与 `buildLineTextFromRange`）。

代码摘录（src/layout.ts:L529-L579）：

```ts
function lineHasDiscretionaryHyphen(
  kinds: SegmentBreakKind[],
  startSegmentIndex: number,
  startGraphemeIndex: number,
  endSegmentIndex: number,
): boolean {
  return (
    endSegmentIndex > 0 &&
    kinds[endSegmentIndex - 1] === 'soft-hyphen' &&
    !(startSegmentIndex === endSegmentIndex && startGraphemeIndex > 0)
  )
}

function buildLineTextFromRange(
  segments: string[],
  kinds: SegmentBreakKind[],
  cache: Map<number, string[]>,
  startSegmentIndex: number,
  startGraphemeIndex: number,
  endSegmentIndex: number,
  endGraphemeIndex: number,
): string {
  let text = ''
  const endsWithDiscretionaryHyphen = lineHasDiscretionaryHyphen(
    kinds,
    startSegmentIndex,
    startGraphemeIndex,
    endSegmentIndex,
  )

  for (let i = startSegmentIndex; i < endSegmentIndex; i++) {
    if (kinds[i] === 'soft-hyphen' || kinds[i] === 'hard-break') continue
    if (i === startSegmentIndex && startGraphemeIndex > 0) {
      text += getSegmentGraphemes(i, segments, cache).slice(startGraphemeIndex).join('')
    } else {
      text += segments[i]!
    }
  }

  if (endGraphemeIndex > 0) {
    if (endsWithDiscretionaryHyphen) text += '-'
    text += getSegmentGraphemes(endSegmentIndex, segments, cache).slice(
      startSegmentIndex === endSegmentIndex ? startGraphemeIndex : 0,
      endGraphemeIndex,
    ).join('')
  } else if (endsWithDiscretionaryHyphen) {
    text += '-'
  }

  return text
}
```

## 8. Bidi 元数据（bidi.ts）

Pretext 并不把 bidi 作为换行引擎的输入，而是为“自绘/自排版”提供每个 segment 的 embedding level：
- 计算入口：`computeSegmentLevels`
- prepare 侧调用：在 rich path 下用 `segStarts` 映射 normalized 字符到 segment 起点（layout.ts 计算 `segLevels`）

实现是“简化版 Unicode bidi 算法”，原理来自 pdf.js 的实践路径（见文件头说明）。

代码摘录（src/bidi.ts:L164-L173）：

```ts
export function computeSegmentLevels(normalized: string, segStarts: number[]): Int8Array | null {
  const bidiLevels = computeBidiLevels(normalized)
  if (bidiLevels === null) return null

  const segLevels = new Int8Array(segStarts.length)
  for (let i = 0; i < segStarts.length; i++) {
    segLevels[i] = bidiLevels[segStarts[i]!]!
  }
  return segLevels
}
```

## 9. 运行时缓存控制：`clearCache` / `setLocale`

对外暴露的缓存控制 API 位于 layout.ts：
- `clearCache()`：清空分析缓存（word segmenter）、rich path grapheme 缓存、测量缓存（按字体的 segment metrics 与 emoji correction）
- `setLocale(locale?)`：设置 Intl.Segmenter 的 locale，并调用 `clearCache()`（注意：不会 retroactively 修改已 prepare 的句柄）

代码摘录（src/layout.ts:L707-L717）：

```ts
export function clearCache(): void {
  clearAnalysisCaches()
  sharedGraphemeSegmenter = null
  sharedLineTextCaches = new WeakMap<PreparedTextWithSegments, Map<number, string[]>>()
  clearMeasurementCaches()
}

export function setLocale(locale?: string): void {
  setAnalysisLocale(locale)
  clearCache()
}
```
## 10. Demo / Accuracy / Benchmark：如何保证“像浏览器”

虽然库本身只依赖 `src/`，但仓库通过 `pages/ + scripts/` 形成了一个“浏览器真值对照”的工程闭环：
- 本地页面服务命令：见 package.json 的 `start` 脚本与 DEVELOPMENT.md 的命令表
- `accuracy-check` / `benchmark-check` / `corpus-sweep` 等脚本入口：见 package.json 的 `scripts`
- 静态 demo 站点构建：scripts/build-demo-site.ts

这套体系的价值在于：当你改动 `analysis/measurement/line-break` 任一环节，都能用 corpus/accuracy 工具快速回归“与 DOM 布局一致”的程度。

## 11. 读源码的建议路径（从易到难）

1. 先读公共 API 与整体注释（layout.ts 文件头、prepare/layout 实现段）
2. 再读文本分析（analyzeText、buildMergedSegmentation）
3. 再读测量与 engine profile（measurement.ts）
4. 最后读换行引擎（建议先看 simple，再看完整路径：walkPreparedLinesSimple、walkPreparedLines）
