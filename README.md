# Kitchn og Tilbords prisindeks

Samler inn alle varer, priser, kampanjer og butikklager på kitchn.no og
tilbords.no. Alt går av seg selv på GitHub. Du trenger ikke installere noe.

## Hvor finner jeg resultatet?

| Fil | Hva |
|---|---|
| [`rapport/SISTE.md`](rapport/SISTE.md) | Kort sammendrag av siste kjøring for begge butikker, med grafer |
| `rapport/kitchn_tracker.xlsx`, `rapport/tilbords_tracker.xlsx` | Full rapport: sammendrag, dag, uke, kategorier, kampanjefasetter, kampanjesider, butikker, alle varer, forklaring |
| [`rapport/helse.md`](rapport/helse.md) | Om innsamlingen gikk bra: antall varer mot det sidene oppgir, forespørsler, feil |
| `data/<butikk>/varer/ÅÅÅÅ-MM-DD.csv.gz` | Rådata: én fil per kjøring, én rad per vare |

## Hva måles?

Samme definisjoner som Kid-trackeren, så tallene kan sammenlignes.

**1) Omsetning (indikatorer):** antall varer (nye/borte), andel på nettlager,
prisindeks på samme varer (priskomponenten i LFL) og **butikklager**.
Produktflisene viser hvor mange enheter hver fysiske butikk har av hver vare
(Kitchn ca. 150 butikker, Tilbords ca. 55). Nedgang i lager på samme vare fra én
dag til neste er en tilnærming til solgte enheter (påfyll trekker ned). Dette
erstatter «nye anmeldelser» fra Kid; anmeldelser per vare vises ikke på
listesidene her.

**2) Kampanjetrykk:** andel av sortimentet med kampanje, fordelt på
butikkens egne merker (kampanjevare, klubbpris, 3 for 2 / flerkjøp, Black Weeks,
lagertømming, «bra deal»), og snittrabatt mot ordinær pris for medlem og
ikke-medlem (også vektet med butikklager). Lagertømming holdes også utenfor i
et eget mål, fordi Kitchn merker den som varig (kampanjeslutt 2030).

Prislag: **ordinær** («Førpris», «Ikke medlem» eller «Etter kampanje» når det
vises, ellers pris), **ikke-medlem** og **medlem** (klubbpris). Prisindeks =
Jevons på samme varer, basis = 10.–15. november 2026 (uken før Black Week).

## Når samles det inn?

- **Daglig i november, desember og januar** (02:47 UTC): Black Week, jul og
  januarsalg. Daglig butikklager fanger salget før påfyll.
- **Hver mandag resten av året.** Ukestallene bruker første kjøring i hver uke
  (mandag), som Kid.

Én kjøring henter side 1 og siste side av hver kategori (siste side viser alle
varene), ca. 145 forespørsler og 15 minutter per butikk. Høflig henting:
robots.txt følges, minst 3 sekunder mellom forespørsler, kun offentlige sider.
De rå sidene lagres som artefakt i GitHub Actions i 14 dager, slik at dataene
kan tolkes på nytt hvis noe blir lest feil.

## Hvis noe går galt

GitHub sender e-post hvis kjøringen feiler, og `rapport/helse.md` viser hva som
mangler. Vanligste årsak er at sidene er endret; be Claude se på
`rapport/helse.md`, og kjør eventuelt *Kartlegging* (fanen **Actions**) for å
hente ferske eksempelsider til `rapport/probe/`.

Starte en kjøring manuelt: fanen **Actions** → *Prisinnsamling* → **Run workflow**
(eller endre `kjor.txt`).

## Teknisk

`scraper/` (Python): `crawl.py` finner kategoriene i menyen og henter alle
varer, `parse.py` leser produktflisene (data-attributter og priseske; begge
butikkene kjører Lindbak og har samme oppsett), `indeks.py` regner målene,
`rapport.py` lager Excel og grafer, `probe.py` kartlegger sidene. Tester i
`tests/` (med ekte sider fra november 2026) kjøres før hver innsamling.
