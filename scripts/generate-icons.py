#!/usr/bin/env python3
"""
Generate icon images for mental models catalog using Replicate API.
Model: FLUX.2 Klein 9B (black-forest-labs/flux-2-klein-9b)
Cost: ~$0.015/image → ~$3.71 for 247 images
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
if not REPLICATE_API_TOKEN:
    print("Error: Set REPLICATE_API_TOKEN environment variable")
    print("  export REPLICATE_API_TOKEN=r8_...")
    sys.exit(1)

PROJECT_DIR = Path(__file__).parent.parent
DATA_FILE = PROJECT_DIR / "public" / "data.json"
ICONS_DIR = PROJECT_DIR / "public" / "icons"
PROMPTS_FILE = PROJECT_DIR / "scripts" / "prompts.json"

ICONS_DIR.mkdir(exist_ok=True)

MODEL = "black-forest-labs/flux-2-klein-9b"
MODEL_VERSION = None  # use latest

STYLE_PREFIX = (
    "Minimal concept icon on pure white background. "
    "Clean geometric illustration, flat design, 2-3 solid colors, no text, no gradients, no shadows. "
    "Single visual metaphor, immediately understandable at 64px. "
    "Information design style like untools.co icons. "
    "Warm earth tones: terra cotta, charcoal, sage green. "
)

def make_api_request(url, data=None, method="GET"):
    headers = {
        "Authorization": f"Bearer {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"  API error {e.code}: {err_body[:200]}")
        raise

def create_prediction(prompt, model_name=None):
    url = "https://api.replicate.com/v1/predictions"
    data = {
        "model": model_name or MODEL,
        "input": {
            "prompt": prompt,
            "aspect_ratio": "1:1",
            "output_format": "png",
            "num_outputs": 1,
        },
    }
    return make_api_request(url, data, method="POST")

def wait_for_prediction(prediction_id, max_wait=120):
    url = f"https://api.replicate.com/v1/predictions/{prediction_id}"
    start = time.time()
    while time.time() - start < max_wait:
        result = make_api_request(url)
        status = result.get("status")
        if status == "succeeded":
            return result
        elif status in ("failed", "canceled"):
            print(f"  Prediction {prediction_id} {status}: {result.get('error', 'unknown')}")
            return None
        time.sleep(1)
    print(f"  Prediction {prediction_id} timed out after {max_wait}s")
    return None

def download_image(url, path):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        with open(path, "wb") as f:
            f.write(resp.read())

def generate_icon(model_data, prompt):
    name = model_data["name"]
    slug = name.lower().replace(" ", "-").replace("/", "-").replace("(", "").replace(")", "").replace("'", "")
    slug = slug.replace("--", "-").strip("-")
    icon_path = ICONS_DIR / f"{slug}.png"

    if icon_path.exists():
        print(f"  Skip (exists): {name}")
        return str(icon_path.relative_to(PROJECT_DIR / "public"))

    full_prompt = STYLE_PREFIX + prompt

    try:
        prediction = create_prediction(full_prompt)
        pred_id = prediction["id"]
        result = wait_for_prediction(pred_id)

        if result and result.get("output"):
            output = result["output"]
            img_url = output if isinstance(output, str) else output[0]
            download_image(img_url, icon_path)
            print(f"  OK: {name} → {icon_path.name}")
            return str(icon_path.relative_to(PROJECT_DIR / "public"))
        else:
            print(f"  FAIL: {name}")
            return None
    except Exception as e:
        print(f"  ERROR: {name}: {e}")
        return None

def main():
    if not PROMPTS_FILE.exists():
        print(f"Error: {PROMPTS_FILE} not found.")
        print("Run the prompt generation workflow first, then:")
        print("  python3 scripts/merge-prompts.py")
        sys.exit(1)

    with open(PROMPTS_FILE) as f:
        prompts = json.load(f)

    with open(DATA_FILE) as f:
        catalog = json.load(f)

    prompt_map = {p["name"]: p["visual_prompt"] for p in prompts}
    models = catalog["models"]

    print(f"Models: {len(models)}, Prompts: {len(prompt_map)}")
    print(f"Estimated cost: ${len(models) * 0.015:.2f}")
    print(f"Output: {ICONS_DIR}")
    print()

    skip = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else len(models)

    results = {}
    generated = 0
    failed = 0

    for i, m in enumerate(models[skip:skip+limit], start=skip):
        name = m["name"]
        prompt = prompt_map.get(name)
        if not prompt:
            prompt = f"Visual metaphor for the concept of {name}: {m.get('one_liner', '')}"

        print(f"[{i+1}/{len(models)}] {name}")
        icon_path = generate_icon(m, prompt)

        if icon_path:
            results[name] = icon_path
            generated += 1
        else:
            failed += 1

        if (i + 1) % 10 == 0:
            print(f"  --- Progress: {generated} generated, {failed} failed ---")

    print(f"\nDone: {generated} generated, {failed} failed")
    print(f"Estimated cost: ${generated * 0.015:.2f}")

    results_file = PROJECT_DIR / "scripts" / "icon-results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {results_file}")

if __name__ == "__main__":
    main()
