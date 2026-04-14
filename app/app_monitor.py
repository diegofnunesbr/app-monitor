import asyncio
import logging
import os
from collections import defaultdict

import aiohttp

from config_loader import load_services
from health_checker import check_health

TEAMS_WEBHOOK = os.getenv("TEAMS_WEBHOOK")
TEAMS_WEBHOOK_MAX_RETRIES = int(os.getenv("TEAMS_WEBHOOK_MAX_RETRIES", "3"))
TEAMS_WEBHOOK_TIMEOUT_SECONDS = float(os.getenv("TEAMS_WEBHOOK_TIMEOUT_SECONDS", "10"))
TEAMS_WEBHOOK_RETRY_BACKOFF_SECONDS = float(os.getenv("TEAMS_WEBHOOK_RETRY_BACKOFF_SECONDS", "1"))
MAX_CONCURRENT_CHECKS = int(os.getenv("MAX_CONCURRENT_CHECKS", "100"))
NON_PROD_ALERT_THRESHOLD = int(os.getenv("NON_PROD_ALERT_THRESHOLD", "5"))
DOWN_THRESHOLD = int(os.getenv("DOWN_THRESHOLD", "2"))

_NON_PROD_ENV_LABELS = frozenset({"qa", "stg", "dev"})
_SPECIAL_NON_PROD_FIRST_LABELS = frozenset({
    "master",
    "source360-dev",
    "source360-qua",
    "trial",
})

def is_non_prod(name):
    n = name.lower().strip()
    labels = [p for p in n.split(".") if p]
    if not labels:
        return False
    if any(label in _NON_PROD_ENV_LABELS for label in labels):
        return True
    if labels[0] in _SPECIAL_NON_PROD_FIRST_LABELS:
        return True
    return False

UP_THRESHOLD = 1

def build_teams_list_message(header_line, sorted_names):
    parts = header_line.split(maxsplit=1)
    if len(parts) == 2:
        title = f"{parts[0]} **{parts[1]}**"
    else:
        title = f"**{header_line}**"
    lines = [title, ""]
    for name in sorted_names:
        lines.append(f"- {name}")
    return "\n".join(lines)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

last_state = {}
failure_count = defaultdict(int)
success_count = defaultdict(int)

async def post_teams(body):
    if not TEAMS_WEBHOOK:
        return
    max_retries = max(1, TEAMS_WEBHOOK_MAX_RETRIES)
    timeout = aiohttp.ClientTimeout(total=TEAMS_WEBHOOK_TIMEOUT_SECONDS)
    last_error = None
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(max_retries):
            try:
                async with session.post(TEAMS_WEBHOOK, json=body) as resp:
                    body_text = await resp.text()
                    if 200 <= resp.status < 300:
                        if attempt > 0:
                            logging.info(
                                f"Teams webhook succeeded on attempt {attempt + 1}/{max_retries}"
                            )
                        return
                    last_error = f"HTTP {resp.status}"
                    if body_text:
                        last_error += f" body={body_text[:500]}"
            except asyncio.TimeoutError as e:
                last_error = f"TimeoutError: {e}"
            except aiohttp.ClientError as e:
                last_error = f"{type(e).__name__}: {e}"
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
            if attempt < max_retries - 1:
                delay = TEAMS_WEBHOOK_RETRY_BACKOFF_SECONDS * (2**attempt)
                logging.warning(
                    f"Teams webhook attempt {attempt + 1}/{max_retries} failed: {last_error}; "
                    f"retry in {delay:.1f}s"
                )
                await asyncio.sleep(delay)
            else:
                logging.error(
                    f"Teams webhook failed after {max_retries} attempts: {last_error}"
                )

async def send_teams_text(text):
    await post_teams({"text": text})

async def send_teams_down(emoji, count, env_display, sorted_apps):
    header = f"{emoji} {count} aplicações DOWN ({env_display})"
    await send_teams_text(build_teams_list_message(header, sorted_apps))

async def send_teams_up(emoji, count, env_display, sorted_names):
    header = f"{emoji} {count} aplicações UP ({env_display})"
    await send_teams_text(build_teams_list_message(header, sorted_names))

async def monitor_service(service, events, semaphore):
    name = service["name"]
    url = service["url"]
    try:
        async with semaphore:
            result = await check_health(name, url)
        for component, status in result.items():
            key = f"{name}:{component}"
            previous = last_state.get(key)
            if component != "service":
                if previous is None:
                    last_state[key] = status
                    logging.info(f"{name} {component} {status}")
                elif previous != status:
                    last_state[key] = status
                    logging.info(f"{name} {component} {status}")
                continue
            if status == "DOWN":
                failure_count[name] += 1
                success_count[name] = 0
                if failure_count[name] >= DOWN_THRESHOLD:
                    if previous != "DOWN":
                        last_state[key] = "DOWN"
                        logging.error(f"{name} service DOWN")
                        events["down"].add(name)
            else:
                success_count[name] += 1
                failure_count[name] = 0
                if success_count[name] >= UP_THRESHOLD:
                    if previous != "UP":
                        last_state[key] = "UP"
                        logging.info(f"{name} service UP")
                        events["up"].add(name)
    except Exception as e:
        failure_count[name] += 1
        success_count[name] = 0
        if failure_count[name] >= DOWN_THRESHOLD:
            logging.error(f"{name} unreachable: {e}")
            events["down"].add(name)

async def monitor_cycle(services):
    events = {
        "up": set(),
        "down": set(),
    }
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
    tasks = [
        asyncio.create_task(monitor_service(service, events, semaphore))
        for service in services
    ]
    await asyncio.gather(*tasks)
    down_prod = [n for n in events["down"] if not is_non_prod(n)]
    down_non_prod = [n for n in events["down"] if is_non_prod(n)]
    up_prod = [n for n in events["up"] if not is_non_prod(n)]
    up_non_prod = [n for n in events["up"] if is_non_prod(n)]
    if down_prod:
        await send_teams_down(
            "🔴",
            len(down_prod),
            "prod",
            sorted(down_prod),
        )
    if down_non_prod and len(down_non_prod) >= NON_PROD_ALERT_THRESHOLD:
        await send_teams_down(
            "🟠",
            len(down_non_prod),
            "qa/stg/dev",
            sorted(down_non_prod),
        )
    if up_prod:
        await send_teams_up(
            "🟢",
            len(up_prod),
            "prod",
            sorted(up_prod),
        )
    if up_non_prod and len(up_non_prod) >= NON_PROD_ALERT_THRESHOLD:
        await send_teams_up(
            "🟢",
            len(up_non_prod),
            "qa/stg/dev",
            sorted(up_non_prod),
        )

async def main():
    services = load_services()
    logging.info(
        f"Loaded {len(services)} services "
        f"(max concurrent: {MAX_CONCURRENT_CHECKS}, down threshold: {DOWN_THRESHOLD})"
    )
    if not services:
        logging.warning("No services configured; monitor loop is idle")
    while True:
        await monitor_cycle(services)

if __name__ == "__main__":
    asyncio.run(main())
