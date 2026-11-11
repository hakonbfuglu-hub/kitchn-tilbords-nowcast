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

MIN_CATEGORIES = 10              # færre i menyen = bruk toppnivå i stedet

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

# Analyse
from pathlib import Path as _P
DATA_DIR = _P(__file__).resolve().parents[1] / "data"
BASE_WINDOW = ("2026-11-10", "2026-11-15")   # basis for prisindeks: uken før Black Week

# ---------------------------------------------------------------------------
# SIDEPROSJEKT: salgsanslag fra butikklager (scraper/salg.py, rapport/salgsanslag/)
# Sett SALGSANSLAG = False for å skru det av: da lagres ikke lager per vare og
# butikk, og rapport/salgsanslag/ oppdateres ikke. Hovedrapporten påvirkes ikke.
SALGSANSLAG = True
SENTRALLAGER_FAKTOR = 10        # «butikk» med > 10 x median enheter = sentrallager
MVA = 1.25
# Årsomsetning eks. mva. (mill. kr) for nivåsjekken (grov: bare et bredt bånd 20-150 %).
# Driftsinntekter 2024 for selskapet, ikke kjeden: Kitch'n AS 1 118 (flere butikker
# ligger i egne selskaper «Kjøkkendrift No 1 ...»), Tilbords AS 401. Bytt gjerne
# ut med kjedeomsetning i butikk hvis du har et bedre tall.
REFERANSE_OMSETNING_MNOK = {"kitchn": 1118, "tilbords": 401}
BASELINE = ("2026-11-12", "2026-11-22")     # salgsdager før Black Week
BLACK_WEEK = ("2026-11-23", "2026-11-30")   # Black Friday 27.11.2026
VURDERINGSDATO = "2026-11-23"               # kontroll 1-3 skal være avgjort her
# Lagersjekk flere ganger om dagen 12.-18. nov: hvor ofte oppdateres lageret?
LAGERSJEKK_KATEGORIER = ["/kjokken/bakeutstyr/", "/interior/lys-og-lysestaker/",
                         "/borddekking/glass/"]

# Helsesjekk: under disse grensene regnes kjøringen som mislykket
HEALTH_MIN_PRODUCTS = 2000
HEALTH_MIN_PRICE_SHARE = 0.95
HEALTH_MAX_DROP_VS_LAST = 0.30      # >30 % færre varer enn forrige uke = varsel
