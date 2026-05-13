# Free Tier Deployment Guide — CreditFraudService

## Platform Comparison

| Platform | RAM | CPU | Storage | LLM | Always-on | Best for |
|----------|-----|-----|---------|-----|-----------|---------|
| **HuggingFace Spaces** | 16 GB | 2 vCPU | 50 GB | Local Qwen2.5 | ✅ | AI/ML apps |
| **Oracle Cloud Free** | 24 GB | 4 ARM | 200 GB | Ollama+Qwen3 | ✅ | Production |
| **Render.com** | 512 MB | 0.1 | None | Groq/HF API | ❌ sleeps | Quick demo |
| **Fly.io** | 256 MB | shared | 3 GB vol | Groq/HF API | ❌ sleeps | API testing |
| **Railway** | 512 MB | shared | 1 GB | Groq/HF API | ❌ sleeps | CI/CD |

---

## Step 0 — Get a Free LLM API Key (required for Render/Fly/Railway)

### Option A: Groq (Recommended — fastest, free)
1. Sign up at **console.groq.com** (no credit card)
2. Go to **API Keys** → Create Key
3. Copy `gsk_...` key → set as `GROQ_API_KEY`
4. Free quota: **14,400 tokens/day**, models: Llama3, Mixtral

### Option B: HuggingFace Inference API (free, rate-limited)
1. Sign up at **huggingface.co** (no credit card)
2. Go to **Settings → Access Tokens** → New Token (read)
3. Copy `hf_...` token → set as `HF_API_TOKEN`

---

## Option 1 — Hugging Face Spaces (BEST free option — 16 GB RAM)

### Why HF Spaces?
- **16 GB RAM** — can run local Qwen2.5-0.5B without any API key
- **Persistent `/data` storage** — ChromaDB survives restarts
- Always-on (no sleep)
- One-click deploy from GitHub

### Deploy Steps

```bash
# 1. Install HF CLI
pip install huggingface-hub

# 2. Create a new Space
huggingface-cli repo create credit-fraud-service --type space --space-sdk docker

# 3. Clone your Space
git clone https://huggingface.co/spaces/YOUR_USERNAME/credit-fraud-service
cd credit-fraud-service

# 4. Copy the HF Dockerfile
cp /path/to/CreditFraudService/deploy/huggingface/Dockerfile.hf Dockerfile
cp /path/to/CreditFraudService/deploy/huggingface/README.md README.md

# 5. Copy the app source
cp -r /path/to/CreditFraudService/* .

# 6. Push to HF Spaces
git add -A && git commit -m "Deploy CreditFraudService"
git push

# Space builds automatically (~5 min first time)
# URL: https://YOUR_USERNAME-credit-fraud-service.hf.space
```

### Set Secrets on HF Spaces
In your Space → **Settings → Variables and secrets**:
```
GROQ_API_KEY    = gsk_...    (optional — for faster/better LLM)
HF_API_TOKEN    = hf_...     (optional — for HF Inference API)
```
Without secrets, it uses the local Qwen2.5-0.5B model (free, slower).

---

## Option 2 — Oracle Cloud Always Free (BEST for production)

Oracle provides **forever-free** VMs that are large enough to run everything including Ollama/Qwen3.

### Free Resources
- 4 ARM Ampere OCPUs + 24 GB RAM (A1 Flex instances)
- 200 GB block storage
- No time limit, no credit card auto-charge

### Setup Steps

```bash
# 1. Sign up at cloud.oracle.com (credit card required but never charged)

# 2. Create VM: Compute → Instances → Create Instance
#    Shape: VM.Standard.A1.Flex (ARM)
#    OCPU: 4, RAM: 24 GB
#    OS: Ubuntu 22.04 (ARM)
#    Storage: 200 GB

# 3. SSH into instance
ssh ubuntu@YOUR_IP

# 4. Install dependencies
sudo apt update && sudo apt install -y python3.11 python3-pip git docker.io docker-compose

# 5. Install Ollama (ARM build)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:latest            # pulls ~4 GB model

# 6. Clone and run the service
git clone https://github.com/vicky9685/CreditFraudService
cd CreditFraudService
cp .env.example .env
# Edit .env: OLLAMA_BASE_URL=http://localhost:11434

# Option A: Docker Compose (recommended)
docker compose up -d

# Option B: Direct Python
pip install -r requirements.txt
python main.py
```

### Open Firewall
```bash
# In OCI Console → Networking → Security Lists → add ingress rules:
# Port 8000 (API), 3000 (Grafana), 9090 (Prometheus)

# Or via CLI:
oci network security-list update --security-list-id OCID \
  --ingress-security-rules '[{"protocol":"6","source":"0.0.0.0/0","tcpOptions":{"destinationPortRange":{"min":8000,"max":8000}}}]'
```

---

## Option 3 — Render.com (512 MB RAM, sleeps after 15 min)

```bash
# 1. Push code to GitHub

# 2. At dashboard.render.com:
#    New → Web Service → Connect GitHub repo
#    Name: credit-fraud-service
#    Runtime: Python 3
#    Build: pip install -r requirements-free-tier.txt && pip install torch --index-url https://download.pytorch.org/whl/cpu
#    Start: python main.py

# 3. Environment Variables (in Render dashboard):
#    GROQ_API_KEY = gsk_...
#    APP_ENV = production

# 4. Deploy → your URL: https://credit-fraud-service.onrender.com

# NOTE: Free tier sleeps after 15 min idle — first request takes ~30 s to wake
```

Or use `render.yaml` (auto-detected):
```bash
# render.yaml is already in the repo root — Render picks it up automatically
```

---

## Option 4 — Fly.io (256 MB free, persistent volume)

```bash
# 1. Install flyctl
curl -L https://fly.io/install.sh | sh

# 2. Login
flyctl auth login

# 3. Launch (uses fly.toml in repo root)
flyctl launch --name credit-fraud-service --no-deploy

# 4. Create persistent volume for ChromaDB
flyctl volumes create fraud_data --size 1 --region iad

# 5. Set API key secret
flyctl secrets set GROQ_API_KEY=gsk_...

# 6. Deploy
flyctl deploy

# URL: https://credit-fraud-service.fly.dev
```

---

## Option 5 — Railway (easiest CI/CD, $5 free credit/month)

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Init project (from repo root)
railway init

# 4. Set environment variables
railway variables set GROQ_API_KEY=gsk_...
railway variables set APP_ENV=production

# 5. Deploy
railway up

# URL shown in dashboard: https://credit-fraud-service.railway.app
```

---

## LLM Backend Auto-Selection

The app tries backends in this order automatically:

```
GROQ_API_KEY set?     → Groq (fastest, 14k tokens/day free)
    ↓ no
HF_API_TOKEN set?     → HuggingFace Inference API (free, rate-limited)
    ↓ no
Ollama running?       → Ollama + Qwen3 (local, zero cost)
    ↓ no
16 GB+ RAM?           → Local Qwen2.5-0.5B via transformers
    ↓ no
                      → Rule-based mock (always works, no LLM)
```

No API key = rule-based fraud detection still works perfectly.
Add `GROQ_API_KEY` for natural language RAG answers.

---

## Free Tier Limitations & Workarounds

| Limitation | Affected Platforms | Workaround |
|-----------|-------------------|-----------|
| App sleeps after 15 min | Render, Railway | Use UptimeRobot (free) to ping `/health` every 10 min |
| No persistent disk | Render free | KB re-indexes on startup (~5 s) — acceptable |
| 512 MB RAM | Render, Railway | Use `requirements-free-tier.txt` (no heavy torch) |
| No Ollama | All cloud free | Use GROQ_API_KEY (free, fast) |
| Rate limits | Groq | 14,400 tokens/day = ~200 fraud analyses |

### Keep Render/Railway Awake (Optional)
```bash
# UptimeRobot (free): monitor.uptimerobot.com
# Add HTTP monitor → your URL/health → interval 5 min
# This prevents the 30-second cold start on free tier
```

---

## Quick Start (any free platform)

```bash
# 1. Get a free Groq API key at console.groq.com

# 2. Set environment variables on your chosen platform:
GROQ_API_KEY=gsk_your_key_here
APP_ENV=production

# 3. Deploy using one of:
#    - render.yaml (Render.com)
#    - fly.toml (Fly.io)
#    - railway.json (Railway)
#    - deploy/huggingface/Dockerfile.hf (HF Spaces)

# 4. Hit your URL:
curl https://YOUR-APP.onrender.com/health
curl https://YOUR-APP.onrender.com/docs    # Swagger UI
```
