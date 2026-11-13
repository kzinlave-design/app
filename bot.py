"""
Бот аренды Telegram-активов + покупка Telegram Premium за TON.
Логика бота. Экспортирует init_bot_and_loop() для app.py (Flask).
"""
import asyncio, os, io, json, time, secrets, random, zlib, threading, logging  # === НОВОЕ: threading, logging ===
from urllib.parse import quote
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton as B, BufferedInputFile, Update)  # === НОВОЕ: Update ===

# ============ НАСТРОЙКИ ============
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "8708165470,8586156220").split(",") if x.strip()]
WALLET    = os.getenv("WALLET", "UQCEI8wLYKGYmARvvyWKc_QGhYu5nVbT3UrqipjVGrZxVCdQ")
DAY_RATE = 0.08
MIN_DAY_PRICE = 0.1
NUMBER_TIERS = {1: 6.0, 7: 20.0, 30: 50.0, 365: 400.0}
PRICE_OFFSETS = [0.0, 0.3, 0.7, 1.1, 1.4, 1.8]
NUMBER_DAY_OVERRIDE = {}
BEAUTY_BONUS = {1: 2.0, 2: 3.0}
PAGE = 8
DAY_OPTIONS = [1, 3, 7, 14, 30]

PREMIUM_BASE = {3: 10.0, 6: 17.0, 12: 28.0}
PREMIUM_MARKUP = 1.05

STARS_BASE = {50: 1.0, 100: 1.9, 250: 4.5, 500: 8.5, 1000: 16.0}
STARS_MARKUP = 1.05

TRANSFER_DESC = "Оплата заказа"

EXTRA_BACKGROUNDS = {f"Black Fon {i:02d}": p for i, p in
                     zip(range(1, 9), [4.0, 4.0, 5.0, 5.0, 6.0, 6.0, 8.0, 10.0])}

EXTRA_GIFTS = {
    "Homemade Cake": 3.0, "Jelly Bunny": 2.0, "Spiced Wine": 3.0, "Santa Hat": 2.0,
    "Candy Cane": 2.0, "Cookie Heart": 2.5, "B-Day Candle": 2.0, "Desk Calendar": 3.0,
    "Fresh Socks": 2.5, "Tama Gadget": 2.0,
}
GIFT_INFO = {
    "Homemade Cake": (1001, "Розовый"), "Jelly Bunny": (1002, "Зелёный"),
    "Spiced Wine": (1003, "Бордовый"), "Santa Hat": (1004, "Красный"),
    "Candy Cane": (1005, "Полосатый"), "Cookie Heart": (1006, "Коричневый"),
    "B-Day Candle": (1007, "Золотой"), "Desk Calendar": (1008, "Голубой"),
    "Fresh Socks": (1009, "Фиолетовый"), "Tama Gadget": (1010, "Бирюзовый"),
    "Black Fon 01": (2001, "Чёрный"), "Black Fon 02": (2002, "Угольный"),
    "Black Fon 03": (2003, "Графитовый"), "Black Fon 04": (2004, "Антрацит"),
    "Black Fon 05": (2005, "Смоляной"), "Black Fon 06": (2006, "Вороной"),
    "Black Fon 07": (2007, "Ночной"), "Black Fon 08": (2008, "Полуночный"),
}

EXTRA_USERNAMES = {"@ppwph": 7.0, "@narkosave": 7.0, "@sheikhart": 7.0, "@neuralink_clincal": 7.0}
EXTRA_NUMBERS = {"+888 0976 2134": 3000, "+888 0157 9623": 3000, "+888 0159 6427": 3000,
                 "+888 0750 2195": 3000, "+888 0436 1579": 3000, "+888 0153 2647": 3000}

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "state.json")
CATS = {"u": "Юзернеймы", "n": "Номера +888", "g": "NFT-подарки"}
ICON = {"u": "👤", "n": "📞", "g": "🎁"}
ITEMS = {"u": [], "n": [], "g": []}
RENTED = {}
ORDERS = {}

TERMS = (
    "<b>Условия аренды</b>\n\n"
    "• Цена зависит от срока (у номеров есть тарифы на день, неделю, месяц и год), сумма видна до оплаты.\n"
    "• После оплаты владелец вручную выдаёт актив и сообщает вам.\n"
    "• По окончании срока актив нужно вернуть владельцу.\n"
    "• Пока лот в аренде, он отмечен ⛔ и недоступен другим.\n"
    "• Платёж в TON не возвращается автоматически.\n\n"
    "<b>Premium</b>: владелец покупает подписку на Fragment и отправляет её на ваш @username."
)

# ============ БАЗА ============
def load_db(path=os.path.join(HERE, "rentdb.txt")):
    if not os.path.exists(path):
        logging.warning("rentdb.txt not found at %s", path)
        return
    sec = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("==="):
                sec = "u" if "ЮЗЕР" in line else "n" if "НОМЕР" in line else "b" if "ФОН" in line else "g"
                continue
            p = line.split("\t")
            if sec == "u" and len(p) == 2 and p[0].startswith("@"):
                ITEMS["u"].append({"name": p[0], "price": float(p[1])})
            elif sec == "n" and len(p) == 2 and p[0].startswith("+888"):
                v = p[1].replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
                ITEMS["n"].append({"name": p[0], "price": float(v), **number_data(p[0])})
            elif sec == "b" and len(p) == 2 and p[0].strip():
                ITEMS["g"].append({"name": p[0].strip(), "price": float(p[1]), "black": True})
            elif sec == "g" and len(p) >= 2 and "#" in p[0]:
                try:
                    price = float(p[1])
                except ValueError:
                    continue
                n, num = p[0].rsplit("#", 1)
                slug = n.strip().replace(" ", "")
                ITEMS["g"].append({
                    "name": p[0], "price": price, "gid": num.strip(),
                    "color": p[2].strip() if len(p) >= 3 and p[2].strip() else None,
                    "link": f"https://t.me/nft/{slug}-{num}",
                    "img": f"https://nft.fragment.com/gift/{slug.lower()}-{num}.medium.jpg"})
    for k, v in EXTRA_USERNAMES.items():
        if k not in {i["name"] for i in ITEMS["u"]}:
            ITEMS["u"].append({"name": k, "price": v})
    for k, v in EXTRA_NUMBERS.items():
        if k not in {i["name"] for i in ITEMS["n"]}:
            ITEMS["n"].append({"name": k, "price": float(v), **number_data(k)})
    for k, v in EXTRA_BACKGROUNDS.items():
        if k not in {i["name"] for i in ITEMS["g"]}:
            gid, color = GIFT_INFO.get(k, (None, None))
            ITEMS["g"].append({"name": k, "price": v, "black": True, "gid": gid, "color": color})
    for k, v in EXTRA_GIFTS.items():
        if k not in {i["name"] for i in ITEMS["g"]}:
            gid, color = GIFT_INFO.get(k, (None, None))
            ITEMS["g"].append({"name": k, "price": v, "gid": gid, "color": color})
    apply_number_prices()
    for c in ITEMS:
        ITEMS[c].sort(key=lambda x: (day_price(x), x["price"]))


def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"orders": ORDERS, "rented": RENTED}, f, ensure_ascii=False)
    except Exception:
        logging.exception("save_state failed")


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            d = json.load(open(STATE_FILE, encoding="utf-8"))
            ORDERS.update(d.get("orders", {}))
            RENTED.update(d.get("rented", {}))
        except Exception:
            logging.exception("load_state failed")


def beauty_level(num):
    d = "".join(ch for ch in num if ch.isdigit())[3:]
    if len(d) < 4:
        return 0
    runs = [d[i:i + 4] for i in range(len(d) - 3)]
    four_same = any(len(set(x)) == 1 for x in runs)
    four_seq = any(all(int(x[j + 1]) - int(x[j]) == 1 for j in range(3)) or
                   all(int(x[j]) - int(x[j + 1]) == 1 for j in range(3)) for x in runs)
    abab = any(x[0] == x[2] and x[1] == x[3] and x[0] != x[1] for x in runs)
    pal = d == d[::-1]
    most = max(d.count(c) for c in set(d))
    if four_same or four_seq or pal or most >= 5:
        return 2
    three = [d[i:i + 3] for i in range(len(d) - 2)]
    three_same = any(len(set(x)) == 1 for x in three)
    three_seq = any((int(x[1]) - int(x[0]) == int(x[2]) - int(x[1]) == 1) or
                    (int(x[0]) - int(x[1]) == int(x[1]) - int(x[2]) == 1) for x in three)
    pair2 = any(d[i:i + 2] == d[i + 2:i + 4] for i in range(len(d) - 3))
    if three_same or three_seq or abab or pair2 or most == 4:
        return 1
    return 0


def number_data(num):
    lvl = beauty_level(num)
    bonus = BEAUTY_BONUS.get(lvl, 0.0)
    return {"tiers": {d: p + bonus for d, p in NUMBER_TIERS.items()}, "beauty": lvl}


def apply_number_prices():
    nums = sorted(ITEMS["n"], key=lambda x: x["name"])
    rnd = random.Random(2026)
    i, prev, used = 0, None, {}
    while i < len(nums):
        size = rnd.randint(2, 5)
        if len(nums) - i - size == 1:
            size = size - 1 if size > 2 else size + 1
        ok = [o for o in PRICE_OFFSETS if o != prev and used.get(o, 0) + size <= 5]
        off = rnd.choice(ok) if ok else min((o for o in PRICE_OFFSETS if o != prev), key=lambda o: used.get(o, 0))
        prev = off
        used[off] = used.get(off, 0) + size
        for it in nums[i:i + size]:
            day = NUMBER_DAY_OVERRIDE.get(it["name"], NUMBER_TIERS[1] + off)
            k = day / NUMBER_TIERS[1]
            bonus = BEAUTY_BONUS.get(it.get("beauty", 0), 0.0)
            t = {d: round(p * k, 1) for d, p in NUMBER_TIERS.items()}
            t[365] = round(NUMBER_TIERS[365] + (day - NUMBER_TIERS[1]) * 5, 1)
            it["tiers"] = {d: round(p + bonus, 1) for d, p in t.items()}
        i += size


def num_cost(tiers, days):
    INF = float("inf")
    dp = [0.0] + [INF] * days
    for i in range(1, days + 1):
        for d, p in tiers.items():
            dp[i] = min(dp[i], dp[max(0, i - d)] + p)
    return dp[days]


def day_price(it):
    if it.get("tiers"):
        return it["tiers"][1]
    return round(max(it["price"] * DAY_RATE, MIN_DAY_PRICE), 2)


def rent_total(it, days):
    if it.get("tiers"):
        return round(num_cost(it["tiers"], days), 2)
    return round(day_price(it) * days, 2)


def prem_price(m):    return round(PREMIUM_BASE[m] * PREMIUM_MARKUP, 2)
def stars_price(n):   return round(STARS_BASE[n] * STARS_MARKUP, 2)


def price_line(it):
    if it.get("tiers"):
        t = it["tiers"]
        star = "✨ Красивый номер\n" if it.get("beauty") else ""
        return (f"{star}День: <b>{fmt(t[1])}</b> · Неделя: <b>{fmt(t[7])}</b> · "
                f"Месяц: <b>{fmt(t[30])}</b> · Год: <b>{fmt(t[365])}</b> TON")
    return f"Цена: <b>{fmt(day_price(it))} TON</b>/сутки"


def fmt(x):        return f"{x:.2f}".rstrip("0").rstrip(".")
def is_busy(name): return name in RENTED
def find(cat, name):
    return next((i for i in ITEMS[cat] if i["name"] == name), None)


# ============ КАРТИНКИ ============
PALETTES = [((255, 94, 98), (255, 195, 113)), ((106, 17, 203), (37, 117, 252)),
            ((0, 198, 255), (0, 114, 255)), ((17, 153, 142), (56, 239, 125)),
            ((238, 9, 121), (255, 106, 0)), ((120, 75, 160), (43, 134, 197)),
            ((252, 70, 107), (63, 94, 251)), ((255, 175, 189), (255, 195, 160))]
FONTS = ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "Arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
_cache = {}

def font(size):
    for f in FONTS:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()

def ctext(d, cx, cy, text, fnt, fill):
    l, t, r, b = d.textbbox((0, 0), text, font=fnt)
    d.text((cx - (r - l) / 2 - l, cy - (b - t) / 2 - t), text, font=fnt, fill=fill)

def fit(d, text, max_w, start):
    s = start
    while s > 28:
        f = font(s)
        l, _, r, _ = d.textbbox((0, 0), text, font=f)
        if r - l <= max_w:
            return f
        s -= 4
    return font(28)

def star(d, cx, cy, R, fill):
    import math
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = R if i % 2 == 0 else R * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)

BLACK_PALETTE = ((0, 0, 0), (60, 60, 66))

def make_card(title, line2, badge, seed, glyph, is_star=False, black=False):
    W = H = 900
    rnd = random.Random(seed)
    c1, c2 = BLACK_PALETTE if black else PALETTES[rnd.randrange(len(PALETTES))]
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    img = img.convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for _ in range(8):
        rr = rnd.randint(90, 280)
        x, y = rnd.randint(-60, W), rnd.randint(-60, H)
        od.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(255, 255, 255, rnd.randint(16, 42)))
    img = Image.alpha_composite(img, ov.filter(ImageFilter.GaussianBlur(8)))
    glass = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glass).rounded_rectangle([60, 60, W - 60, H - 60], radius=64,
                                            fill=(255, 255, 255, 38), outline=(255, 255, 255, 140), width=3)
    img = Image.alpha_composite(img, glass)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([W // 2 - 150, 205, W // 2 + 150, 525], fill=(0, 0, 0, 70))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(img)
    cx, cy = W // 2, 340
    d.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], fill=(255, 255, 255, 245))
    d.ellipse([cx - 128, cy - 128, cx + 128, cy + 128], outline=c1 + (255,), width=6)
    if is_star:
        star(d, cx, cy + 6, 105, c2 + (255,))
    else:
        ctext(d, cx, cy, glyph, fit(d, glyph, 220, 150), c2 + (255,))
    ctext(d, cx, 600, title, fit(d, title, W - 190, 78), (255, 255, 255, 255))
    if line2:
        ctext(d, cx, 680, line2, font(44), (255, 255, 255, 230))
    bw = 330
    d.rounded_rectangle([cx - bw // 2, 740, cx + bw // 2, 815], radius=38, fill=(255, 255, 255, 235))
    ctext(d, cx, 778, badge, font(36), c2 + (255,))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=92)
    return buf.getvalue()

def cached(key, fn):
    if key not in _cache:
        _cache[key] = fn()
    return _cache[key]

def photo_file(key, fn):
    return BufferedInputFile(cached(key, fn), filename="card.jpg")

def img_main():   return photo_file("main", lambda: make_card("Galaxy Rent", "Аренда • Premium", "TON", 7, "R"))
def img_cat(cat):
    g = {"u": "@", "n": "+888", "g": "G"}[cat]
    return photo_file("cat" + cat, lambda: make_card(CATS[cat], f"{len(ITEMS[cat])} лотов", "КАТАЛОГ", ord(cat), g))
def img_item(cat, it):
    g = {"u": "@", "n": "888", "g": it["name"][:1]}[cat]
    sub = f"{fmt(day_price(it))} TON / сутки"
    return photo_file("it" + it["name"], lambda: make_card(it["name"], sub, "АРЕНДА",
                                                           zlib.crc32(it["name"].encode()) % 997, g,
                                                           black=it.get("black", False)))
def img_premium(m=None):
    t = "Telegram Premium"
    sub = f"{m} мес. — {fmt(prem_price(m))} TON" if m else "3 • 6 • 12 месяцев"
    return photo_file(f"pm{m}", lambda: make_card(t, sub, "PREMIUM", 11 + (m or 0), "", True))
def img_stars(n=None):
    sub = f"{n} ⭐ — {fmt(stars_price(n))} TON" if n else "50 • 100 • 250 • 500 • 1000"
    return photo_file(f"st{n}", lambda: make_card("Telegram Stars", sub, "STARS", 23 + (n or 0), "", True))


# ============ UI ============
class S(StatesGroup):
    search = State()
    days = State()
    target = State()

r = Router()

async def show(ev, text, kb, photo=None, fallback=None):
    msg = ev.message if isinstance(ev, CallbackQuery) else ev
    is_cb = isinstance(ev, CallbackQuery)
    if photo is None:
        if is_cb and msg.photo:
            await msg.answer(text, reply_markup=kb, parse_mode="HTML")
            await msg.delete()
        elif is_cb:
            await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await msg.answer(text, reply_markup=kb, parse_mode="HTML")
        return
    try:
        await msg.answer_photo(photo, caption=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        if fallback:
            await msg.answer_photo(fallback(), caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await msg.answer(text, reply_markup=kb, parse_mode="HTML")
    if is_cb:
        try:
            await msg.delete()
        except Exception:
            pass

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="🎁 Арендовать подарок", callback_data="rent")],
        [B(text="⭐ Купить Telegram Premium", callback_data="prem")],
        [B(text="🌟 Купить звёзды", callback_data="stars")],
        [B(text="🔍 Поиск", callback_data="search"), B(text="📦 Мои заказы", callback_data="my")],
        [B(text="ℹ️ Условия", callback_data="terms")]])

def back_home():
    return InlineKeyboardMarkup(inline_keyboard=[[B(text="⬅️ В меню", callback_data="home")]])

MAIN_TEXT = "<b>Galaxy Rent</b>\nАренда юзернеймов, номеров +888, NFT-подарков и покупка Telegram Premium за TON."

@r.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await show(m, MAIN_TEXT, main_kb(), img_main(), lambda: img_main())

@r.callback_query(F.data == "home")
async def home(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(c, MAIN_TEXT, main_kb(), img_main())

@r.callback_query(F.data == "terms")
async def terms(c: CallbackQuery):
    await show(c, TERMS, back_home())

@r.callback_query(F.data == "rent")
async def rent(c: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text=f"{ICON[k]} {CATS[k]} ({len(ITEMS[k])})", callback_data=f"p:{k}:0")] for k in CATS
    ] + [[B(text="⬅️ Назад", callback_data="home")]])
    await show(c, "<b>Выберите категорию</b>", kb, img_main())

def items_kb(pairs, page, nav_prefix, back="rent"):
    chunk = pairs[page * PAGE:(page + 1) * PAGE]
    rows = []
    for cat, it in chunk:
        mark = "⛔ " if is_busy(it["name"]) else ("✨ " if it.get("beauty") else "")
        rows.append([B(text=f"{mark}{it['name']} · {fmt(day_price(it))} TON/д",
                       callback_data=f"i:{cat}:{ITEMS[cat].index(it)}")])
    nav = []
    if page > 0:
        nav.append(B(text="◀️", callback_data=f"{nav_prefix}:{page-1}"))
    nav.append(B(text=f"{page+1}/{max(1,(len(pairs)+PAGE-1)//PAGE)}", callback_data="noop"))
    if (page + 1) * PAGE < len(pairs):
        nav.append(B(text="▶️", callback_data=f"{nav_prefix}:{page+1}"))
    rows.append(nav)
    rows.append([B(text="⬅️ Категории", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@r.callback_query(F.data == "noop")
async def noop(c: CallbackQuery):
    await c.answer()

@r.callback_query(F.data.startswith("p:"))
async def list_items(c: CallbackQuery):
    _, cat, page = c.data.split(":")
    pairs = [(cat, it) for it in ITEMS[cat]]
    await show(c, f"<b>{CATS[cat]}</b>\nВыберите лот:", items_kb(pairs, int(page), f"p:{cat}"), img_cat(cat))

@r.callback_query(F.data == "search")
async def search(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.search)
    await show(c, "🔍 Введите название или часть названия.\nМожно категорию: <code>gift</code>, "
                  "<code>username</code>, <code>number</code>.", back_home())

@r.message(S.search)
async def do_search(m: Message, state: FSMContext):
    q = m.text.lower().strip().lstrip("@")
    alias = {"gift": "g", "подар": "g", "nft": "g", "user": "u", "юзер": "u", "number": "n", "номер": "n"}
    forced = next((v for k, v in alias.items() if q.startswith(k)), None)
    found = [(c_, it) for c_ in ITEMS for it in ITEMS[c_] if forced == c_ or q in it["name"].lower()]
    if not found:
        return await m.answer("Ничего не найдено. Попробуйте другое слово.")
    await state.clear()
    await show(m, f"Найдено: {len(found)}", items_kb(found[:PAGE], 0, "noop", back="home"))

@r.callback_query(F.data.startswith("i:"))
async def item(c: CallbackQuery, state: FSMContext):
    _, cat, idx = c.data.split(":")
    it = ITEMS[cat][int(idx)]
    if is_busy(it["name"]):
        until = time.strftime("%d.%m %H:%M", time.localtime(RENTED[it["name"]]["until"]))
        return await c.answer(f"⛔ Занято до {until}", show_alert=True)
    await state.update_data(kind="rent", cat=cat, name=it["name"])
    names = {1: "1 день", 7: "Неделя", 30: "Месяц", 365: "Год"}
    if it.get("tiers"):
        rows = [[B(text=f"{names[d]} — {fmt(rent_total(it, d))} TON", callback_data=f"d:{d}")] for d in NUMBER_TIERS]
    else:
        rows = [[B(text=f"{d} дн. — {fmt(rent_total(it, d))} TON", callback_data=f"d:{d}")] for d in DAY_OPTIONS]
    rows.append([B(text="✏️ Своё число дней", callback_data="dcustom")])
    rows.append([B(text="⬅️ Назад", callback_data=f"p:{cat}:0")])
    link = f"\n{it['link']}" if it.get("link") else ""
    details = ""
    if cat == "g":
        details = (f"\nID: <code>{it.get('gid') or '—'}</code>"
                   f"\nЦвет: <b>{it.get('color') or '—'}</b>")
    text = (f"{ICON[cat]} <b>{it['name']}</b>{link}{details}\n"
            f"{price_line(it)}\n\nНа сколько вы хотите арендовать?")
    await show(c, text, InlineKeyboardMarkup(inline_keyboard=rows),
               it.get("img") or img_item(cat, it), lambda: img_item(cat, it))

@r.callback_query(F.data == "dcustom")
async def dcustom(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.days)
    await c.message.answer("Введите количество дней числом (1–365):")
    await c.answer()

@r.message(S.days)
async def days_in(m: Message, state: FSMContext):
    if not (m.text or "").isdigit() or not 1 <= int(m.text) <= 365:
        return await m.answer("Нужно число от 1 до 365.")
    await state.set_state(None)
    await rent_confirm(m, state, int(m.text))

@r.callback_query(F.data.startswith("d:"))
async def days_btn(c: CallbackQuery, state: FSMContext):
    await rent_confirm(c, state, int(c.data.split(":")[1]))

async def rent_confirm(ev, state, days):
    d = await state.get_data()
    if "name" not in d:
        return await show(ev, "Сессия устарела. /start", back_home())
    it = find(d["cat"], d["name"])
    total = rent_total(it, days)
    title = f"{it['name']} · {days} дн."
    await state.update_data(days=days, total=total, title=title)
    await show(ev, f"<b>{it['name']}</b>\nСрок: {days} дн.\nИтого: <b>{fmt(total)} TON</b>", confirm_kb())

def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="✅ Подтвердить", callback_data="confirm")],
        [B(text="⬅️ Отмена", callback_data="home")]])

@r.callback_query(F.data == "prem")
async def prem(c: CallbackQuery):
    rows = [[B(text=f"⭐ {m} мес. — {fmt(prem_price(m))} TON", callback_data=f"pm:{m}")] for m in PREMIUM_BASE]
    rows.append([B(text="⬅️ Назад", callback_data="home")])
    await show(c, "<b>Telegram Premium</b>\nОплата в TON. Подписка отправляется на ваш @username "
                  "(как подарок через Fragment).", InlineKeyboardMarkup(inline_keyboard=rows), img_premium())

@r.callback_query(F.data.startswith("pm:"))
async def prem_months(c: CallbackQuery, state: FSMContext):
    m = int(c.data.split(":")[1])
    await state.update_data(kind="premium", months=m, total=prem_price(m))
    rows = []
    if c.from_user.username:
        rows.append([B(text=f"👤 Мне (@{c.from_user.username})", callback_data="pt:me")])
    rows.append([B(text="⬅️ Назад", callback_data="prem")])
    await state.set_state(S.target)
    await show(c, f"<b>Premium {m} мес.</b> — {fmt(prem_price(m))} TON\n\nНапишите @username получателя "
                  "или нажмите кнопку.", InlineKeyboardMarkup(inline_keyboard=rows), img_premium(m))

@r.callback_query(F.data == "stars")
async def stars(c: CallbackQuery):
    rows = [[B(text=f"🌟 {n} ⭐ — {fmt(stars_price(n))} TON", callback_data=f"sn:{n}")] for n in STARS_BASE]
    rows.append([B(text="⬅️ Назад", callback_data="home")])
    await show(c, "<b>Telegram Stars</b>\nОплата в TON. Звёзды отправляются на ваш @username.",
               InlineKeyboardMarkup(inline_keyboard=rows), img_stars())

@r.callback_query(F.data.startswith("sn:"))
async def stars_amount(c: CallbackQuery, state: FSMContext):
    n = int(c.data.split(":")[1])
    await state.update_data(kind="stars", stars=n, total=stars_price(n))
    rows = []
    if c.from_user.username:
        rows.append([B(text=f"👤 Мне (@{c.from_user.username})", callback_data="pt:me")])
    rows.append([B(text="⬅️ Назад", callback_data="stars")])
    await state.set_state(S.target)
    await show(c, f"<b>{n} ⭐</b> — {fmt(stars_price(n))} TON\n\nНапишите @username получателя "
                  "или нажмите кнопку.", InlineKeyboardMarkup(inline_keyboard=rows), img_stars(n))

async def prem_confirm(ev, state, target):
    d = await state.get_data()
    await state.set_state(None)
    if d.get("kind") == "stars":
        title = f"{d['stars']} ⭐ для @{target}"
    else:
        title = f"Premium {d['months']} мес. для @{target}"
    await state.update_data(target=target, title=title)
    await show(ev, f"<b>{title}</b>\nИтого: <b>{fmt(d['total'])} TON</b>", confirm_kb())

@r.callback_query(F.data == "pt:me")
async def pt_me(c: CallbackQuery, state: FSMContext):
    await prem_confirm(c, state, c.from_user.username)

@r.message(S.target)
async def pt_text(m: Message, state: FSMContext):
    t = (m.text or "").strip().lstrip("@")
    if not (4 <= len(t) <= 32) or not t.replace("_", "").isalnum():
        return await m.answer("Некорректный @username. Попробуйте ещё раз.")
    await prem_confirm(m, state, t)

@r.callback_query(F.data == "confirm")
async def confirm(c: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text="💎 TON (GRAM)", callback_data="ton")],
        [B(text="⬅️ Отмена", callback_data="home")]])
    await show(c, "Выберите способ оплаты:", kb)

@r.callback_query(F.data == "ton")
async def ton(c: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text="✅ Согласен", callback_data="agree")],
        [B(text="⬅️ Отмена", callback_data="home")]])
    await show(c, "Нажимая кнопку, вас перебросит в приложение Tonkeeper.\n\nВы согласны?", kb)

@r.callback_query(F.data == "agree")
async def agree(c: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    if "total" not in d or "title" not in d:
        return await c.answer("Сессия устарела, начните заново /start", show_alert=True)
    if d["kind"] == "rent" and is_busy(d["name"]):
        return await c.answer("⛔ Лот только что заняли", show_alert=True)
    oid = secrets.token_hex(4)
    ORDERS[oid] = {"kind": d["kind"], "user": c.from_user.id, "username": c.from_user.username,
                   "title": d["title"], "total": d["total"], "paid": False, "done": False,
                   "created": time.time(), "name": d.get("name"), "cat": d.get("cat"),
                   "days": d.get("days"), "months": d.get("months"), "stars": d.get("stars"),
                   "target": d.get("target")}
    save_state()
    nano = int(round(d["total"] * 1e9))
    comment = f"{TRANSFER_DESC} rent_{oid}"
    url = f"https://app.tonkeeper.com/transfer/{WALLET}?amount={nano}&text={quote(comment)}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [B(text="💎 Оплатить в Tonkeeper", url=url)],
        [B(text="🔄 Я оплатил", callback_data=f"chk:{oid}")],
        [B(text="⬅️ Отмена", callback_data="home")]])
    await show(c, f"Заказ <code>{oid}</code>\n{d['title']}\nСумма: <b>{fmt(d['total'])} TON</b>\n\n"
                  f"Оплатите, добавив комментарий к переводу: <code>{comment}</code>, затем нажмите «Я оплатил».", kb)

async def notify_admins(bot, text, reply_markup=None):
    for a in ADMIN_IDS:
        try:
            await bot.send_message(a, text, reply_markup=reply_markup)
        except Exception:
            pass

async def check_payment(oid, total):
    url = f"https://toncenter.com/api/v2/getTransactions?address={WALLET}&limit=50"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            js = await resp.json()
    for tx in js.get("result", []):
        im = tx.get("in_msg") or {}
        if f"rent_{oid}" in (im.get("message") or "") and int(im.get("value", 0)) >= int(total * 1e9) - 1000:
            return True
    return False

@r.callback_query(F.data.startswith("chk:"))
async def chk(c: CallbackQuery, bot: Bot):
    oid = c.data.split(":")[1]
    o = ORDERS.get(oid)
    if not o or o["user"] != c.from_user.id:
        return await c.answer("Заказ не найден", show_alert=True)
    if o["paid"]:
        return await c.answer("Уже оплачено", show_alert=True)
    if o["kind"] == "rent" and is_busy(o["name"]):
        return await c.answer("⛔ Лот занят другим арендатором.", show_alert=True)
    try:
        ok = await check_payment(oid, o["total"])
    except Exception:
        return await c.answer("Не удалось проверить, попробуйте через минуту", show_alert=True)
    if not ok:
        return await c.answer("Платёж пока не найден. Подождите 1–2 минуты и нажмите снова.", show_alert=True)
    o["paid"] = True
    if o["kind"] == "rent":
        RENTED[o["name"]] = {"until": time.time() + o["days"] * 86400, "order": oid, "notified": False}
    save_state()
    await show(c, f"✅ <b>Оплата получена</b>\n{o['title']}\nВладелец скоро выдаст заказ и свяжется с вами.",
               back_home())
    who = f"@{o['username']}" if o["username"] else f"id {o['user']}"
    if o["kind"] == "rent":
        todo = f"Выдайте «{o['name']}» арендатору на {o['days']} дн."
    elif o.get("stars"):
        todo = f"Отправьте {o['stars']} ⭐ на @{o['target']} (Fragment / бот звёзд)"
    else:
        todo = (f"Купите Premium {o['months']} мес. на fragment.com/premium для @{o['target']}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="✅ Выдано", callback_data=f"adm_ok:{oid}")]])
    await notify_admins(bot, f"💰 Заказ #{oid}\n{o['title']}\n{fmt(o['total'])} TON\n"
                                     f"Клиент: {who}\n\n{todo}", reply_markup=kb)

@r.callback_query(F.data == "my")
async def my(c: CallbackQuery):
    mine = [(k, o) for k, o in ORDERS.items() if o["user"] == c.from_user.id and o["paid"]]
    if not mine:
        return await show(c, "У вас пока нет оплаченных заказов.", back_home())
    lines = []
    for k, o in sorted(mine, key=lambda x: -x[1]["created"])[:10]:
        st = "✅ выдано" if o["done"] else "⏳ ожидает выдачи"
        extra = ""
        if o["kind"] == "rent" and o["name"] in RENTED and RENTED[o["name"]]["order"] == k:
            extra = " · до " + time.strftime("%d.%m %H:%M", time.localtime(RENTED[o["name"]]["until"]))
        lines.append(f"<code>{k}</code> {o['title']} — {st}{extra}")
    await show(c, "<b>Ваши заказы</b>\n\n" + "\n".join(lines), back_home())

@r.callback_query(F.data.startswith("adm_ok:"))
async def adm_ok(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer()
    oid = c.data.split(":")[1]
    o = ORDERS.get(oid)
    if not o:
        return await c.answer("Нет заказа")
    o["done"] = True
    save_state()
    await c.message.edit_text(c.message.text + "\n\n✅ Отмечено как выдано")
    try:
        await bot.send_message(o["user"], f"✅ Заказ <code>{oid}</code> выполнен: {o['title']}", parse_mode="HTML")
    except Exception:
        pass

@r.callback_query(F.data.startswith("adm_ret:"))
async def adm_ret(c: CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer()
    oid = c.data.split(":")[1]
    o = ORDERS.get(oid)
    if o and o.get("name") in RENTED and RENTED[o["name"]]["order"] == oid:
        del RENTED[o["name"]]
        save_state()
    await c.message.edit_text(c.message.text + "\n\n↩️ Лот освобождён")

@r.message(Command("orders"))
async def orders_cmd(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    paid = [(k, o) for k, o in ORDERS.items() if o["paid"]]
    income = sum(o["total"] for _, o in paid)
    busy = "\n".join(f"⛔ {n} до {time.strftime('%d.%m %H:%M', time.localtime(v['until']))}"
                     for n, v in RENTED.items()) or "—"
    last = "\n".join(f"#{k} {o['title']} {fmt(o['total'])} TON {'✅' if o['done'] else '⏳'}"
                     for k, o in sorted(paid, key=lambda x: -x[1]["created"])[:10]) or "—"
    await m.answer(f"📊 Оплачено заказов: {len(paid)}\nДоход: {fmt(income)} TON\n\n"
                   f"В аренде:\n{busy}\n\nПоследние:\n{last}")


# === НОВОЕ: напоминания об окончании аренды, принимаем bot как аргумент ===
async def expiry_loop(bot: Bot):
    while True:
        try:
            now = time.time()
            for name, v in list(RENTED.items()):
                if now >= v["until"] and not v.get("notified"):
                    v["notified"] = True
                    save_state()
                    o = ORDERS.get(v["order"], {})
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [B(text="↩️ Вернули — освободить лот", callback_data=f"adm_ret:{v['order']}")]])
                    await notify_admins(bot, f"⏰ Аренда «{name}» закончилась (заказ #{v['order']}). "
                                             f"Заберите актив.", reply_markup=kb)
                    if o.get("user"):
                        try:
                            await bot.send_message(o["user"], f"⏰ Срок аренды «{name}» истёк. "
                                                              f"Верните актив владельцу.")
                        except Exception:
                            pass
        except Exception:
            logging.exception("expiry_loop")
        await asyncio.sleep(60)


# ============ ЭКСПОРТ ДЛЯ FLASK ============
_bot: Bot = None
_dp: Dispatcher = None
_loop: asyncio.AbstractEventLoop = None


def init_bot_and_loop(webhook_url: str = "", webhook_path: str = "/webhook",
                      webhook_secret: str = "") -> None:
    """
    Инициализация бота. Вызывается ОДИН раз из app.py.
    Если webhook_url пустой — запускается polling (для локальной разработки).
    """
    global _bot, _dp, _loop
    if _bot is not None:
        return
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    load_db()
    load_state()

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    _bot = Bot(BOT_TOKEN)
    _dp = Dispatcher(storage=MemoryStorage())
    _dp.include_router(r)
    _loop.create_task(expiry_loop(_bot))

    if webhook_url:
        async def _set_webhook():
            await _bot.set_webhook(
                f"{webhook_url.rstrip('/')}{webhook_path}",
                secret_token=webhook_secret or None,
                drop_pending_updates=True,
            )
            logging.info("Webhook set to %s%s", webhook_url.rstrip('/'), webhook_path)
        _loop.run_until_complete(_set_webhook())
    else:
        async def _poll():
            await _bot.delete_webhook(drop_pending_updates=True)
            logging.info("Running in POLLING mode (no WEBHOOK_URL)")
            await _dp.start_polling(_bot)
        _loop.create_task(_poll())

    threading.Thread(target=_loop.run_forever, daemon=True, name="aiogram-loop").start()
    logging.info("Bot initialized, event loop started")


async def process_update(update_data: dict) -> None:
    """Обработка одного апдейта из вебхука."""
    update = Update.model_validate(update_data, context={"bot": _bot})
    await _dp.feed_update(_bot, update)