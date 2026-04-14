import asyncio
import os

import aiohttp

HEALTH_CHECK_ATTEMPTS = int(os.getenv("HEALTH_CHECK_ATTEMPTS", "3"))
HEALTH_CHECK_ATTEMPT_INTERVAL = int(os.getenv("HEALTH_CHECK_ATTEMPT_INTERVAL", "15"))

async def check_health(name, url):
    components = {}
    attempts = max(1, HEALTH_CHECK_ATTEMPTS)
    for attempt in range(attempts):
        if attempt > 0:
            await asyncio.sleep(HEALTH_CHECK_ATTEMPT_INTERVAL)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        continue
                    try:
                        data = await resp.json(content_type=None)
                    except Exception:
                        continue
                    components["service"] = data.get("status", "UNKNOWN")
                    details = data.get("details", {})
                    if isinstance(details, dict):
                        for component, info in details.items():
                            if isinstance(info, dict):
                                components[component] = info.get("status", "UNKNOWN")
                            else:
                                components[component] = "UNKNOWN"
                    return components
        except Exception:
            continue
    return {"service": "DOWN"}
