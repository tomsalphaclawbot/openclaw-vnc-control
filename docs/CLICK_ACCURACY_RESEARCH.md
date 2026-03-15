# Click Accuracy Research — State of the Art (2025-2026)

Research conducted 2026-03-15 for openclaw-vnc-control project.

## The Problem

AI agents analyzing screenshots need to predict exact pixel coordinates for click targets.
Current failure modes in our VNC bridge: vision model guesses coordinates from raw screenshots,
accuracy is ~60-70% for small/dense UI elements, misclicks cascade into failure spirals.

## How the Major Players Handle It

### 1. Claude Computer Use (Anthropic)
**Approach: Trained pixel-counting**
- Claude is trained to visually count pixels from screen edges/reference points to UI elements
- No set-of-marks, no external detector — it's a learned visual estimation skill
- Works well at ~1024px width (their recommended screenshot size)
- Accuracy degrades on high-res screens, small targets, and dense UIs
- Developers must handle coordinate scaling if resizing screenshots

### 2. OmniParser v2 (Microsoft) — Most Relevant to Us
**Approach: Detection pipeline → Set-of-Marks → LLM selection**
- **Pipeline**: Screenshot → YOLOv8 detection → PaddleOCR text extraction → Florence icon captioning → numbered bounding boxes overlaid on image → LLM picks element by ID → compute center of bounding box → click
- **Key insight**: The LLM never predicts raw coordinates. It picks from a numbered menu of detected elements.
- **Performance**: 39.5% on ScreenSpot-Pro (vs GPT-4o's 0.8%) — massive improvement
- **GitHub**: https://github.com/microsoft/OmniParser
- **Models**: https://huggingface.co/microsoft/OmniParser-v2.0
- **Requirements**: Python 3.12, PyTorch, CUDA preferred (but PyTorch MPS may work on Apple Silicon)
- **License**: MIT (icon_caption), AGPL (icon_detect/YOLO)

### 3. UI-TARS (ByteDance)
**Approach: End-to-end VLM with normalized coordinates**
- Predicts coordinates in 0-1000 normalized range, then scales to screen resolution
- Uses chain-of-thought reasoning before action prediction
- v1.5 adds reinforcement learning for better reasoning
- **Known issue**: Coordinate accuracy problems reported in practice; misclicks when resolution changes
- **GitHub**: https://github.com/bytedance/UI-TARS

### 4. SeeClick
**Approach: GUI visual grounding model**
- Specialized for GUI element localization from natural language descriptions
- Establishes that grounding accuracy directly correlates with downstream task success
- Foundation for the ScreenSpot benchmark

## Benchmarks

### ScreenSpot
- Evaluates LVLMs on locating screen elements from natural language instructions
- Spans mobile, desktop, web
- General-purpose LVLMs: **5-16% accuracy** (terrible)
- GUI-specific models: **19-53% accuracy**
- Metric: **point-in-box accuracy** (is the predicted point inside the target element's bounding box?)

### ScreenSpot-Pro (harder)
- Professional high-res desktop environments (23 apps, 5 domains, 3 OSes)
- Targets occupy just **0.07% of screenshot area** (vs 2.01% in ScreenSpot)
- Best model (OS-Atlas-7B): **18.9% raw**, boosted to **48.1% with ScreenSeekeR agentic framework**
- LASER fine-tuned: **55.7%** (SOTA for 7B models)
- GPT-4o: **0.8-0.9%** (essentially random)

### Key Finding
**Raw vision models are terrible at coordinate prediction on real UIs. The gap between "look at screenshot and guess coordinates" vs "detect elements first, then pick from menu" is enormous.**

## Techniques That Work

### 1. Set-of-Marks (SoM) — Highest Impact
Overlay numbered labels on detected UI elements before sending to LLM.
- LLM picks element ID instead of predicting raw coordinates
- Coordinates computed from bounding box center: `((x1+x2)/2, (y1+y2)/2)`
- Eliminates coordinate hallucination entirely
- **OmniParser is the production-ready implementation of this**

### 2. Multi-Scale Screenshots
- Capture full screen for context
- Crop + zoom suspected target area for precision
- Two-pass: coarse localization → fine localization
- Helps with small targets on high-res screens

### 3. Grid Overlay
- Overlay a visible grid on screenshots
- Model can reference grid cells ("click in cell B3")
- Simpler than full SoM but still better than raw coordinate prediction
- Can be done as pure image preprocessing (no ML required)

### 4. Confidence Thresholding
- Request multiple candidate points from the model
- Filter by confidence score (>0.9)
- Fall back to nearby points if primary target uncertain
- Validate via post-click screenshot comparison

### 5. Resolution Standardization
- Always capture at a consistent resolution
- Recommended: 1280x800 or 1024px width (Claude's sweet spot)
- Scale coordinates proportionally for native resolution actions

## Recommended Architecture for openclaw-vnc-control

### Phase 1: Grid Overlay (quick win, no ML dependencies)
- Add `--grid` flag to screenshot command
- Overlay a labeled grid (e.g., 10x10 or adaptive) on the screenshot
- AI model says "click grid cell E7" → tool computes center of that cell
- Zero additional dependencies, works with any vision model
- Estimated accuracy improvement: 2-3x over raw coordinate prediction

### Phase 2: OmniParser Integration (production accuracy)
- Run OmniParser v2 as a preprocessing step
- Screenshot → OmniParser → annotated image with numbered elements + JSON metadata
- LLM picks element ID → tool clicks center of bounding box
- Requires: PyTorch, ~2GB model weights, GPU recommended but MPS may work
- **This is the approach that gets 39.5% on ScreenSpot-Pro vs 0.8% for raw GPT-4o**

### Phase 3: Click Accuracy Benchmark
- Build a test harness:
  1. Render a known UI (HTML page with labeled buttons at known positions)
  2. Screenshot via VNC
  3. Send to vision model with "click the X button" instruction
  4. Compare predicted coordinates to ground truth bounding box
  5. Score: point-in-box accuracy, pixel error (PE), success rate at various thresholds
- Test matrix: model × resolution × screenshot format × technique (raw / grid / SoM)
- Automate via VNC bridge (we already have all the primitives)

## Action Items

1. **Immediate**: Add grid overlay to `vnc-control.py` screenshot command
2. **This week**: Build click accuracy benchmark test harness
3. **Next**: Evaluate OmniParser v2 on Apple Silicon (check MPS compatibility)
4. **Next**: Integrate OmniParser as optional `--parse` flag on screenshots
5. **Stretch**: Run benchmark across Claude, GPT-4o, local models, with and without SoM

## Sources

- Microsoft OmniParser: https://github.com/microsoft/OmniParser
- OmniParser v2 blog: https://www.microsoft.com/en-us/research/articles/omniparser-v2-turning-any-llm-into-a-computer-use-agent/
- ScreenSpot-Pro: https://github.com/likaixin2000/ScreenSpot-Pro-GUI-Grounding
- UI-TARS: https://github.com/bytedance/UI-TARS
- SeeClick / ScreenSpot paper: https://www.alphaxiv.org/benchmarks/shanghai-ai-laboratory/screenspot
- Claude Computer Use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool
- ScreenSeekeR (agentic grounding): https://arxiv.org/html/2504.07981v1
- LASER (fine-tuned grounding): https://www.emergentmind.com/topics/screenspot-pro
