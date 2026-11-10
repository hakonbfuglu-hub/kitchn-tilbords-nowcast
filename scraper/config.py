"""Innstillinger. Alt som er spesifikt for kitchn.no og tilbords.no ligger her.

Begge nettbutikkene kjører samme plattform (Lindbak), med samme URL-mønster,
samme produktfliser og samme robots.txt. Derfor én leser for begge.
"""

STORES = {
    "kitchn": {"base": "https://www.kitchn.no", "navn": "Kitchn"},
    "tilbords": {"base": "https://www.tilbords.no", "navn": "Tilbords"},
}

# Listesider: 80 varer per side, ?page=N viser varene 1..N*80 (kumulativt,
# observert nov. 2026). Vi henter derfor side 1 for å lese totalen, og deretter
# siste side direkte, som inneholder alle varene i kategorien.
PAGE_SIZE = 80
MAX_CARDS_PER_REQUEST = 2400      # større kategorier deles opp i underkategorier
MAX_RUNTIME_MIN = 150             # stopp pent før GitHub sin tidsgrense

# Høflig henting: minst 3 s mellom forespørsler (+ tilfeldig tillegg).
DELAY_S = 3.0
USER_AGENT = ("HomecoPrisindeks/1.0 (aksjeanalyse; ukentlig oeyeblikksbilde "
              "av offentlig produktkatalog; lav frekvens)")

# Toppnivå i URL-en som ikke er produktkategorier
EXCLUDE_TOP = {
    "kampanje", "nyheter", "inspirasjon", "oppskrifter", "bryllup", "kundeklubb",
    "kundeservice", "butikker", "utsjekk", "min-side", "konto", "smslogin",
    "sok", "admin", "templates", "lindbak", "om-kitchn", "om-tilbords",
    "baerekraft", "app", "onskeliste", "merkevarer", "serviser", "jul",
    "mummi-produkter", "gavekort",
}

# Toppkategorier (nov. 2026, likt på begge). Brukes hvis menyen ikke kan leses.
FALLBACK_CATEGORIES = ["kjokken", "borddekking", "interior", "uterom"]

# Ord på produktflisene (nov. 2026)
LABELS = {
    "before": ("Førpris",),            # ordinær pris under åpen kampanje
    "nonmember": ("Ikke medlem",),     # det ikke-medlemmer betaler ved klubbpris
    "club": ("Klubbpris",),
    "campaign_end": ("Kampanjeslutt",),
    "new": ("Nyhet",),
    "web_stock": ("På nettlager",),
    "no_web_stock": ("Ikke på nettlager", "Utsolgt på nett"),
    "preorder": ("Forhåndsbestill", "Kommer snart"),
}

# Helsesjekk: under disse grensene regnes kjøringen som mislykket
HEALTH_MIN_PRODUCTS = 2000
HEALTH_MIN_PRICE_SHARE = 0.95
HEALTH_MAX_DROP_VS_LAST = 0.30      # >30 % færre varer enn forrige uke = varsel
