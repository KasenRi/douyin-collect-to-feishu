#!/usr/bin/env python3
"""通过已登录的 Chromium（CDP）搜索抖音视频 / 取单条详情，只读抓取页面自身发出的接口响应。

用法：
  python3 douyin_search.py search "<关键词>" [N=50] > search.json
  python3 douyin_search.py detail <aweme_id 或视频链接>   > detail.json
环境变量：CDP_URL（默认 http://127.0.0.1:9222）。

前提：Chromium 以 --remote-debugging-port 启动，并由你本人手动登录过抖音。
遇到验证码脚本会停下（退出码 3），请到浏览器里手动处理后重跑；本脚本不含任何验证码破解。
只读：不点赞、不评论、不关注、不私信。
"""
import asyncio, json, os, random, re, sys
from urllib.parse import quote
from playwright.async_api import async_playwright

CDP = os.environ.get("CDP_URL", "http://127.0.0.1:9222")
SEARCH_API = ("/aweme/v1/web/search/item/", "/aweme/v1/web/general/search")
DETAIL_API = "/aweme/v1/web/aweme/detail/"


def brief(a):
    au = a.get("author") or {}; s = a.get("statistics") or {}; v = a.get("video") or {}
    return {"aweme_id": a.get("aweme_id"), "desc": a.get("desc"), "author": au.get("nickname"),
            "digg_count": s.get("digg_count"), "collect_count": s.get("collect_count"),
            "comment_count": s.get("comment_count"), "share_count": s.get("share_count"),
            "create_time": a.get("create_time"), "duration_ms": v.get("duration"),
            "url": f"https://www.douyin.com/video/{a.get('aweme_id')}"}


def play_urls(a):
    """仅供下载使用，不要写进文档。按码率从高到低。"""
    v = a.get("video") or {}
    rates = sorted(v.get("bit_rate") or [], key=lambda x: x.get("bit_rate", 0), reverse=True)
    urls = [u for r in rates for u in ((r.get("play_addr") or {}).get("url_list") or [])]
    return urls + ((v.get("play_addr") or {}).get("url_list") or [])


async def main():
    cmd, arg = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        if not any(c["name"] == "sessionid" for c in await ctx.cookies("https://www.douyin.com")):
            print(json.dumps({"ok": False, "error": "未登录：浏览器里没有 sessionid，请先手动登录抖音"}, ensure_ascii=False)); sys.exit(4)
        pg = await ctx.new_page()
        got, det = {}, {}

        async def on(r):
            u = r.url
            try:
                if any(k in u for k in SEARCH_API):
                    d = await r.json()
                    for x in d.get("data") or []:
                        a = x.get("aweme_info") or x
                        if a.get("aweme_id") and a["aweme_id"] not in got: got[a["aweme_id"]] = a
                elif DETAIL_API in u:
                    d = await r.json()
                    if d.get("aweme_detail"): det["a"] = d["aweme_detail"]
            except Exception:
                pass
        pg.on("response", on)
        try:
            if cmd == "search":
                await pg.goto(f"https://www.douyin.com/search/{quote(arg)}?type=video", wait_until="domcontentloaded", timeout=60000)
                await pg.wait_for_timeout(5000)
                for _ in range(20):
                    if "验证码" in await pg.title():
                        print(json.dumps({"ok": False, "error": "出现验证码，请在浏览器中手动处理后重跑"}, ensure_ascii=False)); sys.exit(3)
                    if len(got) >= n: break
                    await pg.mouse.move(700, 500); await pg.mouse.wheel(0, random.randint(2500, 4000))
                    await pg.wait_for_timeout(random.randint(1800, 3200))
                items = [dict(brief(a), play_urls=play_urls(a)) for a in list(got.values())[:n]]
                r = {"ok": bool(items), "keyword": arg, "count": len(items), "items": items}
            else:
                aid = re.search(r"\d{8,25}", arg).group(0)
                await pg.goto(f"https://www.douyin.com/video/{aid}", wait_until="domcontentloaded", timeout=60000)
                for _ in range(12):
                    if "a" in det: break
                    await pg.wait_for_timeout(1500)
                a = det.get("a")
                r = {"ok": False, "aweme_id": aid, "error": "未抓到详情接口"} if not a else dict(brief(a), ok=True, play_urls=play_urls(a))
        finally:
            await pg.close()  # 只关自己开的标签页，不关浏览器
    print(json.dumps(r, ensure_ascii=False, indent=2)); sys.exit(0 if r["ok"] else 2)

asyncio.run(main())
