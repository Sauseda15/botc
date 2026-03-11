# views/base.py

import discord

class BaseView(discord.ui.View):
    def __init__(self, timeout: float = None):
        super().__init__(timeout=timeout)
        self.confirmed = None

    async def send_to(self, user, message: str):
        await user.send(message, view=self)
        await self.wait()

    async def get_selected_value(self, multi: bool = False):
        """
        Retrieves selected value(s) from the first child (usually a Select).
        """
        try:
            select = next(child for child in self.children if isinstance(child, discord.ui.Select))
            if multi:
                return select.values
            return select.values[0] if select.values else None
        except (StopIteration, AttributeError, IndexError):
            return None
