# Salgsanslag fra butikklager (sideprosjekt)

Nedre anslag på salg i fysiske butikker: fall i lager per vare og butikk fra én nattkjøring til neste. Påfyll skjuler salg, så bruk tallene som indeks. Holdes utenfor hovedrapporten. Skrus av med `SALGSANSLAG = False` i `scraper/config.py`.

![Salgsanslag](salgsanslag.png)

## Kitchn

**Vurdering: FOR TIDLIG: avgjøres innen 2026-11-23**

| Kontroll | Status | Resultat | Krav |
|---|---|---|---|
| 1 Søndag nær null | VENTER | trenger en hel søndag og tre hverdager | søndag < 25 % av median hverdag |
| 2 Ukemønster | VENTER | har 2 av 6 ukedager før Black Week | lørdag blant de to største; man-ons lavere enn tor-lør |
| 3 Stabil fordeling | VENTER | har 2 av 8 hele dager før Black Week | kategorier ≥ 0,85 og butikker ≥ 0,80 |
| 4 Black Week-løft | VENTER | 0 dager i Black Week (2026-11-23 til 2026-11-30) | totalt > 1,3x ukene før, og større løft på kampanjevarer enn fullpris |
| 5 Nivå | VENTER | trenger 5 hele dager før Black Week | 20-150 % av årsomsetning i butikk |

Oppdatering av lagertall: Løpende: lageret endrer seg i løpet av dagen

Sentrallager holdt utenfor: 582

| Salgsdag | Dag | Timer | Solgt, enheter | Mill. kr (medlem, inkl. mva) | Påfyll | Andel salg kampanje | Sentrallager ut | Nett: gikk tom / tilbake | Metode |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| 2026-11-10 | tir | 11.8 | 1 737 | 0.62 | 4 353 | 62% | – | 43 / 102 | sum per vare (grov) |
| 2026-11-11 | ons | 24.0 | 6 370 | 2.08 | 26 662 | 56% | – | 83 / 107 | sum per vare (grov) |
| 2026-11-12 | tor | 24.0 | 28 445 | 9.87 | 21 486 | 77% | 93 | 293 / 262 | vare x butikk |
| 2026-11-13 | fre | 23.9 | 31 920 | 10.78 | 17 217 | 77% | 167 | 214 / 160 | vare x butikk |

## Tilbords

**Vurdering: FOR TIDLIG: avgjøres innen 2026-11-23**

| Kontroll | Status | Resultat | Krav |
|---|---|---|---|
| 1 Søndag nær null | VENTER | trenger en hel søndag og tre hverdager | søndag < 25 % av median hverdag |
| 2 Ukemønster | VENTER | har 2 av 6 ukedager før Black Week | lørdag blant de to største; man-ons lavere enn tor-lør |
| 3 Stabil fordeling | VENTER | har 2 av 8 hele dager før Black Week | kategorier ≥ 0,85 og butikker ≥ 0,80 |
| 4 Black Week-løft | VENTER | 0 dager i Black Week (2026-11-23 til 2026-11-30) | totalt > 1,3x ukene før, og større løft på kampanjevarer enn fullpris |
| 5 Nivå | VENTER | trenger 5 hele dager før Black Week | 20-150 % av årsomsetning i butikk |

Oppdatering av lagertall: Løpende: lageret endrer seg i løpet av dagen

Sentrallager holdt utenfor: ingen

| Salgsdag | Dag | Timer | Solgt, enheter | Mill. kr (medlem, inkl. mva) | Påfyll | Andel salg kampanje | Sentrallager ut | Nett: gikk tom / tilbake | Metode |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| 2026-11-10 | tir | 11.8 | 839 | 0.25 | 12 804 | 70% | – | 84 / 136 | sum per vare (grov) |
| 2026-11-11 | ons | 24.0 | 2 533 | 0.80 | 18 752 | 63% | – | 114 / 150 | sum per vare (grov) |
| 2026-11-12 | tor | 24.0 | 12 869 | 4.10 | 5 641 | 82% | 0 | 322 / 390 | vare x butikk |
| 2026-11-13 | fre | 23.9 | 12 536 | 4.14 | 4 368 | 78% | 0 | 241 / 188 | vare x butikk |

