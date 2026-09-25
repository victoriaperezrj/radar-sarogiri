import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import defusedxml.ElementTree as ET

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

X_REGIONS = {"AR": "argentina/", "MUNDO": "", "US": "united-states/"}
GOOGLE_GEOS = ["AR", "US", "GB", "BR", "MX", "ES"]
TIKTOK_COUNTRIES = ["AR", "US", "MX", "BR", "ES", "GB"]
REDDIT_SUBS = {"MUNDO": "all", "AR": "argentina", "EXPLICA": "OutOfTheLoop"}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def item(source, region, keyword, rank, traffic="", url="", extra=None):
    return {
        "source": source,
        "region": region,
        "keyword": keyword.strip(),
        "rank": rank,
        "traffic": traffic,
        "url": url,
        "extra": extra or {},
    }


def x_trends(region):
    """trends24 shows one list per hour; we use them to get hours-in-trending and rank trajectory."""
    page = _get(f"https://trends24.in/{X_REGIONS[region]}")
    blocks = re.findall(r"<ol class=trend-card__list>(.*?)</ol>", page, re.S)[:24]
    hourly = [
        [html.unescape(t) for t in re.findall(r"class=trend-link>([^<]+)<", b)] for b in blocks
    ]
    if not hourly:
        return []
    out = []
    for rank, kw in enumerate(hourly[0], 1):
        ranks = [h.index(kw) + 1 if kw in h else None for h in hourly]
        hours_seen = sum(r is not None for r in ranks)
        prev = next((r for r in ranks[1:] if r is not None), None)
        out.append(
            item(
                "X",
                region,
                kw,
                rank,
                url="https://x.com/search?q=" + urllib.parse.quote(kw),
                extra={
                    "hours_in_trending": hours_seen,
                    "is_new": hours_seen == 1,
                    "rank_prev_hour": prev,
                    "rank_history": ranks[:12],
                },
            )
        )
    return out


def google_trends(geo):
    root = ET.fromstring(_get(f"https://trends.google.com/trending/rss?geo={geo}"))
    ns = {"ht": "https://trends.google.com/trending/rss"}
    out = []
    for rank, i in enumerate(root.iter("item"), 1):
        news = i.find("ht:news_item", ns)
        out.append(
            item(
                "Google",
                geo,
                i.findtext("title"),
                rank,
                traffic=i.findtext("ht:approx_traffic", namespaces=ns) or "",
                url=news.findtext("ht:news_item_url", namespaces=ns) if news is not None else "",
                extra={"news": news.findtext("ht:news_item_title", namespaces=ns) if news is not None else ""},
            )
        )
    return out


def reddit_rising(region):
    atom = {"a": "http://www.w3.org/2005/Atom"}
    url = f"https://www.reddit.com/r/{REDDIT_SUBS[region]}/rising/.rss?limit=25"
    for wait in (8, 30, 60):  # Reddit answers 429 to back-to-back unauthenticated requests
        time.sleep(wait)
        try:
            root = ET.fromstring(_get(url))
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or wait == 60:
                raise
    out = []
    for rank, e in enumerate(root.findall("a:entry", atom), 1):
        cat = e.find("a:category", atom)
        link = e.find("a:link", atom)
        out.append(
            item(
                "Reddit",
                region,
                e.findtext("a:title", namespaces=atom),
                rank,
                url=link.get("href") if link is not None else "",
                extra={"subreddit": cat.get("label") if cat is not None else ""},
            )
        )
    return out


def _parse_tiktok(text, region):
    """Creative Center lists: rank, #tag, [industry], posts, 'Posts', views, 'Views' (industry is sometimes absent)."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = []
    for i, line in enumerate(lines):
        if not (line.startswith("#") and i > 0 and lines[i - 1].isdigit()):
            continue
        block = lines[i + 1 : i + 7]
        posts = block[block.index("Posts") - 1] if "Posts" in block else ""
        views = block[block.index("Views") - 1] if "Views" in block else ""
        industry = block[0] if block and not re.match(r"^[\d.,]+[KMB]?$", block[0]) else ""
        out.append(
            item(
                "TikTok",
                region,
                line,
                int(lines[i - 1]),
                traffic=f"{views} vistas" if views else "",
                url="https://www.tiktok.com/tag/" + urllib.parse.quote(line.lstrip("#")),
                extra={"industry": industry, "posts": posts, "views": views},
            )
        )
    return out


def tiktok_trends(countries=TIKTOK_COUNTRIES):
    from playwright.sync_api import sync_playwright

    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(locale="es-AR", user_agent=UA, viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        for cc in countries:
            try:
                page.goto(
                    f"https://ads.tiktok.com/creative/creativeCenter/trends/hashtag?countryCode={cc}&period=7&region={cc}",
                    timeout=60000,
                )
                page.get_by_text("Posts", exact=True).first.wait_for(timeout=30000)
                results[cc] = _parse_tiktok(page.locator("body").inner_text(), cc)
            except Exception as e:
                results[cc] = f"FALLA: {type(e).__name__}: {e}"
        browser.close()
    return results


def all_sources():
    jobs = [(f"X {r}", lambda r=r: x_trends(r)) for r in X_REGIONS]
    jobs += [(f"Google {g}", lambda g=g: google_trends(g)) for g in GOOGLE_GEOS]
    jobs += [(f"Reddit {r}", lambda r=r: reddit_rising(r)) for r in REDDIT_SUBS]
    return jobs
