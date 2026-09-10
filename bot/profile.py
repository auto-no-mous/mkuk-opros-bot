"""Randomized request headers so each survey run looks like a different visitor."""
import random

# Each entry is one self-consistent identity: the client hints a real Chrome
# sends have to agree with its User-Agent, so they are chosen together rather
# than mixed at random.
IDENTITIES = [
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
        "platform": '"Windows"',
    },
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "platform": '"Windows"',
    },
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "platform": '"Windows"',
    },
    {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
        "platform": '"macOS"',
    },
    {
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
        "platform": '"Linux"',
    },
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
        "sec_ch_ua": None,  # Firefox sends no client hints
        "platform": None,
    },
]

ACCEPT_LANGUAGES = [
    "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "ru-RU,ru;q=0.9",
    "ru,en;q=0.9",
]

BASE_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"


def default_headers() -> dict:
    return random_headers(IDENTITIES[0], randomize=False)


def random_headers(identity: dict = None, randomize: bool = True) -> dict:
    identity = identity or random.choice(IDENTITIES)
    headers = {
        "User-Agent": identity["user_agent"],
        "Accept": BASE_ACCEPT,
        "Accept-Language": random.choice(ACCEPT_LANGUAGES) if randomize else ACCEPT_LANGUAGES[0],
        "Accept-Encoding": "gzip, deflate",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }
    if identity["sec_ch_ua"]:
        headers["sec-ch-ua"] = identity["sec_ch_ua"]
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = identity["platform"]
    return headers
