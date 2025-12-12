# Image Generation Tools for Claude Code

Research completed: 2025-10-22

## Overview

This document catalogs image generation tools that can be integrated into Claude Code via MCP (Model Context Protocol) servers. These tools enable AI-assisted design, mockup creation, and visual content generation for TalkType development.

---

## 🎨 Tool Categories

### 1. Cloud API-Based Services (Require API Keys)
- **Pros:** High quality, no local hardware requirements, fast setup
- **Cons:** Requires API keys, costs money, internet dependency

### 2. Local/Self-Hosted (Run on Your Machine)
- **Pros:** Free (after setup), private, no internet needed, unlimited use
- **Cons:** Requires GPU, initial setup complexity, storage space

---

## ☁️ Cloud API-Based MCP Servers

### 1. Google Imagen 3 MCP Server
**Repository:** [hamflx/imagen3-mcp](https://github.com/hamflx/imagen3-mcp)
**Language:** Rust
**Platform Support:** Windows, macOS, Linux

**Features:**
- High-quality image generation via Google's Imagen 3.0
- Fast generation times
- Professional quality outputs

**Requirements:**
- Google Gemini API key (free tier available)

**Installation for Claude Code:**
```bash
# Download from releases
wget https://github.com/hamflx/imagen3-mcp/releases/latest/download/imagen3-mcp

# Make executable
chmod +x imagen3-mcp

# Add to Claude Code MCP config
claude mcp add imagen3 ./imagen3-mcp --env GEMINI_API_KEY=your-key-here
```

**Use Cases:**
- High-quality UI mockups
- Marketing materials
- Icon concepts
- Design exploration

---

### 2. Fal.ai MCP Server (Multiple Models)
**Repository:** [raveenb/fal-mcp-server](https://github.com/raveenb/fal-mcp-server)
**Language:** Python
**Platform Support:** All platforms (Docker recommended)

**Features:**
- Multiple models: FLUX, Stable Diffusion, MusicGen
- Image, video, and audio generation
- Modern HTTP/SSE transport support

**Requirements:**
- Fal.ai API key (free tier available)
- Python 3.10+

**Installation:**

**Option A: Docker (Recommended):**
```bash
docker pull ghcr.io/raveenb/fal-mcp-server:latest
docker run -d -e FAL_KEY=your-key -p 8080:8080 ghcr.io/raveenb/fal-mcp-server:latest
```

**Option B: PyPI:**
```bash
pip install fal-mcp-server

# Add to Claude Code config
claude mcp add fal-ai "python -m fal_mcp_server.server" --env FAL_KEY=your-key
```

**Use Cases:**
- Versatile image generation
- Video mockups
- Audio/music generation
- Multiple style options

---

### 3. OpenAI DALL-E MCP Server
**Repository:** [SureScaleAI/openai-gpt-image-mcp](https://github.com/SureScaleAI/openai-gpt-image-mcp)
**Language:** JavaScript/TypeScript
**Platform Support:** All platforms

**Features:**
- DALL-E 3 image generation
- Image editing (inpainting, outpainting)
- Compositing capabilities
- Large file handling

**Requirements:**
- OpenAI API key (verified organization account required)
- Node.js

**Installation:**
```bash
git clone https://github.com/SureScaleAI/openai-gpt-image-mcp.git
cd openai-gpt-image-mcp
yarn install
yarn build

# Add to Claude Code config (adjust path)
claude mcp add openai-image "node /path/to/dist/index.js" --env OPENAI_API_KEY=sk-...
```

**Use Cases:**
- Natural language image generation
- Image editing and modification
- Compositing multiple elements
- High-quality concept art

---

## 🖥️ Local/Self-Hosted MCP Servers

These connect to Stable Diffusion WebUI running locally on your machine.

### Prerequisites for Local Generation

1. **Install Stable Diffusion WebUI:**
```bash
git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git
cd stable-diffusion-webui

# Run with API enabled
./webui.sh --api --listen
```

2. **Download a model** (e.g., Stable Diffusion 1.5 or XL)
3. **Verify API access:** Visit `http://localhost:7860/docs`

---

### 1. Image Gen MCP Server (Recommended for Local)
**Repository:** [Ichigo3766/image-gen-mcp](https://github.com/Ichigo3766/image-gen-mcp)
**Language:** JavaScript/TypeScript
**Platform Support:** All platforms

**Features:**
- Text-to-image generation
- Model switching
- Image upscaling
- Full SD WebUI parameter support (steps, CFG, seed, etc.)

**Installation:**
```bash
git clone https://github.com/Ichigo3766/image-gen-mcp.git
cd image-gen-mcp
npm install
npm run build

# Configure environment
export SD_WEBUI_URL=http://localhost:7860
export SD_OUTPUT_DIR=/home/ron/Pictures/AI-Generated

# Add to Claude Code
claude mcp add image-gen "node /path/to/image-gen-mcp/build/index.js" \
  --env SD_WEBUI_URL=http://localhost:7860 \
  --env SD_OUTPUT_DIR=/home/ron/Pictures/AI-Generated
```

**Use Cases:**
- Unlimited free generation
- Full control over models and parameters
- Privacy (no data leaves your machine)
- Custom model support (LoRA, embeddings)

---

### 2. Enhanced Stable Diffusion MCP
**Repository:** [hkhkkh/enhanced-stable-diffusion-mcp](https://github.com/hkhkkh/enhanced-stable-diffusion-mcp)
**Status:** Repository appears to be private/404

**Features (if accessible):**
- Text-to-image
- Image-to-image
- Model switching
- LoRA support
- Full-featured AI art generation

---

### 3. SD WebUI MCP
**Repository:** [boxi-rgb/sd-webui-mcp](https://github.com/boxi-rgb/sd-webui-mcp)
**Language:** TypeScript
**Platform Support:** All platforms

Integrates Claude Desktop directly with Stable Diffusion WebUI.

---

### 4. DiffuGen
**Repository:** [CLOUDWERX-DEV/diffugen](https://github.com/CLOUDWERX-DEV/diffugen)
**Language:** Unknown
**Platform Support:** Local/edge deployment

User-friendly interface for local image generation with multiple AI model support.

---

## 🎯 Recommendations for TalkType Development

### Best Overall: **Fal.ai MCP Server** (Cloud)
- **Why:** Multiple models, easy setup, generous free tier
- **Cost:** Free tier available, then pay-as-you-go
- **Setup time:** 5 minutes
- **Best for:** Quick mockups, design exploration

### Best for Privacy/Unlimited Use: **Image Gen MCP** (Local)
- **Why:** Free unlimited generation, full control, privacy
- **Cost:** Free (hardware already owned)
- **Setup time:** 30-60 minutes (one-time)
- **Best for:** Iterative design, bulk generation, experimentation

### Best for Quality: **Google Imagen 3 MCP** (Cloud)
- **Why:** Highest quality outputs
- **Cost:** Pay-per-image
- **Setup time:** 5 minutes
- **Best for:** Final marketing materials, high-stakes designs

---

## 📊 Quick Comparison

| Tool | Type | Cost | Quality | Speed | Setup |
|------|------|------|---------|-------|-------|
| Imagen 3 | Cloud | $$ | ⭐⭐⭐⭐⭐ | Fast | Easy |
| Fal.ai | Cloud | $ | ⭐⭐⭐⭐ | Fast | Easy |
| OpenAI | Cloud | $$$ | ⭐⭐⭐⭐⭐ | Fast | Medium |
| Image Gen MCP | Local | Free | ⭐⭐⭐⭐ | Medium | Medium |
| SD WebUI Direct | Local | Free | ⭐⭐⭐⭐ | Medium | Complex |

---

## 🚀 Getting Started (Step-by-Step)

### Quick Start: Fal.ai (Cloud, 5 minutes)

1. **Get API key:**
   - Visit https://fal.ai
   - Sign up for free account
   - Get API key from dashboard

2. **Install via PyPI:**
```bash
pip install fal-mcp-server
```

3. **Add to Claude Code:**
```bash
claude mcp add fal-ai "python -m fal_mcp_server.server" --env FAL_KEY=your-key-here
```

4. **Test it:**
   Ask me: "Generate an image of a modern GTK application preferences window with dark theme"

---

### Complete Setup: Local Stable Diffusion (1-2 hours)

**Step 1: Install Stable Diffusion WebUI**
```bash
cd ~/software
git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git
cd stable-diffusion-webui
./webui.sh --api --listen
```

**Step 2: Download a model** (first run will prompt)
- Recommended: Stable Diffusion XL 1.0
- Or use Stable Diffusion 1.5 for faster generation

**Step 3: Install Image Gen MCP**
```bash
cd ~/software
git clone https://github.com/Ichigo3766/image-gen-mcp.git
cd image-gen-mcp
npm install
npm run build
```

**Step 4: Configure output directory**
```bash
mkdir -p ~/Pictures/AI-Generated
```

**Step 5: Add to Claude Code**
```bash
claude mcp add image-gen \
  "node $HOME/software/image-gen-mcp/build/index.js" \
  --env SD_WEBUI_URL=http://localhost:7860 \
  --env SD_OUTPUT_DIR=$HOME/Pictures/AI-Generated
```

**Step 6: Test it**
```bash
# Ensure SD WebUI is running first
cd ~/software/stable-diffusion-webui
./webui.sh --api --listen --nowebui  # headless mode

# Then ask me to generate an image
```

---

## 💡 Usage Examples for TalkType

### UI Mockup Generation
```
"Generate a mockup of a GTK preferences window with these sections:
- General settings
- Model selection dropdown
- Hotkey configuration
- Dark theme with blue accent colors
- Following GNOME Human Interface Guidelines"
```

### Icon Design
```
"Create an icon for a Linux dictation app:
- Microphone symbol
- Modern, flat design
- Suitable for 256x256px
- Colors: blue and white
- Transparent background"
```

### Dialog Concept
```
"Design a welcome dialog for a voice transcription app:
- Friendly, inviting layout
- Shows key features with icons
- 'Get Started' button
- Dark theme compatible"
```

### Marketing Material
```
"Create a hero image for a GitHub readme:
- Screenshot-style mockup
- Shows app in use on Linux desktop
- Modern, professional
- 1200x630px for social sharing"
```

---

## 🔧 Integration with TalkType Workflow

### Phase 1: Design Exploration
1. Generate mockups of new features
2. Compare different visual styles
3. Get user feedback before coding

### Phase 2: Asset Creation
1. Generate icons and graphics
2. Create marketing materials
3. Design dialog layouts

### Phase 3: Documentation
1. Create visual examples for README
2. Generate tutorial images
3. Design feature showcase graphics

---

## ⚠️ Important Notes

### API Key Security
- Never commit API keys to git
- Use environment variables
- Consider using `.env` files (gitignored)

### Cost Management
- Start with free tiers
- Monitor usage
- Set budget alerts
- Use local generation for experimentation

### Quality vs Speed
- Cloud: High quality, fast, costs money
- Local: Good quality, slower, free unlimited

### Privacy Considerations
- Cloud: Images sent to third-party APIs
- Local: Everything stays on your machine

---

## 📚 Additional Resources

- [Model Context Protocol Docs](https://modelcontextprotocol.io/)
- [Stable Diffusion WebUI Wiki](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki)
- [Fal.ai Documentation](https://fal.ai/docs)
- [Google Imagen API](https://cloud.google.com/vertex-ai/docs/generative-ai/image/overview)
- [OpenAI Image API](https://platform.openai.com/docs/guides/images)

---

## 🎯 Next Steps

1. **Choose your approach:**
   - Quick testing: Fal.ai (cloud, free tier)
   - Serious usage: Local Stable Diffusion
   - Best quality: Imagen 3 or OpenAI

2. **Set up MCP server:**
   - Follow installation steps above
   - Test with simple generation

3. **Integrate into workflow:**
   - Start generating UI mockups
   - Get feedback before implementing
   - Use for documentation and marketing

4. **Update DEVELOPMENT_PLAN.md:**
   - Mark image generation as ✅ complete
   - Add to regular development workflow

---

## 🤝 Contributing

Found a better MCP image generation server? Open an issue or PR to add it to this list!

---

**Last Updated:** 2025-10-22
**Status:** Research complete, ready for implementation
