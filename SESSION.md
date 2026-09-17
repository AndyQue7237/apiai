# Session Memory — apiai

Senast uppdaterad: 2026-09-17

## Aktuellt fokus

**Pipeline eval + GPU-fix + nya resize-scripts**

Pipeline eval visade 7/10 pass, 3 failures:
- Kumla/Tyresö: GPU OOM (>2.1MP)
- team_usa: "Corner colors don't match"

Fixar klara, väntar på deploy till apiai.me.

---

## Sessionen (2026-09-17)

### Vad vi gjorde

1. **Pipeline eval** — skapade eval_pipeline.py, körde 10 loggor
2. **team_usa fix** — lade till `passthrough_on_mismatch` i remove_solid_background.py
3. **GPU-fix** — skapade downscale_image.py (max_pixels=2000000 före upscaler)
4. **resize_image.py** — återbyggde scriptet (width/height/fit modes)
5. **Metoduppdatering** — lade till regler om SCRIPT_GUIDELINES i pipeline-arbete

### Nya scripts

| Script | Syfte |
|--------|-------|
| `downscale_image.py` | Skala ned för GPU-gränser (max_pixels) eller filstorlek (max_bytes) |
| `resize_image.py` | Resize till specifika dimensioner (contain/cover/stretch) |

### Commits

- `e0311b7` Fix correct_colors.py based on apiai.me review
- `02c5564` Rename constrain_image to downscale_image (clearer name)
- Flera commits för passthrough_on_mismatch, metoddokumentation

---

## Nästa session

1. **Ladda upp scripts** till apiai.me:
   - `downscale_image.py` — packages: pillow
   - `resize_image.py` — packages: pillow (behöver Claude review)

2. **Uppdatera pipeline** i apiai.me:
   - Lägg till downscale_image före nod 8, 15, 18 (`max_pixels=2000000`)
   - Sätt `passthrough_on_mismatch=true` på nod 12

3. **Kör pipeline eval igen** — verifiera Kumla, Tyresö, team_usa fungerar

---

## apiai.me upload — redo

### downscale_image.py

**Description:**
```
Scale down images to fit within pixel or file size limits. Useful before GPU-limited upscalers (Real-ESRGAN max ~2.1MP) or for web optimization. Only shrinks - images already within limits pass through unchanged.
```

**Packages:** `pillow`

### resize_image.py

**Description:**
```
Resize image to specific dimensions with fit modes. Supports: contain (fit within, preserve ratio), cover (fill, may crop), stretch (exact size, may distort). If only width or height is provided, the other is calculated to preserve aspect ratio.
```

**Packages:** `pillow`

---

## Key learnings (denna session)

1. **Pipeline API format** — apiai.me använder multipart form-data med `files=` och `X-API-Key` header
2. **Real-ESRGAN GPU limit** — max ~2.1MP (2,096,704 pixels)
3. **Passthrough pattern** — returnera original oförändrad istället för att faila
4. **Script workflow i pipeline-arbete** — följ SCRIPT_GUIDELINES även för snabba fixes

---

## Scratch-filer

```
customers/heja/pipeline/scratch/
├── eval_pipeline.py              # Pipeline eval script
└── (tidigare border test-filer)
```
