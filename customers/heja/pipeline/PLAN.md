# heja-team-logo — nodkarta + status

Lokal replik av den live-pipeline `team-logo-nb-pro` som Heja använder. Byggd för att kunna **byta
en nod och mäta skillnaden** — inte för att ersätta plattformen.

Kör: `python3 run_pipeline.py "<logga>" --tag nbpro`
Utvärdering: `evaluator/customers/heja/eval_logo.py` (rapport med flik per körning).

## Kedjan

| # | Nod | Var den kommer ifrån | Parametrar (live, 2026-08-31) |
|---|---|---|---|
| 1 | Detect and Crop | `apiai-tools/scripts/detect_and_crop.py` | `query="complete logo with text, full team logo with text, entire emblem, club logo"` · `min_padding=5` · resten default |
| 2 | Check Transparency | `check_transparency.py` | `field=is_transparent` · `sample_percent=5` · `threshold=250` (default) |
| — | **Villkor** | | transparent → **hoppa över 3–4** |
| 3 | Nano Banana Pro | `/api/process/nano-banana-pro` | `temperature=0.2` · `top_k=15` · `top_p=0.1` · `image_size=1K` · prompt i `run_pipeline.py` |
| 3b | **Seedream 4 (fallback)** | slug + parametrar **saknas i repliken** | utlöses när NB Pro vägrar |
| 4 | Detect and Remove Background | `detect_and_remove_bg.py` | `query="emblem or shield or badge"` · `remove_holes_threshold=2` · resten default |
| 5 | Check Resolution | `check_resolution.py` | `field=is_high_resolution` · `max_pixels=2000000` |
| — | **Villkor** | | högupplöst → **hoppa över 6** |
| 6 | Real-ESRGAN | `/api/process/real-esrgan` | `scale=4` · `face_enhance` av |
| 7 | Transparent Crop | `crop_transparent.py` | `format=1:1` · `margin=10` · `alpha_threshold=10` |

1K in i uppskalaren × 4 ≈ 4096 px, som sedan beskärs mot alfakanalen. Det förklarar utdata på
~3700–3900 px.

**`max_pixels=2000000` här, men README anger leveranskravet till Heja som 1 500 000.** Två olika
tal på två ställen; grinden är 2 M. Red ut vilket som gäller mot kund.

## Så drivs plattformens noder lokalt

Nod-scripten anropas som **subprocesser över samma stdin/stdout-JSON-kontrakt** som runtimen
använder, alltså exakt samma kod — inte en omskrivning. Två saker krävs för att det ska gå:

- **`script_io.py`** i den här mappen är en lokal shim för den modul runtimen tillhandahåller
  (kontraktet står i `apiai-tools/SCRIPT_GUIDELINES.md` §4). Scripten importerar den utan lokal
  fallback, så utan shimmen går de inte att köra alls. **Den ska aldrig laddas upp med en nod.**
- **`REPLICATE_API_TOKEN`** måste ligga i miljön. Grounding DINO anropas *inifrån* nod 1 och 4,
  inte som ett eget modellsteg, så de två scripten når Replicate själva när de körs lokalt.
  Alternativet är att köra även dem som apiai-endpoints, men då blir de svarta lådor och poängen
  med repliken försvinner.

## NB Pro vägrar vissa loggor — fallbacken är inte valfri

`Chicago Blues FC` ger konsekvent `HTTP 502 · finishReason=IMAGE_RECITATION`, Geminis
upphovsrättsspärr. Tre försök, samma svar; en kontroll på en annan logga i samma stund gav 200, så
det är loggan och inte tjänsten. Plattformen faller därför tillbaka på **Seedream 4**.

**Repliken saknar det steget än så länge**, vilket betyder att den inte kan köra Chicago alls. Det
måste in innan jämförelsen mot GPT Image 2 är rättvis — annars jämförs metoderna på olika
delmängder av setet.

Detta är också viktigare än det ser ut: spärren slår mot loggor som *liknar skyddade varumärken*,
och för en tjänst som gör klubbmerch är det ingen kuriositet utan en återkommande situation.

## Status

**Verifierad mot plattformen 2026-08-31, Trollbäckens GK:**

| | Plattform | Lokal replik |
|---|---|---|
| Storlek | 3738×3738 | 3878×3878 |
| Motiv | 3717×2097 | 3857×2189 |
| Marginal v/h | 10 / 11 | 10 / 11 |
| Genomskinligt | 73,8 % | 73,7 % |
| Fog | 2042×1 px | 2592×3 px |

Identiska marginaler och genomskinlig andel inom 0,1 procentenheter. Storleksskillnaden på 3,6 %
följer av att NB Pro ritar olika varje gång och att beskärningen går efter alfakanalen — **byte-
identitet är omöjlig med ett generativt steg, även vid temperature 0,2.** "Identisk" betyder här
samma nodbeteende, samma villkor tagna, samma geometri och ett visuellt likvärdigt resultat.

Repliken bekräftade dessutom **fogen i båda utdata**. Den är alltså en egenskap hos kedjan, inte ett
engångsfel — sannolikt Real-ESRGAN:s kaklade uppskalning.

## Quality Routing — VALIDERAD 10/10 (2026-09-04)

**Frågan:** När behöver vi GPT2 för att förbättra loggor, och när räcker direkt upscaling?

### Två kvalitetsmått (efter detect-and-crop)
1. **MP (megapixels)** — grundmåttet, samma som print-tjänster använder
2. **Hårda kanter (%)** — fångar artefakter som MP missar (kompression, dålig skalning)

### Routing-regeln

```
IF MP > 1.0                          → Upscale (hög kvalitet, hårda kanter = intentionella)
ELSE IF MP < 0.09                    → GPT2 (för liten, behöver rekonstruktion)
ELSE IF hårda_kanter > 20%           → GPT2 (borderline + artefakter)
ELSE                                 → Upscale (borderline men ren)
```

### Principen

- **MP = grundregeln** ("har vi tillräckligt råmaterial?") — samma logik som print-tjänster
- **Hårda kanter = undantagsdetektorn** ("MP ljuger ibland") — fångar bilder med tillräcklig storlek men dålig kvalitet
- **Vid hög MP (>1) är hårda kanter intentionella** — vektorgrafik/rena loggor har hårda kanter by design, inte artefakter

### Tröskelvärden

| Tröskel | Värde | Motivering |
|---------|-------|------------|
| MP hög | 1.0 | 1000×1000 px, problem synliga för ögat vid denna storlek |
| MP låg | 0.09 | ~300×300 px, gränsen för vad upscaler kan jobba med |
| Hårda kanter | 20% | Empiriskt — fångar Chicago Blues (30%) men inte Kumla (7%) |

### Validering mot eval-setet

**10/10 korrekt klassificering:**
- 6 routade till Upscale → alla fungerade
- 4 routade till GPT2 → alla behövde det

---

## BG Removal Routing — VALIDERAD (2026-09-04)

**Frågan:** När behöver vi GPT2 för bakgrundsborttagning, och när räcker ett script (flood-fill)?

### Routing-regeln

```
IF already_transparent              → Skip bg removal
ELSE IF corner_color_distance > 50  → GPT2 (multi-color bg, e.g. esports)
ELSE                                → Script (flood-fill from edges)
```

### Validering mot eval-setet

| Logo | Transparent | Hörn-färger | Routing | Resultat |
|------|-------------|-------------|---------|----------|
| Kumla | Ja (23%) | — | Skip | ✅ |
| Hammarby IF | Ja (37%) | — | Skip | ✅ |
| Tyresö FF | Ja (14%) | — | Skip | ✅ |
| team_usa | Nej | OLIKA (366) | GPT2 | ✅ (esports edge case) |
| Trollbäckens GK | Nej | Samma (0) | Script | ✅ (0.2% enclosed ok) |
| Warner | Nej | Samma (0) | Script | ✅ |
| Chicago Blues | Nej | Samma (40) | Script | ✅ |
| leopards | Nej | Samma (0) | Script | ✅ |
| special_knivstais | Nej | Samma (0) | Script | ✅ |

### Edge case: Connected monogram letters

Trollbäckens "GKT" har bokstäver med gemensamt tak → skapar 203 px (0.2%) innesluten yta
i K:ets "armhåla". **Accepterat** — vänta på faktisk kundfeedback innan vi lägger till
komplexitet (t.ex. Gemini Flash-detektion). YAGNI.

---

## Nästa: GPT Image 2 som utmanare

Byter ut **nod 3 och 4 på en gång**, eftersom GPT Image 2 har promptbar bakgrundsborttagning. Det är
precis de två noder där samtliga tre fel i human-evalen sitter (`../../evaluator/customers/heja/HUMAN_EVAL.md`),
och alla tre loggor som hoppar över dem fick högsta betyg.

- **Kör `medium` quality, inte `high`.** Andreas har testat båda; high är för långsam och dyr för
  Heja, så medium är det som skulle levereras. Att mäta high vore att bevisa något ni inte kan använda.
- Andreas första intryck: den **löste GKT:s bakgrundshål** men gav **något sämre färg än NB Pro**.
- Kör som **ny flik** i eval-rapporten mot dagens NB Pro-körning, samma nio loggor.
- Överväg **palettlåsning** som efterled (`../../evaluator/customers/heja/COLOUR_LOCK.md`) — den kan
  ta hand om just små färgavvikelser, vilket är det GPT Image 2 verkar tappa mot NB Pro.
