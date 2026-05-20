import json
import os
import re
import smtplib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Set, Tuple

import feedparser
import requests

KEYWORDS = ["식품", "표시", "광고", "화장품", "인체"]

RSS_CONFIG = [
    {
        "name": "입법/행정예고",
        "url": "http://www.mfds.go.kr/www/rss/brd.do?brdId=data0009",
        "keyword_filter": True,
    },
    {
        "name": "제·개정고시",
        "url": "http://www.mfds.go.kr/www/rss/brd.do?brdId=data0008",
        "keyword_filter": True,
    },
    {
        "name": "법, 시행령, 시행규칙",
        "url": "http://www.mfds.go.kr/www/rss/brd.do?brdId=data0003",
        "keyword_filter": True,
    },
    {
        "name": "본회의 통과 식의약 법률",
        "url": "http://www.mfds.go.kr/www/rss/brd.do?brdId=relaw0001",
        "keyword_filter": False,
    },
]

SENT_FILE = Path("sent_items.json")
SUBJECT = "[식약처 법령 알림] 신규 법령정보 감지"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 20
REQUEST_RETRIES = 3


@dataclass
class MatchedItem:
    title: str
    published: str
    link: str
    matched_keywords: List[str]


def load_sent_items() -> Set[str]:
    if not SENT_FILE.exists():
        return set()
    try:
        with SENT_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return set(data)
    except (json.JSONDecodeError, OSError):
        pass
    return set()


def save_sent_items(items: Set[str]) -> None:
    with SENT_FILE.open("w", encoding="utf-8") as f:
        json.dump(sorted(items), f, ensure_ascii=False, indent=2)


def get_entry_id(entry: feedparser.FeedParserDict) -> str:
    return entry.get("link") or entry.get("id") or entry.get("guid") or ""


def extract_text(entry: feedparser.FeedParserDict) -> str:
    parts = [entry.get("title", ""), entry.get("summary", ""), entry.get("description", "")]
    return " ".join(parts)


def find_keywords(text: str) -> List[str]:
    found = []
    for keyword in KEYWORDS:
        if re.search(re.escape(keyword), text, re.IGNORECASE):
            found.append(keyword)
    return found


def fetch_feed_content(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            last_error = exc
            if attempt < REQUEST_RETRIES:
                time.sleep(1)
    raise RuntimeError(f"RSS 요청 실패: {url}") from last_error


def parse_feed(url: str, keyword_filter: bool, sent_items: Set[str]) -> Tuple[List[MatchedItem], Set[str], bool]:
    # Feed fetch/parse failures are isolated per RSS source to keep the full run alive.
    try:
        content = fetch_feed_content(url)
        parsed = feedparser.parse(content)
    except Exception as exc:
        print(f"RSS 수집 실패 ({url}): {exc}")
        return [], set(), True

    new_ids: Set[str] = set()
    matched_items: List[MatchedItem] = []

    for entry in parsed.entries:
        item_id = get_entry_id(entry)
        if not item_id or item_id in sent_items:
            continue

        text = extract_text(entry)
        matched_keywords = find_keywords(text)

        if keyword_filter and not matched_keywords:
            continue

        matched_items.append(
            MatchedItem(
                title=entry.get("title", "(제목 없음)"),
                published=entry.get("published", entry.get("updated", "등록일 정보 없음")),
                link=entry.get("link", ""),
                matched_keywords=matched_keywords,
            )
        )
        new_ids.add(item_id)

    return matched_items, new_ids, False


def build_email_body(results: Dict[str, List[MatchedItem]], failed_feeds: Set[str]) -> str:
    lines: List[str] = []
    lines.append("식품의약품안전처 법령정보 RSS 모니터링 결과입니다.")
    lines.append("")

    for idx, config in enumerate(RSS_CONFIG, start=1):
        name = config["name"]
        items = results[name]
        lines.append(f"{idx}. {name}")

        if name in failed_feeds:
            lines.append("- 수집 실패")
            lines.append("")
            continue

        if config["keyword_filter"]:
            if items:
                unique_keywords = sorted({k for item in items for k in item.matched_keywords})
                lines.append("- 키워드 감지 결과: 있음")
                lines.append(f"- 감지 키워드: {', '.join(unique_keywords)}")
                lines.append("- 게시물:")
                for i, item in enumerate(items, start=1):
                    lines.append(f"  {i}) {item.title}")
                    lines.append(f"     등록일: {item.published}")
                    lines.append(f"     링크: {item.link}")
                    lines.append(f"     매칭 키워드: {', '.join(item.matched_keywords)}")
            else:
                lines.append("- 키워드 감지 결과: 없음")
        else:
            if items:
                lines.append("- 신규 업로드 게시물: 있음")
                lines.append("- 게시물:")
                for i, item in enumerate(items, start=1):
                    lines.append(f"  {i}) {item.title}")
                    lines.append(f"     등록일: {item.published}")
                    lines.append(f"     링크: {item.link}")
            else:
                lines.append("- 신규 업로드 게시물: 없음")

        lines.append("")

    return "\n".join(lines).strip()


def send_email(subject: str, body: str) -> None:
    email_user = os.environ["EMAIL_USER"]
    email_password = os.environ["EMAIL_PASSWORD"]
    email_to = os.environ["EMAIL_TO"]

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = email_to

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(email_user, email_password)
        server.send_message(msg)


def main() -> None:
    sent_items = load_sent_items()
    results: Dict[str, List[MatchedItem]] = {}
    ids_to_add: Set[str] = set()
    failed_feeds: Set[str] = set()

    for config in RSS_CONFIG:
        items, ids, failed = parse_feed(config["url"], config["keyword_filter"], sent_items)
        results[config["name"]] = items
        ids_to_add.update(ids)
        if failed:
            failed_feeds.add(config["name"])

    total_new = sum(len(v) for v in results.values())
    should_send = total_new > 0 or bool(failed_feeds)
    if not should_send:
        print(f"{datetime.now(timezone.utc).isoformat()} - 신규 감지 항목 없음. 메일 미발송")
        return

    body = build_email_body(results, failed_feeds)
    send_email(SUBJECT, body)
    save_sent_items(sent_items.union(ids_to_add))
    print(
        f"{datetime.now(timezone.utc).isoformat()} - 메일 발송 완료 "
        f"(신규 {total_new}건, 수집 실패 {len(failed_feeds)}건)"
    )


if __name__ == "__main__":
    main()
