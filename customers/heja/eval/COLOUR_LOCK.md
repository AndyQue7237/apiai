# Palettlåsning — testad 2026-08-31, delvis lovande

Andreas idé: i stället för att *mäta* färgdrift, **omöjliggör** den genom att låsa utdatans färger
till originalets palett. Samma princip som redan gäller i repot — låt modellen göra det bara den
kan, och lås fast det som inte får ändras deterministiskt
(`pipelines/MODEL_SELECTION_GUIDELINES.md`, carpx komposit-garanti).

Hans egen invändning var gradienter. Den visade sig inte vara problemet.

## Är loggorna platta nog? Ja, alla nio

Andel pixlar inom 30 enheter från någon av originalets 8 vanligaste färger:

| Logga | Platt andel |
|---|---|
| special_knivstais-hockey | 97,4 % |
| Trollbäckens GK | 96,8 % |
| Warner | 96,2 % |
| team USA | 95,1 % |
| leopards | 94,7 % |
| Chicago Blues FC | 93,8 % |
| Hammarby IF | 93,4 % |
| Tyresö FF | 92,2 % |
| Kumla Hockey | 91,8 % |

**9/9 över 90 %, median 94,7 %.** Gradienter är alltså inte hindret i det här setet.

## Vad som testades

**1. Närmaste-färg-låsning** (originalets palett, tolerans 70, bara ogenomskinliga pixlar, kantutjämnade
mellanlägen lämnas i fred). 58 % av pixlarna låstes.

Resultat på Chicago: **halvvägs.** Himlen rättades, den ljusblå tonen gick mot vitare precis som
Andreas ville. **Husen förblev grå.** Skälet är mätbart: gråtonen ligger 125 enheter från originalets
marinblå, långt utanför varje säker tolerans. Modellen har inte skiftat kulören utan **avmättat**,
och närmaste-färg kan inte överbrygga det utan att dra med sig allt annat.

**2. Rangmappning** — utdatas i:te största färg ersätts av originalets i:te största. **Klart sämre.**
Bokstäverna blev röda, rutmönstret rött, bollen röd. Ytrangordningen motsvarar inte samma delar:
originalets största är svart 23,9 %, utdatas är grå 28,8 %, och den röda på femte plats hamnade på
en marinblå. Idén är förkastad.

## Slutsats

Båda misslyckandena har **samma orsak som allt annat vi provat i dag**: för att laga en stor
färgmiss måste man veta att *den här grå ytan är skylinen och skylinen ska vara marinblå*. Det är
semantik, och varken avstånd i färgrymden eller ytrangordning känner till den. Samma vägg som
fällde de två bakgrundsdetektorerna och de tre färgmåtten.

**Men palettlåsning är ändå värd att bygga — som garant, inte som reparation.** När modellen redan
är nära förvandlar den "nästan rätt färger" till "exakt klubbens färger", och tar därmed bort hela
klassen av små driftfel som vi bevisligen inte ens kan mäta. Den räddar inte ett Chicago; det måste
lösas uppströms.

Det gör den till ett naturligt **efterled till GPT Image 2**: mät den modellen på om den kommer
nära, och låt låsningen ta resten. Testa som en egen flik med och utan låsning, så syns det vad
den faktiskt bidrar med.

Prototyperna ligger i sessionens scratchpad (`chicago_compare.png`, `chicago_rank_compare.png`) —
bygg om från den här beskrivningen, de är inte produktionskod.
