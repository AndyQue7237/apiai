<!-- ADMIN — hur apiai.me:s admin fungerar: datamodell, flik för flik. Skriven 2026-09-29 ur admin-HTML (docs/html/extracted/) och admin-API:t (inspelning), inte ur minnet. -->

# apiai.me Admin: så fungerar det

Dokumenterar **hur** admin-delen av apiai.me fungerar: vilka begrepp som finns, hur de hänger
ihop och vad varje fält gör. Syftet är att en ny produkt ska kunna bygga samma sak, eller
medvetet göra annorlunda, utan tillgång till plattformen.

**Källor** (2026-09-29):
- `docs/html/extracted/*.md`: formulär, fält och hjälptexter ur den sparade Admin Console.
- Admin-API:t (`/admin/api/*`), inspelat med `docs/tools/record_admin.py`: datamodell,
  enum-värden och antal. Råinspelningen är lokal och gitignorerad.
- `docs/public-docs-summary.md`: den publika API-dokumentationen (sammanfattad).

Ingen kunddata och inga nycklar finns här. Påståenden som är slutsatser snarare än avläsningar
är markerade **(tolkning)**.

---

## 1. Datamodell i en bild

```
Server ──< API (workflow) >── Pipeline (flow) ── nod ── nod ── nod …
  │           │
  │           └── Script  (när servern är "Python (Local)")
  │
  └── credentials (API-nyckel per provider)

User ──> Org (team)          Access: Global │ Per user │ Per team
Admin user (separat inlogg, TOTP)
```

| Begrepp | I UI | I API/data | Vad det är |
|---|---|---|---|
| **Server** | Servers | `servers` | En provider-anslutning: typ, URL, nyckel. 7 st. |
| **API** | APIs | `workflows` | Ett anropbart verktyg: en modell *eller* ett script bakom en server. 87 st. Publik endpoint `/api/process/{slug}`. |
| **Script** | Scripts | `scripts` | Python-källkod som körs av Python-servern. 46 st. Blir anropbart först när en API pekar på det. |
| **Pipeline** | Pipelines | `flows` | En kedja av API:er (noder), med villkor och grindar. 27 st. Publik endpoint `/api/pipeline/{slug}`. |
| **User** | Users | `users` | Kund med saldo och API-nyckel. Kan tillhöra en org. |
| **Org** | (Team) | `orgs` | Team; medlemmar delar pipeline-åtkomst och saldo. |
| **Admin user** | Users → Admin Users | `admin-users` | Separat konto för admin, med TOTP. |

Namnen skiljer sig mellan UI och data: **API = workflow** och **Pipeline = flow**. Detta
kommer från plattformens ursprung som ComfyUI-backend (exportfilen heter `comfyui-b2b-export`
och API-formuläret har fortfarande ett fält för "Workflow JSON (ComfyUI API format)").

---

## 2. Access Control ⭐

Styr **vilka API:er och pipelines en användare får anropa**. Tre nivåer, som adderas:

| Nivå | Gäller | Kan ge | Hur |
|---|---|---|---|
| **Global Access** | *Alla* registrerade användare, automatiskt | API:er och pipelines | Sök, markera, "Grant Selected to All Users". |
| **Per-User Access** | En användare | API:er och pipelines | Välj användare → markera → "Grant Selected". *"In addition to any global access."* |
| **Team Access** | En hel org | **Endast pipelines** | Välj team → markera → "Grant Selected". *"All current and future members automatically inherit access."* |

Läget 2026-09-29: **73 API:er och 1 pipeline** var globalt tillgängliga (av 87 resp. 27).
Varje tilldelning har en tidsstämpel (`granted_at`).

**Regler som går att läsa ut:**
- **Templates kräver global åtkomst.** En pipeline markerad *Template* erbjuds som startpunkt i
  varje användares *My Pipelines*, där de kan kopiera och redigera en egen version. *"Templates
  may only use tools that are granted globally — saving tells you which ones are missing."*
  Alltså valideras det vid sparning.
- **Copyable** är en separat flagga på pipelinen: om användare får kopiera den.
- **Kundspecifika pipelines** (Heja, AZ, Widforss …) ges via Team Access eller Per-User,
  inte globalt **(tolkning:** bara 1 pipeline är global, och kundflödena är inte templates).
- **Teamroller** (ur publika docs): *Owner* (allt), *Developer* (API + Dashboard), *Designer*
  (bara Dashboard). **Delad fakturering:** ägarens saldo täcker alla medlemmar. Rollen ligger
  på användaren (`org_role`).

**Att ta med till ny produkt:** tre nivåer räcker långt. Team-nivån som ärver till framtida
medlemmar är det som gör kundflöden hanterbara. Att teams bara kan få *pipelines*, inte
enskilda API:er, är ett medvetet val värt att ompröva.

---

## 3. Users ⭐

Fliken har tre delar: Admin Users, spärr av registreringar, och registrerade användare.

### 3.1 Registrerade användare

**Inloggning är lösenordsfri:** e-post → 6-siffrig kod (`POST /login` → `POST /verify` i
publika API:t). API-anrop autentiseras med `X-API-Key: ak_…`. Nyckeln kan roteras av användaren.

**Skapa användare (admin):** e-post + företagsnamn → **"Create & Send Code"**. Användaren
får en kod och verifierar sig själv.

**Fält per användare:**

| Fält | Betydelse |
|---|---|
| `username`, `email`, `company` | Identitet. Användarnamnet härleds från e-posten **(tolkning)**. |
| `api_key` | Användarens API-nyckel. |
| `balance` | Förbetalt saldo i USD. Dras per anrop (`X-Cost`). |
| `email_verified` | Har angett koden. *"Never entered a code"* = registrerad men aldrig verifierad. |
| `org_role` | Roll i sitt team (Owner / Developer / Designer). |
| `trial_status` | Status för provkredit. Admin kan *Grant trial* eller *Decline*. |
| `suspended` | Avstängd; *Suspend* / *Unsuspend*. |
| `signup_ip`, `signup_country` | Sparas vid registrering, för missbruksskydd. |

**Åtgärder på ett användarkort:** ✎ redigera (saldo och roll redigeras inline, **tolkning** ur
elementens namn), *Grant trial*, *Decline*, *Suspend*/*Unsuspend*.

**Filter:** All users · Verified only · Never entered a code · Balance above $0 · Trial credit
held · Suspended. Sök på e-post, namn, företag eller IP. Listan grupperas per dag och per e-postdomän.

Läget 2026-09-29: 185 användare, varav 3 aldrig verifierade.

### 3.2 Missbruksskydd vid registrering

- **Blocked Sign-up Domains:** registreringar från dessa e-postdomäner *nekas tyst*.
  - Manuellt: domän + valfri anledning → *Block*.
  - **Automatiskt:** en domän som når **3 verifierade registreringar på 24 timmar** blockeras.
  - En publik lista över engångs-mejladresser är inbyggd i koden och syns inte i listan.
- **Refused sign-ups:** logg över nekade registreringar, filter 24 h / 7 d / 30 d.

### 3.3 Admin Users

- Separat inloggning från vanliga användare: **e-post + TOTP-kod** (Google Authenticator,
  1Password, Authy …).
- **Första gången:** *"Enroll TOTP via bootstrap token"* — en engångstoken används för att
  registrera autentiseringsappen.
- Lägg till admin: e-post + namn. Per admin: *Reset TOTP*, *Remove*.

---

## 4. Servers

En server är en **provider-anslutning**. API:er pekar på en server.

**Formulär (Add Server):** Name · Type · URL · credentials. Serverns typ avgör vilken
konfigurationspanel API-formuläret visar (se 5.2).

**Typer som går att välja:** ComfyUI · Google Gemini · xAI (Grok) · OpenAI · RunPod Serverless ·
Replicate · Python (Local) · Other.

**Konfigurerade servrar (7):**

| Namn | Typ | URL | Config |
|---|---|---|---|
| Pyton Scripts | python | `local` | — |
| Replicate | replicate | — | `api_key` |
| Gemini | gemini | `https://generativelanguage.googleapis.com/v1beta` | `api_key` |
| GROK | xai | `https://api.x.ai/v1` | `api_key` |
| GROK Video | xai | `https://api.x.ai/v1` | `api_key`, `model` |
| Gemini Video | gemini | `https://generativelanguage.googleapis.com/v1beta` | `api_key`, `model` |
| OpenAI | openai | `https://api.openai.com/v1` | `api_key`, `model` |

**Hälsokontroll (probe):** admin anropar `/admin/api/{provider}/probe` per API och sparar
resultatet på API:t (`last_probe_status`, `…_capability`, `…_elapsed_ms`, `…_inference_tested`).
UI visar "✓ live". Läget: 56 verified, 7 failed, 24 aldrig testade.

**Lärdom:** nycklarna lagras i klartext i serverns config och följer med i exporten. En ny
produkt bör lagra dem i en secrets-hanterare och aldrig exportera dem.

---

## 5. APIs

En API är **en anropbar enhet**: antingen en modell hos en provider eller ett script.
87 st: 44 script-baserade, 43 modell-baserade (Replicate 24, Gemini 11, OpenAI 7, Grok 1).

### 5.1 Gemensamma fält (Add API)

| Fält | Betydelse |
|---|---|
| Name, Slug, Description | Slug blir URL: `/api/process/{slug}`. Slug genereras från namnet. |
| **AI Context** | Extra vägledning till "?"-hjälpchatten: bra parametervärden, när verktyget ska användas, modellens egenheter, vanliga fel. Knappen *Suggest* genererar ett förslag. 44 av 87 API:er har det ifyllt. |
| Category | Image Generation, Video, Image Editing and Cropping, Visual Intelligence, Utilities, Image Filters, Background Removal, Customer Scripts, Text Generation … |
| **Price per Request ($)** | Vad kunden debiteras per anrop (fyra decimaler). |
| Provider cost per request ($) | Vad providern tar av oss. *"Neither is used at charge time; they make the margin visible."* **Ifyllt på 0 av 87.** |
| Markup override (%) | Påslag per API; tomt = standard från Pricing. Ifyllt på 0 av 87. |
| **Parametric pricing rule** | Ersätter fast pris när den är på: pris beräknat ur request-parametrar. Se 5.3. |
| Server | Vilken provider. Avgör konfigurationspanelen nedan. |
| **I/O Type Declarations** | Accepted Inputs: Image / Video / Text-JSON / Audio, var och en *off → optional → required*. Output Type: Image / Video / Text-JSON / Audio / ZIP. |
| Max Images | Hur många bildfiler primär-inputen tar (1 = en, högre = flera, max 20). |
| Canva | Flagga för Canva-integration (16 API:er). |
| **Parameters** | Lista över parametrar. *Scan JSON* / *Scan Script* hittar dem automatiskt. Se 5.4. |

**Innan sparning:** en *pre-flight validation* körs, *"so a broken API is caught here rather
than by a customer"*. Det finns också en **Test Run**-panel: ladda upp bild, skriv prompt,
överskrid parametrar, se körloggen.

### 5.2 Konfiguration per servertyp

| Servertyp | Fält |
|---|---|
| **Gemini** | Modell (*Fetch Models* listar tillgängliga) · Response Type: Image / Video / Text / Auto (Image + Text) · Temperature, Top-P, Top-K, Max Output Tokens · Aspect Ratio (1:1, 3:4, 4:3, 9:16, 16:9) · Image Size (512, 1K, 2K, 4K) · Num Images (1–4) · Safety Filter · Negative Prompt · **Prompt** |
| **xAI (Grok)** | Modell (*Fetch Models*) · Response Type: Text / Image / Video / Auto · Temperature, Top-P, Max Tokens, Frequency/Presence Penalty · **Prompt** |
| **OpenAI** | Modell (*Fetch Models*) · Response Type: Text / Image · Temperature, Top-P, Max Tokens, Penalties · Size (auto, 1024², 1536×1024, 1024×1536 …) · Quality (Standard, HD, Low, Medium, High, Auto) · Background (Transparent, Opaque, Auto) · Style (Vivid, Natural) · **Prompt** |
| **Replicate** | Sök i Replicate-katalogen eller ange model-ID (`bytedance/seedream-4`) → *Fetch Schema* hämtar modellens inputs automatiskt och mappar dem till kanoniska namn (`prompt`, `image`) · Image Field (auto-detect) · Image Upload: Auto (Data URL för video, Files API annars) / tvinga Files API / tvinga Data URL · Output Type |
| **Python (Local)** | Script (från Scripts-fliken) · Timeout (s, standard 30, max 300) · Output Type (inkl. ZIP) |
| **ComfyUI** | Workflow JSON (ComfyUI API-format). `LoadImage` byts automatiskt mot `{{INPUT_IMAGE}}`. |

**Promptmallar:** för Gemini, Grok och OpenAI skrivs prompten i API:t med platshållare:
- `{{PARAM_NAME}}` — ersätts med en konfigurerbar parameter.
- `{{PROMPT}}` — ersätts med kundens egen ad-hoc-prompt.

Så kan samma modell finnas som flera API:er med olika inbakade prompts, till exempel
"Nano Banana Pro Inpainting" och "Nano Banana Pro Reference Image".

### 5.3 Parametrisk prissättning

JSON-regel som räknar ut priset från anropets parametrar. Förinställda typer: *Veo (request
params)*, *Replicate-by-seconds (reconciled)*, *Token-based (LLM, not yet reconciled)*, *Flat*.
Exempel ur formulärets platshållare:

```json
{"kind": "formula", "base": 0.05, "min": 0.10, "max": 20.00,
 "linear": [{"param": "duration_sec", "rate": 0.50}],
 "multipliers": [{"param": "resolution", "values": {"720p": 1.0, "1080p": 2.0, "4k": 6.0}, "default": 1.0}]}
```

Pris = base + Σ(param × rate), gånger multiplikatorer, klämt mellan min och max **(tolkning**
av formatet). En förhandsvisning räknar ut kostnaden för exempelparametrar. Publika API:t har
`POST /process/{slug}/estimate` för samma sak.

### 5.4 Parametrar

Per parameter: `name`, `expose_name` (publikt namn om det skiljer sig), `description`,
`default_value`, `required`, `is_image`, `type` (string / int / float).

---

## 6. Scripts

Python-källkod som körs av servern "Python (Local)". Fullständig källkod för alla 46 script
finns i den sanerade exporten (`docs/export/*.sanitized.json`). Kontraktet för hur ett script
skrivs finns i `guidelines/SCRIPT_GUIDELINES.md`.

**Formulär (Add Script):**
- Name (filnamn utan `.py`) · Description.
- **Packages**, bara från en tillåten lista: `Pillow`, `replicate`, `numpy`,
  `opencv-python-headless`, `scikit-image`, `cairosvg`, `scipy`, `pillow-heif`.
- **Miljövariabler** (via `os.environ`): `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
  `OPENAI_API_KEY`, `REPLICATE_API_TOKEN`, `XAI_API_KEY`. Ett script kan alltså själv anropa
  modeller: `nb_pro_inpaint` och `nb_pro_reference_image` anropar Gemini, och
  `detect_and_crop`, `correct_colors` och `Detect and Remove Background` använder
  `replicate`-biblioteket (som läser `REPLICATE_API_TOKEN`).
- Source Code: klistra in eller *Upload .py*.
- **Ask Claude** / **Fix it**: AI-assistent som skriver eller ändrar scriptet utifrån en
  beskrivning.

**Test Script:** ladda upp en bild + parametrar som JSON (`{"padding": "20"}`) → *Run Test*.

**Från script till anropbart verktyg:** skapa en API med servern "Pyton Scripts", välj scriptet,
sätt timeout och output-typ, och lägg till parametrar (*Scan Script* hittar dem).

---

## 7. Pipelines

*"Build multi-step pipelines that chain tools together. Metadata (bounding boxes, colors,
flags) can be passed between steps."*

**Formulär (Add Pipeline):** Name · Slug (`/api/pipeline/{slug}`) · Description · Preview image
(för template-kortet) · flaggor **Active**, **Template**, **Copyable**. Därunder: *Available
Workflows* (klicka för att lägga till som nod) och *Pipeline Nodes*.

**Test Flow:** *Run Flow* kör hela kedjan; *Debug* kör steg för steg (publikt:
`POST /flow/{slug}/debug`).

### 7.1 Nodtyper

Ur `flow_config` för alla flöden: 82 workflow-noder, 7 condition, 3 gate.

| Typ | Fält | Beteende |
|---|---|---|
| **workflow** | `workflow` (API-slug), `params` | Kör en API. |
| **condition** | `condition_field`, `condition_value`, `skip_count` | Om fältet i föregående nods JSON-utdata har värdet → **hoppa över nästa N noder**. T.ex. `is_high_resolution = true, skip 2` hoppar över uppskalningen. |
| **gate** | `gate_prompt`, `gate_input`, `yes_message`, `no_message`, `rejected_message`, `gate_branch_yes`, `gate_expose` | LLM svarar JA/NEJ på en fråga om bilden (Quality Gate, ~$0.001). NEJ stoppar flödet med `no_message`. `rejected_message` om säkerhetsfiltret blockerar. `gate_branch_yes: "stop"` avslutar även vid JA **(tolkning)**. |

`output_node` anger vilken nods resultat flödet returnerar.

### 7.2 Parametrar på en nod: fem sätt att binda

Ur hjälptexten: *"Configure each parameter as Expose (user provides via API), Fixed (baked in),
Wire ← prev (from previous node output), Default, or Omit (remove from request)."*

| Bindning | I `flow_config` | Betydelse | Antal |
|---|---|---|---|
| **Fixed** | `{"fixed": "…"}` | Inbakat värde, t.ex. en prompt. | 308 |
| **Wire** | `{"from_node": "node_4", "is_image": true}` | Tar utdata från en tidigare nod. | 54 |
| **Original** | `{"use_original": true, "is_image": true}` | Tar pipelinens *ursprungliga* inbild, oavsett steg. | 6 |
| **Expose** | `{"expose": "image", "required": true, "default": "…"}` | Blir en parameter i pipelinens publika API. | 39 |
| **Omit** | `{"omit": true}` | Parametern skickas inte alls. | 51 |
| **Default** | `{}` | API:ts eget standardvärde gäller. | 20 |

En condition-nod släpper igenom bilden: nästa nod wirar `from_node` till condition-noden.

**Lärdom för ny produkt:** den här bindningsmodellen är kärnan i "kedja modeller och script".
*Original*-bindningen (jämför mot källbilden efter generering) är det som gör t.ex. Hejas
färgkorrigering möjlig.

Heja-flödet nod för nod: se `docs/flows/HEJA.md` (kommer).

---

## 8. Usage & Billing

Datumfilter (från–till) → två tabeller:

| Tabell | Kolumner |
|---|---|
| **By User** | Förbrukning per användare (visas inte här: kunddata). |
| **By API** | `workflow_slug`, `workflow_name`, `total_requests`, `success_count`, `error_count`, `total_cost`. Pipelines syns som `flow:{slug}`. |

`total_cost` är det kunden debiterats, inte providerkostnaden, som aldrig registrerades (5.1).

**Exempel, 2026-08-31 till 2026-09-29** (74 API:er/pipelines med trafik), de tre största:

| API / pipeline | Anrop | Fel | Debiterat |
|---|---|---|---|
| Nano Banana 2 | 4 896 | 50 | $242.30 |
| `flow:widforss-produktbild` | 2 900 | 32 | $86.04 |
| Gemini 3.1 Flash Lite Preview | 1 180 | 1 | $47.16 |

**Hur debitering fungerar** (ur publika docs): förbetalt saldo; varje svar har `X-Cost` och
`X-Balance-Remaining`. Påfyllning via Stripe ($10 / $50 / $100) och auto-refill när saldot
understiger $5.

---

## 9. Monitor

Tidsfönster 1 h / 6 h / 24 h / 48 h / 7 d.

| Del | Innehåll |
|---|---|
| **Stats Cards** | total_requests, success/error_count, error_rate, avg_ms, **p95_ms**, total_cost |
| **Live execution capacity** | Vem som håller körplatserna just nu: `in_flight`, `holders`. **Gränser: 8 samtidiga körningar totalt, 4 per användare.** |
| Hourly Chart | requests, errors, avg_ms per timme |
| Error Breakdown | vanligaste felet per API/pipeline med antal |
| Slowest Requests | långsammaste anropen |
| Recent Errors | senaste felen med felmeddelande |
| **AI Analysis** | AI-sammanfattning av felbilden |

**Exempel, 24 h till 2026-09-29:** 296 anrop, 6.4 % fel, snitt 8.7 s, p95 26.7 s, $8.66.
Alla 19 fel kom från ett flöde (`widforss-produktbild`): Replicate-bakgrundsborttagning
avvisar AVIF (415). **Lärdom:** normalisera bildformat innan första providern.

**Avvikelse:** publika docs säger 1 samtidig körning per användare och 2 totalt; admin visar
4 och 8. Admin-värdet är aktuellt.

---

## 10. Öppna frågor

- **Pipeline-editorns UI** (nodlistan, hur man väljer bindning) syns bara med ett flöde
  öppet. Datan är dokumenterad (7.1–7.2); själva editorn är inte sparad.
- **User-delen** (vanlig inloggning: dashboard, My Pipelines, API-nycklar) är inte crawlad.
- **Pricing-fliken** (prenumerationer, *What if?*) är medvetet utelämnad: inte lanserat.
- **Eval-plattformen** (eval.apiai.me) och **batch** finns bara i publika docs.
- **Providerkostnader** registrerades aldrig; marginal per API är okänd.
