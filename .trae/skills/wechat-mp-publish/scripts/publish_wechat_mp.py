#!/usr/bin/env python3

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
DRAFT_ADD_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
FREEPUBLISH_SUBMIT_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/submit"
FREEPUBLISH_GET_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/get"

PUBLISH_STATUS_LABELS = {
    0: "success",
    1: "publishing",
    2: "original_check_failed",
    3: "normal_failed",
    4: "platform_audit_failed",
    5: "deleted_after_publish",
    6: "banned_after_publish",
}

ROOT_DIR = Path(__file__).resolve().parents[4]
WEB_SPEC_PATH = Path(__file__).with_name("publish_wechat_mp_web.spec.js")


class WeChatPublishError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish an article to WeChat Official Account")
    parser.add_argument("--title", help="Article title")
    parser.add_argument("--content", help="Inline article content")
    parser.add_argument("--content-file", help="Path to a file containing article content")
    parser.add_argument(
        "--publish-mode",
        choices=("auto", "web", "api"),
        default="auto",
        help="Publish via web automation or official api, defaults to auto",
    )
    parser.add_argument(
        "--action",
        choices=("draft", "publish"),
        default="draft",
        help="Save as draft or publish immediately in web mode",
    )
    parser.add_argument(
        "--content-format",
        choices=("auto", "html", "text", "markdown"),
        default="auto",
        help="Input content format, defaults to auto",
    )
    parser.add_argument("--thumb-media-id", help="Permanent cover material media id")
    parser.add_argument("--author", help="Article author")
    parser.add_argument("--digest", default="", help="Article digest")
    parser.add_argument("--content-source-url", default="", help="Original source URL")
    parser.add_argument("--cover-prompt", default="", help="Prompt for AI cover generation in web mode")
    parser.add_argument("--render-only", action="store_true", help="Render the content to HTML and print it")
    parser.add_argument("--keep-browser", action="store_true", help="Keep browser open after web automation")
    parser.add_argument("--browser-channel", default="chrome", help="Browser channel for Playwright web mode")
    parser.add_argument("--user-data-dir", help="Persistent browser profile directory for web mode login reuse")
    parser.add_argument(
        "--need-open-comment",
        type=int,
        choices=(0, 1),
        default=0,
        help="Whether to enable comments",
    )
    parser.add_argument(
        "--only-fans-can-comment",
        type=int,
        choices=(0, 1),
        default=0,
        help="Whether only followers can comment",
    )
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Publish status poll interval seconds")
    parser.add_argument("--timeout", type=float, default=180.0, help="Overall publish timeout seconds")
    return parser.parse_args()


def read_source(args: argparse.Namespace) -> Tuple[str, Optional[Path]]:
    if bool(args.content) == bool(args.content_file):
        raise WeChatPublishError("必须且只能提供 --content 或 --content-file 其中一种")

    source_path = Path(args.content_file) if args.content_file else None
    if args.content_file:
        content = source_path.read_text(encoding="utf-8")
    else:
        content = args.content

    if not content or not content.strip():
        raise WeChatPublishError("文章正文不能为空")

    return content, source_path


def read_content(args: argparse.Namespace) -> Tuple[str, str, Optional[Path]]:
    content, source_path = read_source(args)

    content_format = detect_content_format(content, args.content_format, source_path)

    if content_format == "text":
        return content, text_to_html(content), source_path
    if content_format == "markdown":
        return content, markdown_to_wechat_html(content), source_path
    return content, content, source_path


def resolve_publish_mode(args: argparse.Namespace) -> str:
    if args.publish_mode != "auto":
        return args.publish_mode
    return "web"


def resolve_author(args: argparse.Namespace) -> str:
    return (args.author or os.getenv("WECHAT_MP_AUTHOR", "") or "繁漪").strip()


def resolve_title(args: argparse.Namespace, raw_content: str, source_path: Optional[Path]) -> str:
    if args.title and args.title.strip():
        return args.title.strip()

    if detect_content_format(raw_content, args.content_format, source_path) == "markdown":
        title = extract_title_from_markdown(raw_content)
        if title:
            return title

    if source_path:
        return source_path.stem.replace("-", " ").replace("_", " ").strip()

    first_line = next((line.strip() for line in raw_content.splitlines() if line.strip()), "")
    if first_line:
        return first_line[:80]
    raise WeChatPublishError("无法推断标题，请显式传入 --title")


def extract_title_from_markdown(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^#\s+(.+)$", stripped)
        if match:
            return cleanup_markdown_text(match.group(1))

    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("```", "- ", "* ", "> ")):
            return cleanup_markdown_text(stripped)
    return ""


def cleanup_markdown_text(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\(([^\)]+)\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^\)]+)\)", r"\1", text)
    text = re.sub(r"[`*_#>]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def build_digest(html_content: str, limit: int = 120) -> str:
    plain = re.sub(r"<style[\s\S]*?</style>", " ", html_content, flags=re.I)
    plain = re.sub(r"<script[\s\S]*?</script>", " ", plain, flags=re.I)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = html.unescape(re.sub(r"\s+", " ", plain)).strip()
    return plain[:limit]


def run_web_publish(
    args: argparse.Namespace,
    title: str,
    author: str,
    digest: str,
    source_path: Optional[Path],
) -> int:
    env = os.environ.copy()
    env["WECHAT_MP_TITLE"] = title
    env["WECHAT_MP_AUTHOR"] = author
    env["WECHAT_MP_DIGEST"] = digest
    env["WECHAT_MP_ACTION"] = args.action
    env["WECHAT_MP_CONTENT_FORMAT"] = args.content_format
    env["WECHAT_MP_BROWSER_CHANNEL"] = args.browser_channel

    if args.cover_prompt:
        env["WECHAT_MP_COVER_PROMPT"] = args.cover_prompt
    if args.keep_browser:
        env["WECHAT_MP_KEEP_BROWSER"] = "1"
    if args.user_data_dir:
        env["WECHAT_MP_USER_DATA_DIR"] = args.user_data_dir

    if args.content_file:
        env["WECHAT_MP_CONTENT_FILE"] = str(source_path.resolve())
    else:
        env["WECHAT_MP_CONTENT"] = args.content or ""

    command = [
        "npx",
        "--prefix",
        str(ROOT_DIR),
        "playwright",
        "test",
        str(WEB_SPEC_PATH),
        "--headed",
        "--workers=1",
    ]

    completed = subprocess.run(command, env=env)
    if completed.returncode != 0:
        raise WeChatPublishError(f"后台自动化发布失败，退出码: {completed.returncode}")
    return completed.returncode


def detect_content_format(content: str, requested_format: str, source_path: Optional[Path]) -> str:
    if requested_format != "auto":
        return requested_format

    suffix = source_path.suffix.lower() if source_path else ""
    if suffix in {".md", ".markdown", ".mdown"}:
        return "markdown"
    if suffix in {".html", ".htm"}:
        return "html"
    if looks_like_html(content):
        return "html"
    if looks_like_markdown(content):
        return "markdown"
    return "text"


def looks_like_html(content: str) -> bool:
    snippet = content.lstrip()[:300]
    return bool(re.search(r"<\s*(p|div|section|article|h[1-6]|ul|ol|li|blockquote|img|pre|table|br)\b", snippet, re.I))


def looks_like_markdown(content: str) -> bool:
    sample = content[:2000]
    patterns = [
        r"(?m)^#{1,6}\s+",
        r"(?m)^```",
        r"(?m)^\s*[-*+]\s+",
        r"(?m)^\s*\d+\.\s+",
        r"\[[^\]]+\]\([^\)]+\)",
        r"\*\*[^*]+\*\*",
        r"`[^`]+`",
    ]
    return any(re.search(pattern, sample) for pattern in patterns)


def text_to_html(content: str) -> str:
    paragraphs = [segment.strip() for segment in content.replace("\r\n", "\n").split("\n\n")]
    blocks = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        escaped = html.escape(paragraph).replace("\n", "<br/>")
        blocks.append(f"<p>{escaped}</p>")
    if not blocks:
        raise WeChatPublishError("纯文本内容转换后为空，请检查输入")
    return "\n".join(blocks)


def markdown_to_wechat_html(content: str) -> str:
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    paragraph_lines = []
    list_items = []
    list_type = None
    code_lines = []
    code_lang = ""
    in_code_block = False
    blockquote_lines = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        text = "<br/>".join(render_inline(line.strip()) for line in paragraph_lines if line.strip())
        if text:
            output.append(
                '<p style="margin: 1em 0; line-height: 1.75; color: #222; font-size: 16px;">'
                + text
                + "</p>"
            )
        paragraph_lines = []

    def flush_list() -> None:
        nonlocal list_items, list_type
        if not list_items:
            return
        tag = "ol" if list_type == "ol" else "ul"
        output.append(
            f'<{tag} style="margin: 1em 0 1em 1.5em; padding: 0; line-height: 1.75; color: #222; font-size: 16px;">'
            + "".join(f'<li style="margin: 0.35em 0;">{item}</li>' for item in list_items)
            + f"</{tag}>"
        )
        list_items = []
        list_type = None

    def flush_blockquote() -> None:
        nonlocal blockquote_lines
        if not blockquote_lines:
            return
        quote_html = "<br/>".join(render_inline(line.strip()) for line in blockquote_lines if line.strip())
        output.append(
            '<blockquote style="margin: 1em 0; padding: 0.75em 1em; background: #f6f7f8; border-left: 4px solid #07c160; color: #555;">'
            + quote_html
            + "</blockquote>"
        )
        blockquote_lines = []

    def flush_code_block() -> None:
        nonlocal code_lines, code_lang
        code = "\n".join(code_lines)
        label = f'<div style="margin-bottom: 0.5em; color: #576b95; font-size: 13px;">{html.escape(code_lang)}</div>' if code_lang else ""
        output.append(
            '<section style="margin: 1em 0;">'
            + label
            + '<pre style="margin: 0; padding: 12px 14px; overflow-x: auto; background: #f6f8fa; border-radius: 6px;">'
            + f'<code style="font-family: Menlo, Consolas, monospace; font-size: 13px; line-height: 1.6; color: #24292f;">{html.escape(code)}</code>'
            + "</pre></section>"
        )
        code_lines = []
        code_lang = ""

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        fence_match = re.match(r"^```\s*([^`]*)$", stripped)
        if fence_match:
            flush_paragraph()
            flush_list()
            flush_blockquote()
            if in_code_block:
                flush_code_block()
                in_code_block = False
            else:
                in_code_block = True
                code_lang = fence_match.group(1).strip()
                code_lines = []
            continue

        if in_code_block:
            code_lines.append(raw_line)
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            flush_blockquote()
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flush_paragraph()
            flush_list()
            flush_blockquote()
            output.append('<hr style="border: none; border-top: 1px solid #e6e6e6; margin: 1.5em 0;"/>')
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            flush_list()
            flush_blockquote()
            level = len(heading_match.group(1))
            heading_text = render_inline(heading_match.group(2).strip())
            size = {1: "28px", 2: "24px", 3: "20px", 4: "18px", 5: "16px", 6: "15px"}[level]
            weight = "700" if level <= 2 else "600"
            output.append(
                f'<h{level} style="margin: 1.2em 0 0.6em; font-size: {size}; line-height: 1.4; font-weight: {weight}; color: #111;">{heading_text}</h{level}>'
            )
            continue

        blockquote_match = re.match(r"^>\s?(.*)$", stripped)
        if blockquote_match:
            flush_paragraph()
            flush_list()
            blockquote_lines.append(blockquote_match.group(1))
            continue

        unordered_match = re.match(r"^\s*[-*+]\s+(.*)$", line)
        ordered_match = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if unordered_match or ordered_match:
            flush_paragraph()
            flush_blockquote()
            current_type = "ol" if ordered_match else "ul"
            if list_type and list_type != current_type:
                flush_list()
            list_type = current_type
            item_text = ordered_match.group(1) if ordered_match else unordered_match.group(1)
            list_items.append(render_inline(item_text.strip()))
            continue

        flush_list()
        flush_blockquote()
        paragraph_lines.append(line)

    if in_code_block:
        flush_code_block()
    flush_paragraph()
    flush_list()
    flush_blockquote()

    if not output:
        raise WeChatPublishError("Markdown 转换后为空，请检查输入")
    return "\n".join(output)


def render_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(
        r"!\[([^\]]*)\]\(([^\)\s]+)(?:\s+\&quot;([^\"]*)\&quot;)?\)",
        lambda m: render_image(m.group(2), m.group(1), m.group(3) or m.group(1)),
        escaped,
    )
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^\)\s]+)\)",
        lambda m: f'<a href="{m.group(2)}" style="color: #576b95; text-decoration: none;">{m.group(1)}</a>',
        escaped,
    )
    escaped = re.sub(r"`([^`]+)`", r'<code style="padding: 0.15em 0.3em; background: #f2f4f5; border-radius: 4px; font-family: Menlo, Consolas, monospace; font-size: 0.92em;">\1</code>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", escaped)
    return escaped


def render_image(src: str, alt: str, title: str) -> str:
    alt_attr = html.escape(alt or title or "image")
    title_attr = html.escape(title or alt or "")
    caption = f'<figcaption style="margin-top: 0.5em; color: #888; font-size: 13px; text-align: center;">{title_attr}</figcaption>' if title_attr else ""
    return (
        '<figure style="margin: 1.2em 0; text-align: center;">'
        + f'<img src="{src}" alt="{alt_attr}" style="max-width: 100%; height: auto; border-radius: 6px;"/>'
        + caption
        + "</figure>"
    )


def request_json(url: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise WeChatPublishError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise WeChatPublishError(f"网络请求失败: {exc}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise WeChatPublishError(f"接口返回不是合法 JSON: {body}") from exc

    errcode = result.get("errcode", 0)
    if errcode not in (0, None):
        errmsg = result.get("errmsg", "unknown error")
        raise WeChatPublishError(f"微信接口调用失败: errcode={errcode}, errmsg={errmsg}")
    return result


def get_access_token() -> str:
    existing = os.getenv("WECHAT_MP_ACCESS_TOKEN", "").strip()
    if existing:
        return existing

    appid = os.getenv("WECHAT_MP_APPID", "").strip()
    appsecret = os.getenv("WECHAT_MP_APPSECRET", "").strip()
    if not appid or not appsecret:
        raise WeChatPublishError("缺少认证信息：请设置 WECHAT_MP_ACCESS_TOKEN 或 WECHAT_MP_APPID + WECHAT_MP_APPSECRET")

    query = urllib.parse.urlencode(
        {
            "grant_type": "client_credential",
            "appid": appid,
            "secret": appsecret,
        }
    )
    response = request_json(f"{TOKEN_URL}?{query}")
    token = response.get("access_token", "").strip()
    if not token:
        raise WeChatPublishError("获取 access_token 成功但响应中没有 access_token")
    return token


def api_url(base_url: str, access_token: str) -> str:
    return f"{base_url}?{urllib.parse.urlencode({'access_token': access_token})}"


def create_draft(access_token: str, article_payload: dict) -> str:
    response = request_json(
        api_url(DRAFT_ADD_URL, access_token),
        method="POST",
        payload={"articles": [article_payload]},
    )
    media_id = response.get("media_id", "").strip()
    if not media_id:
        raise WeChatPublishError("草稿创建成功但未返回 media_id")
    return media_id


def submit_publish(access_token: str, media_id: str) -> dict:
    response = request_json(
        api_url(FREEPUBLISH_SUBMIT_URL, access_token),
        method="POST",
        payload={"media_id": media_id},
    )
    publish_id = response.get("publish_id", "").strip()
    if not publish_id:
        raise WeChatPublishError("发布提交成功但未返回 publish_id")
    return response


def poll_publish(access_token: str, publish_id: str, poll_interval: float, timeout: float) -> dict:
    deadline = time.time() + timeout
    last_response = None

    while time.time() <= deadline:
        response = request_json(
            api_url(FREEPUBLISH_GET_URL, access_token),
            method="POST",
            payload={"publish_id": publish_id},
        )
        last_response = response
        status = response.get("publish_status")
        if status == 0:
            return response
        if status != 1:
            label = PUBLISH_STATUS_LABELS.get(status, "unknown")
            raise WeChatPublishError(
                f"发布失败: publish_status={status} ({label}), response={json.dumps(response, ensure_ascii=False)}"
            )
        time.sleep(poll_interval)

    raise WeChatPublishError(
        "发布轮询超时，最后一次响应: " + json.dumps(last_response or {}, ensure_ascii=False)
    )


def extract_article_url(publish_response: dict) -> str:
    detail = publish_response.get("article_detail") or {}
    items = detail.get("item") or []
    if not items:
        return ""
    first = items[0] or {}
    return str(first.get("article_url", ""))


def main() -> int:
    try:
        args = parse_args()
        raw_content, content, source_path = read_content(args)
        title = resolve_title(args, raw_content, source_path)
        author = resolve_author(args)
        digest = args.digest.strip() or build_digest(content)
        publish_mode = resolve_publish_mode(args)

        if args.render_only:
            print(content)
            return 0

        if publish_mode == "web":
            return run_web_publish(args, title, author, digest, source_path)

        if not args.thumb_media_id:
            raise WeChatPublishError("缺少封面素材：API 模式下必须提供 --thumb-media-id")

        access_token = get_access_token()

        article_payload = {
            "title": title,
            "author": author,
            "digest": digest,
            "content": content,
            "content_source_url": args.content_source_url,
            "thumb_media_id": args.thumb_media_id,
            "need_open_comment": args.need_open_comment,
            "only_fans_can_comment": args.only_fans_can_comment,
        }

        media_id = create_draft(access_token, article_payload)
        submit_response = submit_publish(access_token, media_id)
        publish_id = submit_response["publish_id"]
        publish_response = poll_publish(access_token, publish_id, args.poll_interval, args.timeout)

        result = {
            "media_id": media_id,
            "publish_id": publish_id,
            "publish_status": publish_response.get("publish_status"),
            "publish_status_label": PUBLISH_STATUS_LABELS.get(publish_response.get("publish_status"), "unknown"),
            "article_id": publish_response.get("article_id", ""),
            "article_url": extract_article_url(publish_response),
            "fail_idx": publish_response.get("fail_idx", []),
        }

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except FileNotFoundError as exc:
        print(f"输入文件不存在: {exc}", file=sys.stderr)
        return 1
    except WeChatPublishError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
