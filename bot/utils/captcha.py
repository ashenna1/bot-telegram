"""
Captcha system - emoji / math / both
Fun, friendly, Persian-first.
"""
import random
import time

EMOJI_POOL = ["🍎", "🍌", "🍓", "🍕", "🚀", "⭐", "🔥", "💎", "🎈", "🐶", "🐱", "🦊", "🐼", "🌈", "⚽", "🎸", "🍩", "🍪", "🍉", "🍒"]
MATH_TEMPLATES = [
    ("{a} + {b} = ?", lambda a, b: str(a + b)),
    ("{a} × {b} = ?", lambda a, b: str(a * b)),
    ("{a} - {b} = ?", lambda a, b: str(a - b)),
]

def generate_captcha(mode: str = "emoji") -> tuple[str, str, list[str]]:
    """
    Returns (question_text, correct_answer, options_for_keyboard)
    mode: emoji | math | both (random)
    """
    if mode == "both":
        mode = random.choice(["emoji", "math"])

    if mode == "math":
        tmpl, fn = random.choice(MATH_TEMPLATES)
        a = random.randint(1, 10)
        b = random.randint(1, 10)
        # for minus keep positive
        if "-" in tmpl and a < b:
            a, b = b, a
        question = tmpl.format(a=a, b=b)
        answer = fn(a, b)
        # generate 4 options
        opts = {answer}
        while len(opts) < 4:
            opts.add(str(int(answer) + random.randint(-5, 5)))
            # ensure no duplicates and positive
            opts = {o for o in opts if o.lstrip("-").isdigit()}
            if len(opts) < 4:
                opts.add(str(random.randint(1, 20)))
        opts = list(opts)
        random.shuffle(opts)
        q_text = f"🧮 <b>کپچا ریاضی</b>\n\nجواب درست رو انتخاب کن:\n<b>{question}</b>"
        return q_text, answer, opts

    # emoji mode
    target = random.choice(EMOJI_POOL)
    distractors = random.sample([e for e in EMOJI_POOL if e != target], 5)
    options = [target] + distractors[:3]
    random.shuffle(options)
    q_text = (
        f"🛡️ <b>تأیید انسان بودن</b>\n\n"
        f"برای جلوگیری از اسپم، لطفاً این ایموجی رو انتخاب کن:\n"
        f"<b>{target}</b> ← همین رو لمس کن!\n\n"
        f"بعدش می‌تونی بدون محدودیت دانلود کنی 🎉"
    )
    return q_text, target, options

def captcha_expired(created_at: int, timeout_sec: int = 120) -> bool:
    return int(time.time()) - created_at > timeout_sec
