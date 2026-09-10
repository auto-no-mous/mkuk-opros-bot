"""HTTP session on the stdlib only: cookies, gzip, retries, one identity per run.

A fresh Session is created for every survey run, which gives the same isolation
the throwaway browser profile used to: no cookies carry over between runs.
"""
from __future__ import annotations

import gzip
import http.cookiejar
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

TIMEOUT_SECONDS = 30
RETRIES = 3
RETRY_BACKOFF_SECONDS = 3

_CHARSET = re.compile(r"charset=([\w-]+)", re.I)
_META_CHARSET = re.compile(rb"<meta[^>]+charset=[\"']?([\w-]+)", re.I)


class NetworkError(RuntimeError):
    """A request failed after all retries."""


class Response:
    __slots__ = ("url", "status", "html")

    def __init__(self, url: str, status: int, html: str) -> None:
        self.url = url
        self.status = status
        self.html = html


def _decode_body(raw: bytes, headers) -> str:
    encoding = (headers.get("Content-Encoding") or "").lower()
    if encoding == "gzip":
        raw = gzip.decompress(raw)
    elif encoding == "deflate":
        # Servers disagree on whether "deflate" means zlib-wrapped or raw.
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)

    charset_match = _CHARSET.search(headers.get("Content-Type") or "")
    charset = charset_match.group(1) if charset_match else None
    if charset is None:
        meta_match = _META_CHARSET.search(raw[:4096])
        charset = meta_match.group(1).decode("ascii", "replace") if meta_match else "utf-8"
    try:
        return raw.decode(charset, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


class Session:
    def __init__(self, headers: dict = None, timeout: float = TIMEOUT_SECONDS) -> None:
        self.timeout = timeout
        self.headers = dict(headers or {})
        self.cookies = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )
        # urllib's default handlers add their own User-Agent; ours go on each
        # Request instead so they always win.
        self._opener.addheaders = []

    def get(self, url: str, referer: str = None) -> Response:
        return self._request(url, None, referer)

    def post(self, url: str, fields: dict, referer: str = None) -> Response:
        body = urllib.parse.urlencode(fields, encoding="utf-8").encode("utf-8")
        return self._request(url, body, referer)

    def _request(self, url: str, body: bytes, referer: str) -> Response:
        headers = dict(self.headers)
        if referer:
            headers["Referer"] = referer
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers["Origin"] = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(url))

        last_error = None
        for attempt in range(1, RETRIES + 1):
            request = urllib.request.Request(url, data=body, headers=headers)
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    raw = response.read()
                    return Response(
                        response.geturl(), response.status, _decode_body(raw, response.headers)
                    )
            except urllib.error.HTTPError as exc:
                # A 4xx/5xx is a real answer from the site, not a transport
                # problem -- retrying the same POST would just repeat it.
                raise NetworkError(f"Сервер ответил ошибкой {exc.code} на {url}") from exc
            except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError) as exc:
                last_error = exc
                if attempt < RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        raise NetworkError(
            f"Не удалось связаться с сайтом опроса за {RETRIES} попытки: {last_error}"
        )
