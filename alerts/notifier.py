"""Notification integrations for alert-level changes."""

from __future__ import annotations

import json
from typing import Optional
from urllib.request import Request, urlopen


def _post_json(url: str, payload: dict, headers: Optional[dict] = None) -> None:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    if headers:
        for key, value in headers.items():
            request.add_header(key, value)
    with urlopen(request, timeout=20):
        pass


def send_telegram_message(bot_token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    _post_json(url, {"chat_id": chat_id, "text": message})


def create_github_issue(repo: str, token: str, title: str, body: str) -> None:
    url = f"https://api.github.com/repos/{repo}/issues"
    _post_json(url, {"title": title, "body": body}, headers={"Authorization": f"Bearer {token}"})
