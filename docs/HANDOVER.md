<!-- HANDOVER — överlämning från en carpx-session 2026-09-29: varför docs/ finns, vad som hittats och var arbetet står. Läs först. -->

# Överlämning: dokumentera apiai inför en ny produkt

**Skriven 2026-09-29** ur en session som av misstag kördes i carpx-mappen (session
`275ff0b0`, 11:15–11:28). Inget av det nedan fanns sparat någon annanstans.

## Uppdraget (Andreas, ordagrant i sak)

Andreas och utvecklaren går skilda vägar. **Utvecklaren behåller koden och IP:n**; Andreas
bygger en ny produkt, annorlunda och mer anpassad för content, men på samma princip: att
kedja modeller och script. Backend kommer att saknas.

- **Steg 1:** dokumentera så mycket som möjligt av script, modeller och admin.
- **Steg 2:** planera den nya produkten. Den finns inte än.

Arbetet börjar med **Explore** här i apiai-repot.

**Gränsen vi drog:** dokumentera **principer, beslut och mätningar** (modellval och varför,
förkastade spår med underlag, promptstrategier, kostnader, kedjornas logik). Det är både
oproblematiskt och mer värt för en ny produkt med annan layout än en avskrift av hans
implementation. Är något tveksamt: stäm av med honom först.

**Undantag: scripten (beslut av Andreas 2026-09-29).** Merparten av Python-scripten/noderna
har Andreas själv byggt, lokalt i detta repo innan de publicerades på sajten. **Alla** script
i exporten får sparas **ordagrant med full källkod**, inte bara som principer. Det
utvecklaren behåller är **plattformskoden i hans git-repo** (backend, admin, sajten), som
Andreas inte har tillgång till. Gränsen ovan gäller den koden, inte scripten.

## Svar från Andreas på fyra frågor

1. **När upphör åtkomsten till apiai.me?** Inget datum satt, men gör jobbet nu ändå.
2. **Finns en export?** Ja, av verktyg och script, precis exporterad. Läggs i
   **`docs/export/`**. Dessutom finns publik dokumentation på https://apiai.me/docs, som
   sammanfattas i [`public-docs-summary.md`](public-docs-summary.md).
3. **Var ligger crawlern?** I `~/projects/tools/mockups/` (se nedan). **Den inloggade
   admin-delen är viktigast.**
4. **Vad är den nya produkten?** Finns inte än.

**Obesvarat när sessionen bröts:** *"Finns två inloggade delar. 1 som vanlig user.
2 apiai/admin (separat inlogg)."* Båda behöver alltså crawlas, med var sin inloggning.

## Vad som redan finns

| Repo | Innehåll |
|---|---|
| **`apiai/`** (detta) | `guidelines/`: 1 002 rader i fem dokument (SCRIPT, PIPELINE, PROMPT, MODEL_SELECTION, EVAL) · `customers/` az-design, heja, shl · 21 python-noder i `scripts/` |
| **`tools/`** | `evaluator/` (batch-eval), `image-tools/`, tre carpx-pipelines, `mockups/apiai/` med dashboard-mockup |
| **`carpx/`** | `APIAI_FLOWS.md` (361 rader), `STUDIO_PIPELINE.md`, WINNER-filer, evalharnesser |

Alla tre ligger på Andreas konto (`AndyQue7237`). Det som försvinner är **plattformen bakom
apiai.me**, inte repona.

**Uppgiften är därför främst att konsolidera och göra portabelt, inte att skriva från noll.**
`carpx/APIAI_FLOWS.md` är mallen: *"skriven ur den körande koden, inte ur minnet"*, med
promptarna ordagrant och parametrarna exakta.

**Crawlern:** `tools/mockups/apiai/download.py`, skriven av Andreas. Den har `--login` för
autentiserade sidor, sanerar API-nycklar och tar bort auth-redirects så att sidan fungerar
lokalt. Det är verktyget för admin-delen. `dashboard-mockup/` är en tidigare nedladdning,
och det var inte fastställt om den är admin eller den publika sidan.

## Prioritering: efter vad som försvinner, inte efter vikt

Det som ligger i repona kan dokumenteras när som helst. Det som bara finns **inne i
plattformen** går först:

1. **Flödesdefinitionerna**: noder, ordning, parametrar. `APIAI_FLOWS.md` täcker carpx fyra
   flöden. **Az-design, heja och shl saknar motsvarande.**
2. **Vilka modeller som är inkopplade** och under vilka namn.
3. **Nodkontraktet**: hur ett script blir en nod.
4. **Faktiska kostnader** per modell (kom i `X-Cost`-headern).
5. **Admin**: hur ett flöde faktiskt byggs. Både user-delen och `apiai/admin`.

## Nästa steg

1. Andreas lägger exporten i `docs/export/`. **Kontrollera att den saknar nycklar före commit.**
2. Läs exporten och `public-docs-summary.md`, och jämför med `guidelines/` och `scripts/`:
   vad är redan täckt, vad saknas?
3. Crawla båda inloggade delarna med `download.py --login`.
4. Föreslå en struktur för `docs/` och skriv en Feature Brief för dokumentationsarbetet.
