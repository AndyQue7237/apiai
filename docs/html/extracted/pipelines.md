<!-- Extracted from the saved apiai.me Admin Console (#sec-flows) by docs/tools/extract_admin_html.py. Structure only; sanitized. -->

### Pipelines
[button: + Add Pipeline]
Build multi-step pipelines that chain tools together. Metadata (bounding boxes, colors, flags) can be passed between steps.
  Upscale only if it needs it
  upscale-only-if-it-needs-it
  The condition node skips the paid steps when the photo is already big enough. This is the only template that would demonstrate branching, and "the cheapest step is the one that says no" already worked once for Bouncer.
  1. Check Resolution
  →
  2. Real Esrgan Upscaler
  →
  3. Sharpen
  →
  4. Format Converter
  Active
  Template
  [button: Test]
  [button: Edit]
  [button: Delete]
  Logo, cleaned and vectoriseed
  logo-cleaned-and-vectoriseed
  A JPEG logo a client emailed becomes a clean SVG.
  1. Format Converter
  →
  2. Recraft Remove Background
  →
  3. Recraft Vectorize
  Active
  Template
  [button: Test]
  [button: Edit]
  [button: Delete]
  …(25 more `pipeline-row` items)
