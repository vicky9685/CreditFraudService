#!/usr/bin/env python3
"""
deploy_to_hf_spaces.py — One-click deployment to Hugging Face Spaces.

Usage (run on YOUR machine):
    # Set your keys first:
    export HF_TOKEN=hf_...
    export GROQ_API_KEY=gsk_...

    pip install huggingface-hub
    python deploy/huggingface/deploy_to_hf_spaces.py

What it does:
  1. Authenticates with your HF token
  2. Creates a new Space (or reuses existing)
  3. Uploads the full application
  4. Sets GROQ_API_KEY and HF_API_TOKEN as Space secrets
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

# ── Keys read from environment (never hardcode secrets in source) ─────────────
HF_TOKEN     = os.environ.get("HF_TOKEN") or os.environ.get("HF_API_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
SPACE_NAME   = os.environ.get("HF_SPACE_NAME", "credit-fraud-service")
REPO_ROOT    = Path(__file__).parent.parent.parent   # CreditFraudService/

IGNORE = {
    ".env", ".git", "__pycache__", "chroma_db", "logs",
    ".pytest_cache", "*.pyc", "*.pyo", "dist", "build",
    "htmlcov", ".coverage",
}


def main():
    if not HF_TOKEN:
        print("ERROR: HF_TOKEN is not set.")
        print("  export HF_TOKEN=hf_...")
        sys.exit(1)

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("Installing huggingface-hub...")
        os.system(f"{sys.executable} -m pip install huggingface-hub -q")
        from huggingface_hub import HfApi

    api = HfApi(token=HF_TOKEN)

    # ── 1. Get username ───────────────────────────────────────────────────────
    print("Authenticating with Hugging Face...")
    user = api.whoami()
    username = user["name"]
    repo_id  = f"{username}/{SPACE_NAME}"
    print(f"  Logged in as : {username}")
    print(f"  Space target : https://huggingface.co/spaces/{repo_id}")

    # ── 2. Create Space (idempotent) ──────────────────────────────────────────
    print(f"\nCreating Space '{repo_id}' ...")
    api.create_repo(
        repo_id=repo_id,
        repo_type="space",
        space_sdk="docker",
        private=False,
        exist_ok=True,
    )
    print("  Space ready.")

    # ── 3. Prepare upload directory ───────────────────────────────────────────
    print("\nPreparing files for upload...")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        for item in REPO_ROOT.iterdir():
            if item.name in IGNORE or item.name.startswith("."):
                continue
            dest = tmp_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, ignore=shutil.ignore_patterns(*IGNORE))
            else:
                shutil.copy2(item, dest)

        # Use HF-specific Dockerfile (port 7860)
        hf_dockerfile = REPO_ROOT / "deploy" / "huggingface" / "Dockerfile.hf"
        if hf_dockerfile.exists():
            shutil.copy2(hf_dockerfile, tmp_path / "Dockerfile")
            print("  Using HF Spaces Dockerfile (port 7860)")

        # Write Space README with metadata header
        (tmp_path / "README.md").write_text(
            "---\n"
            "title: Credit Fraud Detection Service\n"
            "emoji: 🔍\n"
            "colorFrom: red\n"
            "colorTo: orange\n"
            "sdk: docker\n"
            "app_port: 7860\n"
            "pinned: false\n"
            "license: mit\n"
            "short_description: Enterprise Credit Fraud Detection with RAG + ADK + MCP\n"
            "---\n\n"
            "# Credit Fraud Detection Service\n\n"
            "Enterprise credit card fraud detection powered by RAG (ChromaDB + "
            "sentence-transformers), Google ADK agents, MCP, Groq LLM, and "
            "enterprise AI governance.\n\n"
            "**API docs:** [/docs](./docs)\n"
        )

        # ── 4. Upload ─────────────────────────────────────────────────────────
        print(f"\nUploading to {repo_id} ...")
        api.upload_folder(
            folder_path=str(tmp_path),
            repo_id=repo_id,
            repo_type="space",
            commit_message="Deploy CreditFraudService — RAG, ADK, MCP, governance",
            ignore_patterns=["*.pyc", "__pycache__", "*.pyo"],
        )
        print("  Upload complete.")

    # ── 5. Set Secrets ────────────────────────────────────────────────────────
    print("\nSetting Space secrets...")
    if GROQ_API_KEY:
        api.add_space_secret(repo_id=repo_id, key="GROQ_API_KEY", value=GROQ_API_KEY)
        print("  GROQ_API_KEY  ✓")
    else:
        print("  GROQ_API_KEY  skipped (not set in env)")

    api.add_space_secret(repo_id=repo_id, key="HF_API_TOKEN", value=HF_TOKEN)
    print("  HF_API_TOKEN  ✓")

    # ── 6. Done ───────────────────────────────────────────────────────────────
    slug = SPACE_NAME.replace("-", "-")
    print(f"""
══════════════════════════════════════════════════════
  Deployment submitted!

  Space     : https://huggingface.co/spaces/{repo_id}
  API docs  : https://{username}-{slug}.hf.space/docs
  Health    : https://{username}-{slug}.hf.space/health
  Build log : https://huggingface.co/spaces/{repo_id}/logs

  First build takes ~5 min (Docker + model download).
══════════════════════════════════════════════════════
""")


if __name__ == "__main__":
    main()
