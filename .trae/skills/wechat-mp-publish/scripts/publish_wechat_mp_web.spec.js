const { test, chromium } = require('playwright/test');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname);
const RENDERER = path.join(ROOT, 'publish_wechat_mp.py');

function requiredEnv(name) {
  const value = process.env[name];
  if (!value || !value.trim()) {
    throw new Error(`缺少环境变量 ${name}`);
  }
  return value.trim();
}

function optionalEnv(name, fallback = '') {
  const value = process.env[name];
  return value === undefined ? fallback : value;
}

function renderHtmlFromSource() {
  const content = optionalEnv('WECHAT_MP_CONTENT');
  const contentFile = optionalEnv('WECHAT_MP_CONTENT_FILE');
  const contentFormat = optionalEnv('WECHAT_MP_CONTENT_FORMAT', 'auto');

  if (Boolean(content) === Boolean(contentFile)) {
    throw new Error('必须设置 WECHAT_MP_CONTENT 或 WECHAT_MP_CONTENT_FILE 其中之一');
  }

  const args = [RENDERER, '--render-only', '--content-format', contentFormat];
  if (content) {
    args.push('--content', content);
  } else {
    args.push('--content-file', path.resolve(contentFile));
  }

  const result = spawnSync('python3', args, { encoding: 'utf-8' });
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || 'Markdown 转 HTML 失败').trim());
  }
  return result.stdout.trim();
}

function htmlToPlainText(html) {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function buildDigest(html) {
  const plain = htmlToPlainText(html);
  const maxLength = Number(optionalEnv('WECHAT_MP_DIGEST_MAX_LENGTH', '120')) || 120;
  return plain.slice(0, maxLength);
}

async function waitForAnyVisible(page, selectors, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    for (const selector of selectors) {
      const locator = page.locator(selector).first();
      if (await locator.count()) {
        try {
          if (await locator.isVisible()) {
            return locator;
          }
        } catch (_) {}
      }
    }
    await page.waitForTimeout(500);
  }
  throw new Error(`未找到可见元素: ${selectors.join(' | ')}`);
}

async function clickFirst(page, selectors, timeout = 15000) {
  const locator = await waitForAnyVisible(page, selectors, timeout);
  await locator.click();
  return locator;
}

async function fillFirst(page, selectors, value, timeout = 15000) {
  const locator = await waitForAnyVisible(page, selectors, timeout);
  await locator.fill('');
  await locator.fill(value);
  return locator;
}

async function typeIntoTitle(page, title) {
  const selectors = [
    '[placeholder="请在这里输入标题（选填）"]',
    '[placeholder*="输入标题"]',
    'textarea[placeholder*="标题"]',
    '[contenteditable="true"][data-placeholder*="标题"]',
    '[contenteditable="true"][placeholder*="标题"]',
  ];

  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    if (await locator.count()) {
      try {
        await locator.click();
        if (await locator.getAttribute('contenteditable')) {
          await locator.evaluate((el, value) => {
            el.focus();
            el.innerHTML = '';
            el.textContent = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
          }, title);
        } else {
          await locator.fill(title);
        }
        return;
      } catch (_) {}
    }
  }
  throw new Error('未找到标题输入框');
}

async function fillEditorHtml(page, html) {
  const frameDeadline = Date.now() + 30000;
  while (Date.now() < frameDeadline) {
    for (const frame of page.frames()) {
      try {
        const body = frame.locator('body[contenteditable="true"], body');
        if ((await body.count()) && (await body.first().isVisible())) {
          await body.first().evaluate((node, value) => {
            node.innerHTML = value;
            node.dispatchEvent(new Event('input', { bubbles: true }));
          }, html);
          return;
        }
      } catch (_) {}
    }

    const candidates = [
      '.ql-editor',
      '.ProseMirror',
      '[contenteditable="true"][role="textbox"]',
      '[contenteditable="true"]',
    ];
    for (const selector of candidates) {
      const locator = page.locator(selector).first();
      if (await locator.count()) {
        try {
          await locator.click();
          await locator.evaluate((node, value) => {
            node.innerHTML = value;
            node.dispatchEvent(new Event('input', { bubbles: true }));
          }, html);
          return;
        } catch (_) {}
      }
    }
    await page.waitForTimeout(500);
  }
  throw new Error('未找到正文编辑区');
}

async function ensureLoggedIn(page) {
  await page.goto('https://mp.weixin.qq.com/', { waitUntil: 'domcontentloaded' });
  const loginTimeout = Number(optionalEnv('WECHAT_MP_LOGIN_TIMEOUT_MS', '180000')) || 180000;
  const deadline = Date.now() + loginTimeout;
  while (Date.now() < deadline) {
    const url = page.url();
    if (!/login/i.test(url) && /mp\.weixin\.qq\.com/.test(url)) {
      const body = page.locator('body');
      if (await body.count()) {
        const text = await body.innerText().catch(() => '');
        if (!text.includes('微信扫码登录')) {
          return;
        }
      }
    }
    await page.waitForTimeout(1000);
  }
  throw new Error('登录超时：请在打开的浏览器中完成公众号后台登录');
}

async function openEditor(page) {
  const directUrls = [
    'https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&type=10&isNew=1&lang=zh_CN',
    'https://mp.weixin.qq.com/cgi-bin/appmsg',
  ];

  for (const url of directUrls) {
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    try {
      await waitForAnyVisible(page, [
        '[placeholder*="标题"]',
        'textarea[placeholder*="标题"]',
        '[contenteditable="true"][data-placeholder*="标题"]',
      ], 10000);
      return;
    } catch (_) {}
  }

  await clickFirst(page, [
    'text=图文消息',
    'text=新建图文',
    'text=写新图文',
    'text=新的创作',
  ], 15000);
}

async function generateAiCover(page) {
  const enableSelectors = [
    'text=封面和摘要',
    'text=封面摘要',
    'text=添加封面',
    'text=设置封面',
  ];
  try {
    await clickFirst(page, enableSelectors, 5000);
  } catch (_) {}

  await clickFirst(page, [
    'text=AI配图',
    'text=AI生成封面',
    'text=智能配图',
    'text=生成封面图',
    'text=生成图片',
  ], 20000);

  const prompt = optionalEnv('WECHAT_MP_COVER_PROMPT');
  if (prompt) {
    try {
      await fillFirst(page, [
        'textarea[placeholder*="描述"]',
        'textarea[placeholder*="提示词"]',
        'input[placeholder*="描述"]',
        'input[placeholder*="提示词"]',
      ], prompt, 8000);
    } catch (_) {}
  }

  try {
    await clickFirst(page, [
      'text=生成',
      'text=立即生成',
      'text=开始生成',
    ], 10000);
  } catch (_) {}

  await clickFirst(page, [
    'img',
    '[role="img"]',
    '.cover img',
    '.material_list img',
  ], 60000);

  try {
    await clickFirst(page, [
      'text=确认',
      'text=使用',
      'text=选用',
      'text=完成',
    ], 10000);
  } catch (_) {}
}

async function publishArticle(page) {
  await clickFirst(page, [
    'text=发表',
    'text=发布',
    'button:has-text("发表")',
    'button:has-text("发布")',
  ], 20000);

  try {
    await clickFirst(page, [
      'text=确定',
      'text=确认发表',
      'text=继续',
      'text=发布',
    ], 10000);
  } catch (_) {}
}

async function saveDraft(page) {
  await clickFirst(page, [
    'text=保存为草稿',
    'text=保存草稿',
    'text=保存',
    'button:has-text("保存")',
  ], 20000);
}

async function waitForDraftResult(page) {
  const timeout = Number(optionalEnv('WECHAT_MP_PUBLISH_TIMEOUT_MS', '180000')) || 180000;
  const deadline = Date.now() + timeout;

  while (Date.now() < deadline) {
    const bodyText = await page.locator('body').innerText().catch(() => '');
    if (/保存成功|草稿已保存|已保存到草稿箱|保存为草稿成功/.test(bodyText)) {
      return { url: page.url() };
    }
    await page.waitForTimeout(1000);
  }
  throw new Error('等待保存草稿结果超时');
}

async function waitForPublishResult(page) {
  const timeout = Number(optionalEnv('WECHAT_MP_PUBLISH_TIMEOUT_MS', '180000')) || 180000;
  const deadline = Date.now() + timeout;

  while (Date.now() < deadline) {
    const currentUrl = page.url();
    if (/mp\.weixin\.qq\.com/.test(currentUrl) && !/edit/.test(currentUrl)) {
      return { url: currentUrl };
    }
    const bodyText = await page.locator('body').innerText().catch(() => '');
    if (/发表成功|发布成功|已发表/.test(bodyText)) {
      return { url: currentUrl };
    }
    await page.waitForTimeout(1000);
  }
  throw new Error('等待发布结果超时');
}

test('publish wechat mp article via web ui', async () => {
  test.setTimeout(0);

  const title = requiredEnv('WECHAT_MP_TITLE');
  const author = optionalEnv('WECHAT_MP_AUTHOR', '繁漪');
  const action = optionalEnv('WECHAT_MP_ACTION', 'draft');
  const userDataDir = path.resolve(optionalEnv('WECHAT_MP_USER_DATA_DIR', path.join(ROOT, '.wechat-mp-browser')));
  fs.mkdirSync(userDataDir, { recursive: true });

  const html = renderHtmlFromSource();
  const digest = optionalEnv('WECHAT_MP_DIGEST', buildDigest(html));

  const context = await chromium.launchPersistentContext(userDataDir, {
    channel: optionalEnv('WECHAT_MP_BROWSER_CHANNEL', 'chrome'),
    headless: false,
    viewport: { width: 1440, height: 960 },
  });
  const page = context.pages()[0] || await context.newPage();

  try {
    await ensureLoggedIn(page);
    await openEditor(page);
    await typeIntoTitle(page, title);

    if (author) {
      try {
        await fillFirst(page, [
          'input[placeholder*="作者"]',
          'textarea[placeholder*="作者"]',
        ], author, 8000);
      } catch (_) {}
    }

    if (digest) {
      try {
        await fillFirst(page, [
          'textarea[placeholder*="摘要"]',
          'input[placeholder*="摘要"]',
        ], digest, 8000);
      } catch (_) {}
    }

    await fillEditorHtml(page, html);
    await generateAiCover(page);
    let result;
    if (action === 'publish') {
      await publishArticle(page);
      result = await waitForPublishResult(page);
    } else {
      await saveDraft(page);
      result = await waitForDraftResult(page);
    }
    console.log(JSON.stringify({ mode: 'web', action, title, author, result_url: result.url }, null, 2));
  } finally {
    if (optionalEnv('WECHAT_MP_KEEP_BROWSER', '0') !== '1') {
      await context.close();
    }
  }
});
