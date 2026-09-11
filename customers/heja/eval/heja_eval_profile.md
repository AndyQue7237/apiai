# Heja — eval profile (`team-logo-nb-pro`)

The version-controlled mirror of the Profile on eval.apiai.me. Author it here, paste it there.
Never leave a profile only on the platform — see `../../EVAL_GUIDELINES.md`.

**Status:** proposed 2026-08-31, not yet calibrated against a real run. The threshold and the
exception clauses are deliberate guesses; revisit both after the first pass over the nine logos.

| Field | Value |
|---|---|
| Profile name | Heja — team logo, print-ready |
| Enabled | yes |
| Pass threshold | **85** |
| Watches | `team-logo-nb-pro` |
| Input slot `{image_1}` | the team's own logo file — **Original** (the comparison anchor) |

**Why 85.** Text exactness carries weight 0.20 and is scored 0 on any character difference. A
single wrong letter therefore caps the total at 80 even when every other axis is perfect, which
lands below the threshold. That is the intent: Heja prints the club's name on garments the club
sells, so a misspelled logo is worse than an unprocessed one. Change the threshold and that
guarantee changes with it — recompute before touching it.

## Goals

> This eval measures whether an automated pipeline turns a team's own logo file into a print-ready
> asset for merchandise **without changing the logo**. The output must be the same logo as
> {image_1} — identical wording, shapes and colours — cleanly isolated from its background, with
> sharp edges and the whole logo centred on a transparent canvas. The decisive question is
> fidelity, not beauty: these logos are printed on garments a club sells under its own name, so a
> redrawn or misspelled logo is worse than no processing at all.

## Rubric

> The output is a print-ready version of the team logo in {image_1}, produced by an automated
> pipeline that crops to the logo, redraws it when it has no transparency, removes the background,
> upscales it and frames it on a square transparent canvas. Judge the output ONLY against
> {image_1}.
>
> Reward an output that is the SAME logo — unchanged wording, shapes, proportions and colours —
> cleanly separated from its background, with crisp edges at high resolution.
>
> Penalise hardest any change to the logo itself. This pipeline uses a generative model, so the
> characteristic failure is an output that looks good but is no longer the club's logo. Do not
> reward a redrawn, "improved", restyled or simplified logo.
>
> TEXT is critical. Compare the wording character by character, including Swedish characters
> (å, ä, ö) and any year or number. A changed, added, removed, misspelled or re-lettered
> character is a critical failure: score Text exactness 0. Text that is illegible in {image_1} but
> sharp in the output is acceptable only if the characters are the same; if you cannot read
> {image_1}, write the words TEXT UNVERIFIABLE in your reasoning and judge only what you can
> actually compare, rather than assuming a match.
>
> Changed emblem shapes, added or removed elements (stars, wreaths, animals, stripes, shield
> outlines) or altered proportions are failures of Logo fidelity.
>
> Colour has its own dimension, Colour fidelity, and is judged by HUE rather than by intensity.
> This pipeline deliberately restores faded, yellowed or colour-cast originals to clean, uniform
> colour, so stronger and cleaner colour of the same hue is the intended result and should be
> rewarded. A shifted hue is a failure: a navy that has turned violet, a club green that has become
> blue, a warm gold that has become lemon. Compare the main colours side by side rather than
> judging each on its own — a small shift is easy to miss and is exactly what this pipeline does
> wrong.
>
> This pipeline also deliberately re-renders the logo in a flat, vector-like style. Loss of
> photographic texture, fabric weave, paper grain, gradients, drop shadows and compression mush is
> INTENDED, not a fault. Judge whether the same design survived, not whether it still looks
> photographic.
>
> Background isolation: the logo must stand free with no residual background — no white or coloured
> box, no rectangle edge, no leftover sky, fabric or paper. A soft halo or a fringe of background
> colour around the edges belongs here too. Because the pipeline places the logo on solid white
> before removing the background, WHITE PARTS OF THE LOGO ITSELF are the characteristic failure:
> a white letter, star, outline or panel cut away leaving a hole, or a white area left behind as a
> floating island or a square patch. Look specifically for this whenever the logo contains white.
>
> Only the background OUTSIDE the design is removed. Everything the design encloses stays and is
> part of the logo: the field inside a shield, the disc inside a ring, the sky behind a skyline,
> the panel a crest sits on. Removing any of it is a failure — a logo with its interior punched
> out is worse than one with too much left. THE EXCEPTION is a logo made only of lettering: there
> the space between and inside the letters is outside the design and should be transparent, so a
> filled pocket between two letters is a failure. Decide which kind of logo you are looking at
> first; the same enclosed white is correct in one and wrong in the other.
>
> Edge quality: edges should be clean and sharp at print size, without jagged stair-stepping,
> upscaling smear, melted or invented detail, or a visible cut-out outline.
>
> Framing: the whole logo must be present, nothing cropped off, centred with even margins.
>
> Do NOT penalise the following — they are correct:
> - A logo that is only text with no emblem. Many clubs have one. Judge the text, not a missing
>   badge.
> - A very wide or very tall logo that leaves large empty margins when centred on a square canvas.
>   That is correct framing for its shape.
> - A logo that is monochrome or uses few colours, when {image_1} is the same.
> - Flat, uniform colour fills and crisp vector-like edges where {image_1} is soft, grainy or
>   photographic. That is the intended restoration, not a loss of detail.
> - Anything genuinely absent from {image_1}. Only penalise what was changed, added or lost
>   relative to {image_1}.
> - Transparency itself, which cannot be seen. Judge isolation from what is visible; do not guess
>   about the alpha channel.
>
> If {image_1} is small or heavily compressed, expect the output to be sharper. Added sharpness is
> the goal and is not an error, as long as nothing changed.

## Scoring dimensions

| Name | Description | Weight |
|---|---|---|
| Text exactness | Every character matches {image_1} — wording, spelling, numbers, year, å/ä/ö. Score 0 if a single character differs, is added or is missing. | **0.20** |
| Logo fidelity | Shapes, emblem elements and proportions match {image_1}. Nothing added, removed or restyled. A flat, vector-like re-render is intended, not a fault. | **0.25** |
| Colour fidelity | The main colours match {image_1} by HUE. Restored, un-faded, more saturated colour of the same hue is correct; a shifted hue (navy turned violet, gold turned lemon) is a failure. | **0.10** |
| Background isolation | The logo stands free — no residual background box, rectangle edge, halo or colour fringe, and no background left inside enclosed areas. White parts OF THE LOGO must survive: no holes where white was cut away. | **0.20** |
| Edge quality | Edges are sharp and clean at print size — no stair-stepping, upscaling smear, melted detail or visible cut-out outline. | **0.15** |
| Framing | The whole logo is present and centred with even margins. Large margins on a very wide or tall logo are correct. | **0.10** |

## Not judged here — assert it in the harness instead

**Resolution.** The judge cannot count pixels; it guesses. The old `eval_heja.py` worked around
this by telling the model the dimensions, which makes the model a narrator rather than a measurer.
Measure it deterministically in the harness as a hard assertion (`w*h >= 1_500_000`), alongside
"the output actually has an alpha channel with transparent pixels" — the other thing the judge
provably cannot see.

**Trapped background inside enclosed areas.** The background is removed from the outside in, so a
region fully surrounded by the logo keeps its background. Measured on the first real output
(Trollbäckens GK, 2026-08-31): 69 enclosed near-white regions, but **68 of them are anti-aliasing
fringe with a median of 98 px**. The single real defect was the triangular pocket between the K and
the T, **48,544 px**. Every ordinary letter counter — the G, and the O, U and B in
"GYMNASTIKKLUBBEN" — was removed correctly, so this is not "the script cannot do letters".

Detect it deterministically: label the connected regions of *opaque* pixels whose colour matches
the removed background, and flag any that do not touch the image border and exceed a size floor.
**A floor of 2000 px found the real defect and produced zero false positives** on that output; a
floor of 50 px produced 68. Scale the floor with the subject area rather than hard-coding it.

The judge cannot be relied on here: it very likely sees the output composited on white, and white
background left on a white backdrop is invisible. That is the mechanism behind the first false
positive. The rubric now asks for ENCLOSURE UNVERIFIABLE rather than a guess — but the
deterministic check is the one that decides.

**Colour drift.** Same output, measured: navy went rgb(24,48,72) hue 210° → rgb(0,24,72) hue
220–240°, gold went rgb(216,168,72) hue 40° → rgb(240,192,24) hue 47°. Darker, bluer, more
saturated. This follows directly from the NB Pro prompt's "find the original, intended colours …
No fading", so it is instructed behaviour that has overshot. The judge scored it as a pass.

Measure it deterministically alongside the judge: extract the dominant saturated colours from
{image_1} and from the output (quantise, ignore white/grey/black), match them up, and report the
**hue delta**. It costs nothing and is far more reliable than asking a model whether two navies are
the same navy. The Colour fidelity dimension exists so a human can *see* which axis failed; the
harness number is what should gate.

**Unverifiable text.** The NB Pro prompt orders the model to render all text legibly, so when the
source text is unreadable the model *invents* letterforms — confidently, and at Heja's scale,
thousands of times. The judge cannot catch this: it has the same blurry original we do. Do not try
to encode it as a score, which would either fail legitimate low-resolution logos or hide the risk.
Instead have the harness grep the judge's `reasoning` for **TEXT UNVERIFIABLE** and route those to
a human regardless of score. A confident pass on text nobody could read is the one outcome that
must never reach a printed garment.

## Calibration notes for the first run

Two logos in the test set will expose rubric bugs if the exception clauses are wrong:

- **knivsta IS** is 980×150 (6.5:1). Centred on a square canvas it becomes a thin strip with large
  margins. Correct — the Framing exception must hold.
- **Trollbäckens GK** is text only, with no emblem, and is the known Grounding DINO failure case.
  The "text-only logo" exception must hold.

Per the guidelines: iterate on disagreements with the judge, not in a vacuum. When you disagree
with a score, encode the exception here explicitly and re-paste.
