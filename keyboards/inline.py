from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ─── Premium emoji IDs ────────────────────────────────────────────────────────
_E = {
    "settings":   "5870982283724328568",
    "profile":    "5870994129244131212",
    "people":     "5870772616305839506",
    "person_ok":  "5891207662678317861",
    "person_no":  "5893192487324880883",
    "file":       "5870528606328852614",
    "stats":      "5870921681735781843",
    "growth":     "5870930636742595124",
    "lock":       "6037249452824072506",
    "unlock":     "6037496202990194718",
    "megaphone":  "6039422865189638057",
    "check":      "5870633910337015697",
    "cross":      "5870657884844462243",
    "pencil":     "5870676941614354370",
    "trash":      "5870875489362513438",
    "info":       "6028435952299413210",
    "bot":        "6030400221232501136",
    "eye":        "6037397706505195857",
    "bell":       "6039486778597970865",
    "refresh":    "5345906554510012647",
    "money":      "5904462880941545555",
    "calendar":   "5890937706803894250",
    "tag":        "5886285355279193209",
    "write":      "5870753782874246579",
    "home":       "5873147866364514353",
    "link":       "5769289093221454192",
    "gift":       "6032644646587338669",
    "clock":      "5983150113483134607",
    "party":      "6041731551845159060",
    "send_up":    "5963103826075456248",
    "download":   "6039802767931871481",
    "box":        "5884479287171485878",
}


def _btn(text: str, eid: str = None, **kwargs) -> InlineKeyboardButton:
    """Create InlineKeyboardButton with optional premium emoji icon."""
    if eid:
        return InlineKeyboardButton(text=text, icon_custom_emoji_id=eid, **kwargs)
    return InlineKeyboardButton(text=text, **kwargs)


# ─── Main menu ────────────────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        _btn("Прогрев", _E["send_up"], callback_data="warmup_menu"),
        _btn("Как работает", _E["info"], callback_data="how_it_works"),
    )
    return b.as_markup()


def _back_btn(to: str = "main_menu") -> InlineKeyboardButton:
    return InlineKeyboardButton(text="◁ Назад", callback_data=to)


# ─── Subscription gate ────────────────────────────────────────────────────────

def _pf_link(sponsor: dict) -> str:
    return (
        sponsor.get("link")
        or sponsor.get("channel_link")
        or sponsor.get("url")
        or sponsor.get("channel")
        or ""
    )


def _pf_title(sponsor: dict) -> str:
    return (
        sponsor.get("title")
        or sponsor.get("name")
        or sponsor.get("channel_name")
        or sponsor.get("channel_title")
        or ""
    )


def _ch_url(channel_id: str) -> str:
    if channel_id.startswith("http"):
        return channel_id
    stripped = channel_id.lstrip("@")
    if stripped.lstrip("-").isdigit():
        return f"https://t.me/c/{stripped.lstrip('-100')}"
    return f"https://t.me/{stripped}"


def subscription_check_keyboard(
    pf_sponsors: list,
    mandatory: list,
    check_cb: str = "check_sub_start",
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for sponsor in pf_sponsors:
        link = _pf_link(sponsor)
        title = _pf_title(sponsor) or "Спонсор"
        if link:
            b.row(_btn(title, _E["megaphone"], url=link))
    for ch in mandatory:
        title = ch.channel_title or ch.channel_id
        b.row(_btn(title, _E["megaphone"], url=_ch_url(ch.channel_id)))
    b.row(_btn("Я подписался", _E["check"], callback_data=check_cb))
    return b.as_markup()


# ─── Warmup menu ──────────────────────────────────────────────────────────────

def warmup_menu_keyboard(accounts: list, active_ids: set) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for acc in accounts:
        eid = _E["check"] if acc.id in active_ids else _E["clock"]
        b.row(_btn(acc.phone, eid, callback_data=f"account_detail:{acc.id}"))
    b.row(_btn("Добавить аккаунт", _E["send_up"], callback_data="add_account"))
    b.row(_back_btn("main_menu"))
    return b.as_markup()


def account_detail_keyboard(account_id: int, status: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if status in ("paused", "pending", "error"):
        b.row(_btn("Запустить прогрев", _E["send_up"], callback_data=f"warmup_start:{account_id}"))
    elif status == "active":
        b.row(_btn("Остановить прогрев", _E["clock"], callback_data=f"warmup_stop:{account_id}"))
    b.row(
        _btn("Профиль", _E["profile"], callback_data=f"profile:{account_id}"),
        _btn("История", _E["file"], callback_data=f"history:{account_id}:0"),
    )
    b.row(_btn("Удалить", _E["trash"], callback_data=f"account_delete_confirm:{account_id}"))
    b.row(_back_btn("warmup_menu"))
    return b.as_markup()


def confirm_delete_keyboard(account_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        _btn("Да, удалить", _E["check"], callback_data=f"account_delete:{account_id}"),
        _btn("Отмена", _E["cross"], callback_data=f"account_detail:{account_id}"),
    )
    return b.as_markup()


# ─── Profile ──────────────────────────────────────────────────────────────────

def profile_keyboard(account_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        _btn("Обновить", _E["refresh"], callback_data=f"profile:{account_id}"),
        _btn("История", _E["file"], callback_data=f"history:{account_id}:0"),
    )
    b.row(_back_btn(f"account_detail:{account_id}"))
    return b.as_markup()


# ─── History ──────────────────────────────────────────────────────────────────

def history_keyboard(account_id: int, offset: int, total: int, page_size: int = 10) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    nav = []
    if offset > 0:
        nav.append(_btn(
            "Пред.",
            _E["download"],
            callback_data=f"history:{account_id}:{max(0, offset - page_size)}",
        ))
    if offset + page_size < total:
        nav.append(_btn(
            "След.",
            _E["send_up"],
            callback_data=f"history:{account_id}:{offset + page_size}",
        ))
    if nav:
        b.row(*nav)
    b.row(_back_btn(f"account_detail:{account_id}"))
    return b.as_markup()


# ─── Admin ────────────────────────────────────────────────────────────────────

def admin_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        _btn("Пользователи", _E["people"], callback_data="admin_users"),
        _btn("Статистика",   _E["stats"],  callback_data="admin_stats"),
    )
    b.row(
        _btn("Лимиты",    _E["settings"],  callback_data="admin_limits"),
        _btn("Рассылка",  _E["megaphone"], callback_data="admin_broadcast"),
    )
    b.row(
        _btn("Аккаунты",     _E["refresh"], callback_data="admin_accounts"),
        _btn("Обяз. каналы", _E["lock"],    callback_data="admin_mandatory"),
    )
    b.row(_back_btn("main_menu"))
    return b.as_markup()


def admin_mandatory_keyboard(channels: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        title = ch.channel_title or ch.channel_id
        b.row(
            _btn(title, _E["megaphone"], callback_data=f"mandatory_info:{ch.channel_id}"),
            _btn("Удалить", _E["trash"], callback_data=f"mandatory_remove:{ch.channel_id}"),
        )
    b.row(_btn("Добавить канал", _E["send_up"], callback_data="mandatory_add"))
    b.row(_back_btn("admin_menu"))
    return b.as_markup()


def admin_limits_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_back_btn("admin_menu"))
    return b.as_markup()


def cancel_keyboard(back_to: str = "main_menu") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("Отмена", _E["cross"], callback_data=back_to))
    return b.as_markup()


def skip_api_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_btn("Отмена", _E["cross"], callback_data="warmup_menu"))
    return b.as_markup()
