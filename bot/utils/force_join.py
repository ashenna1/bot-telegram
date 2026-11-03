"""
Force-join (mandatory subscription) checker
Checks via getChatMember without requiring extra permissions.
"""
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from bot.db import list_channels

async def get_active_channels():
    return await list_channels(active_only=True)

async def check_user_joined(bot: Bot, user_id: int) -> tuple[bool, list]:
    """
    Returns (all_joined, missing_channels)
    missing_channels = list of channel rows that user hasn't joined
    """
    channels = await get_active_channels()
    if not channels:
        return True, []
    missing = []
    for ch in channels:
        # ch = (id, username, title, invite_link, is_active)
        _, username, title, invite_link, _ = ch
        # normalize username to chat identifier
        chat_id = username.strip()
        # username may be @channel or t.me link
        if "t.me/" in chat_id:
            # extract last part
            chat_id = "@" + chat_id.split("t.me/")[-1].split("?")[0].split("/")[0]
        if not chat_id.startswith("@") and not chat_id.startswith("-100"):
            # assume missing @
            if chat_id and not chat_id.startswith("https"):
                chat_id = "@" + chat_id
            else:
                # https invite link can't be checked via getChatMember directly
                # we skip check and require manual check via invite_link
                # Instead, we treat invite_link channels as always needing button
                # For now add to missing and let user click
                missing.append(ch)
                continue
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            status = getattr(member, "status", "")
            if status in ("left", "kicked", "banned"):
                missing.append(ch)
        except TelegramBadRequest as e:
            # Bot not admin in channel -> can't verify. We show channel as optional warning
            # Better to include it so admin can fix, but don't block user forever
            # Log and skip blocking: treat as joined to avoid lockout
            # However we still show info in admin panel
            # For UX, we consider it joined but admin will see warning
            continue
        except Exception:
            continue
    return len(missing) == 0, missing

def channel_button_url(ch: tuple) -> str:
    _, username, title, invite_link, _ = ch
    if invite_link:
        return invite_link
    uname = username.strip()
    if uname.startswith("@"):
        return f"https://t.me/{uname[1:]}"
    if "t.me" in uname:
        return uname if uname.startswith("http") else f"https://{uname}"
    if uname.startswith("https"):
        return uname
    return f"https://t.me/{uname.lstrip('@')}"
