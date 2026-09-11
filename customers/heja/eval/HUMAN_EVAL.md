# Human eval — `team-logo-nb-pro`, hela setet, 2026-08-31

Andreas ögonbedömning av de nio utdata i rapportens flik "Hela setet · 2026-08-31"
(`out/report.html`). Detta är facit som de automatiska kontrollerna kalibreras mot — inte tvärtom.

Körning: 9 loggor, 5,8 min, ~$0,92, `eval_logo.py --fresh`.

| Logga | NB Pro körs? | Andreas | Vad felet är |
|---|---|---|---|
| Chicago Blues FC | **nej — SEEDREAM 4** | **BIG FAIL** | Färgerna omgjorda. Husen i skylinen ska vara mörkblå, är grå. Himlen ska vara en vitare ton, är ljusblå. **Se rättelsen nedan: NB Pro rörde aldrig den här loggan.** |
| Hammarby IF | **nej** | perfekt | — |
| Kumla Hockey | **nej** | perfekt | — |
| Trollbäckens GK | ja | bra färger | Det kända hålet: bakgrund kvar i fickan mellan K och T. |
| Tyresö FF | **nej** | bra | — |
| Warner | ja | bra | — |
| leopards | ja | bra | Ändrar texten från vit till blå för att funka mot vit bakgrund. Andreas: "Smart!" — alltså en godkänd färgändring. |
| special_knivstais-hockey | ja | ok | Tar bort bakgrund **inuti** loggan, vilket är fel. |
| team USA | ja | bra | — |

**Sammanfattning: ett färgfel och två fel som beror på bakgrundsscriptet.** 6/9 rena.

## RÄTTELSE 2026-08-31: färgfelet är inte NB Pros

Den lokala repliken avslöjade det. NB Pro **vägrar** Chicago Blues FC, konsekvent, tre försök i rad:

```
HTTP 502 · gemini response contained no image data (finishReason=IMAGE_RECITATION)
```

Det är Geminis upphovsrättsspärr — Chicagos flagga plus en Champions League-liknande boll. En
kontroll på leopards i samma stund gav HTTP 200, så det är loggan och inte tjänsten. Felet är känt
sedan tidigare (README nämner det, fast med fel fallback-modell: **det är Seedream 4 som används**,
inte Flux-2-max).

**Alltså ritades Chicago av Seedream 4, inte av NB Pro.** Det enda färgfelet i hela human-evalen
tillhör fallback-vägen. **NB Pros egen facit på det här setet är 8/8 utan ett enda färgfel** — kvar
står bara de två felen i bakgrundsnoden (GKT:s ficka, Knivstas över-borttagning).

Två följder:
1. **Bedöm NB Pro och fallbacken var för sig.** De är olika modeller med olika svagheter, och att
   blanda ihop dem gjorde att en modell fick skulden för en annans utdata.
2. **Fallback-vägen behöver egen kvalitetsgranskning.** Den utlöses av upphovsrättsspärren, alltså
   just på loggor som liknar skyddade varumärken — vilket för en tjänst som gör klubbmerch inte är
   ett kantfall utan en återkommande situation.

## Fyndet: alla fel ligger i den generativa grenen

De tre loggor som var transparenta från början hoppar över nod 3–4 (NB Pro + bakgrundsborttagning)
och är **exakt** de tre som fick högsta betyg. Varje defekt i setet ligger i grenen som kör den
generativa noden. Ett set på nio är litet, men mönstret är utan undantag.

Bakgrundsscriptet har dessutom fel **åt två håll**: det lämnar kvar bakgrund i en innesluten ficka
(GKT) och det äter bort bakgrund som ligger inuti loggan och ska vara kvar (Knivsta).

Det pekar direkt på nästa hypotes: **GPT Image 2, som har inbyggd bakgrundsborttagning**, skulle
ersätta både nod 3 och nod 4 — alltså precis de två noder där samtliga tre fel sitter. Mät den som
en ny flik mot den här körningen.

## Vad kalibreringen gjorde med de automatiska kontrollerna

**Färgkontrollen är borttagen som domare.** Den flaggade leopards, knivsta och team USA — Andreas
godkände alla tre — och **släppte igenom Chicago**, som är den enda verkliga färgmissen. Sämsta
tänkbara utfall. Tre mått provades och alla tre föll:

1. *Nyansavstånd, topp-4 mot topp-4.* Rapporterade 162° för ett guld som bara ramlat ur topplistan.
2. *Nyansavstånd med större pool.* Hittade alltid en tvilling — kunde aldrig faila.
3. *Andelsviktat färgavstånd.* Diskriminerade mellan två kända utfall men missade Chicago, vars fel
   är att en färg **tappade mättnad och blev grå** — och måttet sorterar bort grått för att bli av
   med bakgrunden. Att sedan mäta medelmättnad föll också: Chicago +6,6 (ser bra ut) medan team USA
   fick −67,3 och godkändes.

Slutsatsen är inte att ett fjärde mått ska provas. Måttet kan se att en färg **förändrats**, men
inte om förändringen är **önskad** — leopards vita text som blir blå är en verklig färgändring som
koden flaggade och människan berömde. Det är en semantisk fråga, och den hör hemma i domarens
rubrik. **Färg mäts inte i harnessen.**

**Bakgrundskontrollen är borttagen helt.** Andreas rättade själva premissen: **bakgrund inuti en
logga ska vara kvar**, det är bara den utanför som ska bort. GKT är undantaget, eftersom texten där
*är* loggan och mellanrummen därför ligger utanför designen. Två detektorer byggdes och båda
falsifierades mot hans bedömning inom minuter:

1. *Innesluten bakgrund kvar.* Flaggade 4,3 miljoner px på Warner och 1,55 miljoner på team USA —
   nästan allt loggornas egna ljusa ytor, som ska vara kvar.
2. *Hål stansade inuti loggan* (motsatsen). Tyst på Knivsta, den enda verkliga över-borttagningen,
   eftersom den hänger ihop med ytterbakgrunden och inte är ett inneslutet hål — och larmade på
   Hammarby, som han kallade perfekt, vars krans har äkta genomskinliga glapp.

Regeln är semantisk, inte topologisk: ingen pixelräkning vet var en design slutar. **Bakgrunden hör
hemma hos domaren och ögat.** Rubriken i `heja_eval_profile.md` är rättad — den sa tidigare
motsatsen och hade lärt domaren att underkänna korrekta utdata.

## Textgranskning 2026-08-31 — inga fel funna

Den sista obedömda risken, och den allvarligaste: NB Pro-prompten beordrar modellen att rendera all
text läsligt även när förlagan är oläslig, alltså att **hitta på bokstäver**. Alla åtta klubbnamn i
den lokala körningen lästes mot originalet:

KUMLA HOCKEY · 1963 · GYMNASTIKKLUBBEN TROLLBÄCKEN · TYRESÖ FF · 1971 · WARNER & SPENCER ·
FOOTBALL CLUB · LEOPARDS · FOOTBALL TEAM · 1998 · TEAM USA · H I F

**Inget felstavat, inget ombildat, inga påhittade tecken.** Risken infriades inte på det här setet.
Det är ett set på nio och inte ett bevis, men det är den mest betryggande enskilda observationen
hittills.

**En avvikelse, och den är till det bättre:** `leopards.jpg` bär vattenstämpeln `WWW.FOTOJET.COM` i
originalet, och utdata har tagit bort den. För Heja är det önskvärt — ingen vill trycka en
gratistjänsts adress på en tröja. Men notera vad som hände: prompten säger uttryckligen *"Do not add
or remove elements"*, och modellen tog ändå bort något efter eget omdöme. **Det är samma förmåga
som, riktad åt fel håll, skriver om ett klubbnamn.** Att den valde rätt här är tur, inte kontroll.

## Vad harnessen bevisat att den klarar

Upplösning, äkta transparens, och **fogar** — långsmala inneslutna artefakter, som den 2 425 × 3 px
söm den hittade i Trollbäckens och som Andreas inte kunde se med blotta ögat men som finns i filen
och följer med i tryck. Det är kontroller där siffran är sanningen, inte en gissning om avsikt.
