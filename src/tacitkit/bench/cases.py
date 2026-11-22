"""The bake-off corpus: 1,430 labelled synthetic cases, 13 categories of 110. Seeded, so
every build is identical (checked by `corpus_hash`).

No real person, account or statement: names are invented from common given names and
surnames (English, Malay, Chinese in Latin letters and in characters, Indian), businesses and
places are public, numbers are made up. Each case:
{"id", "category", "text", "names": [str], "keeps": [str]}
A name is a substring that must be hidden; a keep is a substring that must survive (a date,
an amount, a merchant, an organisation, a place). Names that are cut off or glued are the
visible part only. Layouts follow what bank statements print: DUITNOW, IBG, TRSF, GIRO, JOMPAY.
"""

from __future__ import annotations

import json
import random
import sys

SEED = 20261122
R = random.Random(SEED)
N = 110  # cases per category
NAME_CATS = (
    "english",
    "malay",
    "chinese",
    "indian",
    "allcaps",
    "split_lines",
    "cut_off",
    "glued",
    "statement_rows",
)
FACT_CATS = ("organisations", "places", "facts_survive", "statement_rows", "allcaps", "cut_off")
ASIAN_CATS = ("malay", "chinese", "indian")
AMBIGUOUS = "shops_named_after_people"  # a shop named after a person: hiding it is defensible

ENGLISH_FIRST = [
    "Emily",
    "James",
    "Olivia",
    "Daniel",
    "Sophie",
    "Michael",
    "Hannah",
    "Thomas",
    "Grace",
    "William",
    "Chloe",
    "Robert",
    "Laura",
    "Peter",
    "Rachel",
    "George",
    "Megan",
    "Edward",
    "Natalie",
    "Samuel",
    "Rebecca",
    "Oliver",
    "Charlotte",
    "Henry",
]
ENGLISH_LAST = [
    "Carter",
    "Thompson",
    "Hughes",
    "Walker",
    "Bennett",
    "Harrison",
    "Fletcher",
    "Morgan",
    "Turner",
    "Davies",
    "Robinson",
    "Clarke",
    "Mitchell",
    "Foster",
    "Russell",
    "Spencer",
    "Barnes",
    "Holloway",
    "Whitaker",
    "Pearson",
]
MALAY_M = [
    "Ahmad",
    "Muhammad",
    "Faizal",
    "Hafiz",
    "Azlan",
    "Ismail",
    "Zulkifli",
    "Amirul",
    "Khairul",
    "Syafiq",
    "Haziq",
    "Razak",
    "Rosli",
    "Firdaus",
    "Nazri",
    "Iskandar",
]
MALAY_F = [
    "Siti",
    "Nur",
    "Aisyah",
    "Farah",
    "Nurul",
    "Aminah",
    "Hajar",
    "Zarina",
    "Liyana",
    "Syazwani",
    "Rohani",
    "Salmah",
    "Izzati",
    "Faridah",
    "Norhayati",
    "Atiqah",
]
MALAY_FATHER = [
    "Hassan",
    "Rahman",
    "Abdullah",
    "Ibrahim",
    "Yusof",
    "Osman",
    "Abu",
    "Hamid",
    "Salleh",
    "Mohd Noor",
    "Ismail",
    "Kassim",
    "Jaafar",
    "Sulaiman",
]
CHINESE_SURNAME = [
    "Tan",
    "Lim",
    "Lee",
    "Wong",
    "Ng",
    "Chan",
    "Goh",
    "Ong",
    "Teo",
    "Yap",
    "Chong",
    "Low",
    "Koh",
    "Cheah",
    "Liew",
    "Foo",
]
CHINESE_GIVEN = [
    "Wei Ling",
    "Ah Kow",
    "Mei Yee",
    "Chee Keong",
    "Siew Mei",
    "Kok Wai",
    "Hui Min",
    "Jia Hao",
    "Boon Hock",
    "Pei Shan",
    "Kah Seng",
    "Xin Yi",
    "Yong Sheng",
    "Li Ting",
    "Soon Huat",
    "Zhi Wei",
]
CHINESE_ENGLISH = ["Jason", "Vivian", "Kelvin", "Jessica", "Alvin", "Michelle", "Ivan", "Cindy"]
HANZI = [
    "陈伟玲",
    "林志强",
    "黄美仪",
    "李嘉豪",
    "吴秀梅",
    "张国伟",
    "王丽婷",
    "刘永胜",
    "郑佩珊",
    "杨家成",
    "谢欣怡",
    "梁志伟",
]
INDIAN_M = [
    "Rajesh",
    "Suresh",
    "Kumar",
    "Ganesh",
    "Arun",
    "Vijay",
    "Ravi",
    "Prakash",
    "Muthu",
    "Saravanan",
    "Dinesh",
    "Karthik",
    "Mohan",
    "Selvam",
]
INDIAN_F = [
    "Priya",
    "Kavitha",
    "Lakshmi",
    "Deepa",
    "Anitha",
    "Meena",
    "Shalini",
    "Revathi",
    "Malini",
    "Sangeetha",
    "Thilaga",
    "Devi",
]
INDIAN_FATHER = [
    "Subramaniam",
    "Krishnan",
    "Ramasamy",
    "Muniandy",
    "Govindasamy",
    "Raj",
    "Pillai",
    "Nair",
    "Rajendran",
    "Arumugam",
    "Maniam",
    "Velu",
]

ORGS = [
    "Maybank",
    "CIMB Bank",
    "Public Bank",
    "Petronas Dagangan Berhad",
    "Tenaga Nasional Berhad",
    "Syarikat Jaya Maju Sdn Bhd",
    "Grab",
    "AirAsia",
    "Shopee",
    "Lazada",
    "Telekom Malaysia",
    "Axiata Group",
    "Sunway Group",
    "IOI Corporation",
    "Genting Berhad",
    "Top Glove",
    "Hong Leong Bank",
    "RHB Bank",
    "Celcom Digi",
    "Astro Malaysia",
    "Kumon Malaysia",
    "Prestige Logistics Sdn Bhd",
    "Bina Teguh Enterprise",
    "Global Tech Solutions Sdn Bhd",
    "Mutiara Kreatif Enterprise",
    "LHDN",
    "KWSP",
    "PERKESO",
    "Bursa Malaysia",
    "Tealive",
]
PLACES = [
    "Petaling Jaya",
    "Shah Alam",
    "Kuala Lumpur",
    "Subang Jaya",
    "Bangsar",
    "Cheras",
    "Bukit Bintang",
    "Jalan Ampang",
    "Mont Kiara",
    "Damansara Heights",
    "Puchong",
    "Klang",
    "Ipoh",
    "Georgetown",
    "Johor Bahru",
    "Melaka",
    "Seremban",
    "Kota Kinabalu",
    "Kuching",
    "Putrajaya",
    "Cyberjaya",
    "Setapak",
    "Kepong",
    "Sri Hartamas",
    "Taman Tun Dr Ismail",
    "Jalan Tuanku Abdul Rahman",
    "Ara Damansara",
    "Bandar Utama",
    "Kajang",
    "Lembah Pelita",
]
MERCHANTS = [
    "7-Eleven Malaysia",
    "Village Grocer",
    "Tealive",
    "KK Super Mart",
    "Jaya Grocer",
    "Petronas Mesra",
    "Shell Kepong",
    "Watsons",
    "Guardian Pharmacy",
    "MR DIY",
    "Aeon Big",
    "Lotus's",
    "Starbucks Bangsar",
    "Zus Coffee",
    "Mydin",
    "Uniqlo",
    "Popular Bookstore",
    "Giant Hypermarket",
    "Caltex",
    "Daiso",
    "Secret Recipe",
    "Texas Chicken",
    "Pizza Hut",
    "Touch n Go",
    "Unifi",
    "Indah Water",
    "Syabas",
    "TNB",
]
PERSON_SHOPS = [
    "Nasi Kandar Ali",
    "Restoran Ah Cheng",
    "Mamak Raju Corner",
    "Kedai Runcit Pak Mat",
    "Roti Canai Kak Yah",
    "Ah Huat Kopitiam",
    "Restoran Rebung Chef Ismail",
    "Murugan Idli Shop",
    "Nasi Lemak Mak Wanjor",
    "Tony Roma's",
    "Uncle Lim's Kitchen",
    "Ali Maju Restoran",
    "Kak Ton Kuih",
    "Pak Li Satay",
    "Auntie Anne's",
    "Marrybrown",
    "Wong Kee Roast",
    "Ramly Burger",
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def pick(seq):
    return R.choice(seq)


def english():
    return (
        f"{pick(ENGLISH_FIRST)} {pick(ENGLISH_LAST)}" if R.random() < 0.8 else pick(ENGLISH_FIRST)
    )


def malay():
    if R.random() < 0.5:
        first = f"{pick(MALAY_M)} {pick(MALAY_M)}" if R.random() < 0.5 else pick(MALAY_M)
        return f"{first} {pick(['bin', 'Bin'])} {pick(MALAY_FATHER)}" if R.random() < 0.6 else first
    first = f"{pick(MALAY_F)} {pick(MALAY_F)}" if R.random() < 0.6 else pick(MALAY_F)
    return (
        f"{first} {pick(['binti', 'Binti', 'bt'])} {pick(MALAY_FATHER)}"
        if R.random() < 0.6
        else first
    )


def chinese():
    roll = R.random()
    if roll < 0.25:
        return pick(HANZI)
    if roll < 0.45:
        return f"{pick(CHINESE_ENGLISH)} {pick(CHINESE_SURNAME)}"
    return f"{pick(CHINESE_SURNAME)} {pick(CHINESE_GIVEN)}"


def indian():
    if R.random() < 0.5:
        name, marker = pick(INDIAN_M), pick(["a/l", "A/L", "s/o"])
    else:
        name, marker = pick(INDIAN_F), pick(["a/p", "A/P", "d/o"])
    return (
        f"{name} {marker} {pick(INDIAN_FATHER)}"
        if R.random() < 0.6
        else f"{name} {pick(INDIAN_FATHER)}"
    )


ANY = [english, malay, chinese, indian]
CHAT = [
    "Remind me to call {n} tomorrow at 10am",
    "Draft a thank-you note to {n} for covering the client call",
    "Tell {n} the vendor demo moved to Thursday",
    "Summarise what {n} said about the budget in today's meeting",
    "Can you ask {n} whether the offsite is still on?",
    "{n} will send the signed form by Friday.",
    "Meeting with {n} at 3:30 pm about the renewal",
    "Please forward the invoice to {n} and copy me",
    "Hi {n}, thanks for the update. Let's talk on Monday.",
    "Add a note: {n} prefers email over calls",
    "Write a short reply to {n}: the report is ready",
    "Book lunch with {n} next Wednesday",
]


def keep_date():
    d, m = R.randint(1, 28), R.randint(1, 12)
    return pick(
        [
            f"{d:02d}/{m:02d}/2026",
            f"{d} {MONTHS[m - 1]} 2026",
            f"{d:02d}-{MONTHS[m - 1].upper()}-26",
            f"2026-{m:02d}-{d:02d}",
        ]
    )


def keep_amount():
    v = R.randint(1, 99999) / 100 * R.choice([1, 1, 10])
    return pick([f"RM {v:,.2f}", f"RM{v:,.2f}", f"MYR {v:,.2f}", f"{v:,.2f}"])


def case(category, text, names=(), keeps=()):
    for item in (*names, *keeps):
        assert item in text, (category, item, text)
    return {"category": category, "text": text, "names": list(names), "keeps": list(keeps)}


def people(category, make):
    out = []
    for _ in range(N):
        name = make()
        out.append(case(category, pick(CHAT).format(n=name), [name]))
    return out


def allcaps():
    out = []
    for _ in range(N):
        name = pick(ANY)().upper()
        while not name.isascii():
            name = pick(ANY)().upper()
        date, amount = keep_date(), keep_amount()
        row = pick(
            [
                "{d} DUITNOW TRF TO {n} {a}",
                "{d} IBG CR {n} {a}",
                "{d} TRSF FR {n} {a}",
                "{d}  FUND TRANSFER  {n}  {a} CR",
                "ACCOUNT NAME: {n}",
                "PAYEE {n}  {a}",
                "{d} GIRO {n} {a} DR",
            ]
        )
        text = row.format(d=date, n=name, a=amount)
        out.append(case("allcaps", text, [name], [k for k in (date, amount) if k in text]))
    return out


def split():
    out = []
    for _ in range(N):
        name = pick(ANY)()
        while " " not in name:
            name = pick(ANY)()
        if R.random() < 0.5:
            name = name.upper()
        words = name.split(" ")
        cut = R.randint(1, len(words) - 1)
        head, tail = " ".join(words[:cut]), " ".join(words[cut:])
        text = pick(
            [
                "Transfer to {h}\n{t} for the deposit",
                "Name: {h}\n      {t}\nStatus: paid",
                "DUITNOW TRF {h}\n{t}  {a}",
                "Please call {h}\n{t} about the claim",
            ]
        )
        text = text.format(h=head, t=tail, a=keep_amount())
        out.append(case("split_lines", text, [head, tail]))
    return out


def cutoff():
    out = []
    for _ in range(N):
        name = pick(ANY)().upper()
        while " " not in name or not name.isascii():
            name = pick(ANY)().upper()
        shown = name[: max(len(name.split(" ")[0]) + 2, len(name) - R.randint(1, 5))].rstrip()
        date, amount = keep_date(), keep_amount()
        text = pick(["{d} DUITNOW TRF {n} {a}", "{d} IBG CR {n}  {a}", "{d} TRSF {n}   {a} DR"])
        text = text.format(d=date, n=shown, a=amount)
        out.append(case("cut_off", text, [shown], [date, amount]))
    return out


def glued():
    out = []
    for _ in range(N):
        name = pick(ANY)()
        while not name.isascii():
            name = pick(ANY)()
        style = R.randint(0, 3)
        if style == 0:
            text, shown = f"PAYMENTTO{name.upper()} {keep_amount()}", name.upper()
        elif style == 1:
            bank = pick(["MAYBANK", "CIMB", "RHB", "PBB"])
            text, shown = f"{name.upper()}{bank} 5140", name.upper()
        elif style == 2:
            shown = name.replace(" ", "")
            text = f"Sent by {shown} via the portal"
        else:
            shown = name.upper()
            text = f"TLR0031{shown} TRF"
        out.append(case("glued", text, [shown]))
    return out


def orgs():
    out = []
    for _ in range(N):
        org = pick(ORGS)
        text = pick(
            [
                "Pay the {o} invoice before the 25th",
                "{o} sent a letter about the renewal",
                "Compare {o} and its rivals on fees",
                "Call {o} customer service about my order",
                "The {o} contract renews next month",
                "Draft a complaint to {o} about the delay",
            ]
        )
        out.append(case("organisations", text.format(o=org), keeps=[org]))
    return out


def places():
    out = []
    for _ in range(N):
        place = pick(PLACES)
        text = pick(
            [
                "Find a dentist in {p} open on Sunday",
                "Traffic from {p} to KLCC at 6pm",
                "Book a hotel near {p} for Friday",
                "Is there a post office in {p}?",
                "Move the dinner to {p} instead",
                "Best nasi lemak around {p}",
            ]
        )
        out.append(case("places", text.format(p=place), keeps=[place]))
    return out


def statement_rows():
    """Ledger Flow-style rows (REMY-PRIVACY-REVIEW.md): transfers carry people, purchases merchants."""
    out = []
    for _ in range(N):
        date, amount = keep_date(), keep_amount()
        if R.random() < 0.5:
            name = pick(ANY)().upper()
            while not name.isascii():
                name = pick(ANY)().upper()
            row = pick(
                [
                    "{d} DUITNOW TRF CR {n} {a}",
                    "{d} IBG CR {n} REF 0031882 {a}",
                    "{d} TRSF DR {n} {a}",
                    "{d} INSTANT TRF TO {n}   {a}",
                ]
            )
            out.append(
                case("statement_rows", row.format(d=date, n=name, a=amount), [name], [date, amount])
            )
        else:
            merchant = pick(MERCHANTS).upper()
            row = pick(
                [
                    "{d} POS PURCHASE {m} {a}",
                    "{d} CARD TXN {m} KUALA LUMPUR {a}",
                    "{d} JOMPAY {m} {a}",
                    "{d} {m}  {a} DR",
                ]
            )
            out.append(
                case(
                    "statement_rows",
                    row.format(d=date, m=merchant, a=amount),
                    [],
                    [date, amount, merchant],
                )
            )
    return out


def facts():
    out = []
    for _ in range(N):
        date, amount, merchant = keep_date(), keep_amount(), pick(MERCHANTS)
        text = pick(
            [
                "Paid {a} at {m} on {d}",
                "Refund of {a} from {m} expected by {d}",
                "{m} receipt {d} total {a}",
                "Remind me: {m} bill {a} due {d}",
            ]
        )
        out.append(
            case(
                "facts_survive",
                text.format(a=amount, m=merchant, d=date),
                keeps=[date, amount, merchant],
            )
        )
    return out


def person_shops():
    out = []
    for _ in range(N):
        shop = pick(PERSON_SHOPS)
        text = pick(
            [
                "Lunch at {s} today?",
                "{s} receipt {d} total {a}",
                "Order delivery from {s}",
                "Is {s} open on Sunday?",
            ]
        ).format(s=shop, d=keep_date(), a=keep_amount())
        out.append(case("shops_named_after_people", text, keeps=[shop]))
    return out


def build():
    R.seed(SEED)
    cases = [
        *people("english", english),
        *people("malay", malay),
        *people("chinese", chinese),
        *people("indian", indian),
        *allcaps(),
        *split(),
        *cutoff(),
        *glued(),
        *orgs(),
        *places(),
        *statement_rows(),
        *facts(),
        *person_shops(),
    ]
    for index, item in enumerate(cases):
        item["id"] = index
    return cases


def corpus_hash(cases=None) -> str:
    """SHA-256 prefix of the corpus, stored in every result so runs on different corpora are
    never compared."""
    import hashlib  # noqa: PLC0415

    data = json.dumps(cases or build(), ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()[:16]


if __name__ == "__main__":
    data = build()
    with open(sys.argv[1], "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=0)
    print(len(data), "cases")
