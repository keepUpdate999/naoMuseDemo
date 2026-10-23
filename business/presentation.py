"""Bounded visual pacing around actual Playwright actions; never retries actions."""
from pathlib import Path

SCRIPT=(Path(__file__).with_name('action_overlay.js')).read_text(encoding='utf-8')


class ActionPresenter:
    def __init__(self, enabled=True):self.enabled=enabled

    async def show(self, page, label, kind='transition', box=None):
        if not self.enabled:return
        try:await page.evaluate(SCRIPT,{'label':label,'kind':kind,'box':box})
        except Exception:pass  # An unavailable visual layer cannot replay or fail a business action.

    async def before(self, page, locator, label):
        if not self.enabled:return None
        try:
            # Keep the real target visible; never click the overlay or intercept page input.
            await locator.scroll_into_view_if_needed(timeout=5000)
            box=await locator.bounding_box()
            await self.show(page,'正在'+label,'target',box)
            await page.wait_for_timeout(340)
            return box
        except Exception:return None

    async def after(self, page, label, box=None):
        if not self.enabled:return
        await self.show(page,'已完成'+label,'complete',box)
        await page.wait_for_timeout(260)

    async def transition(self, page, label):
        if not self.enabled:return
        await self.show(page,label)
        await page.wait_for_timeout(280)
