# Stable Diffusion Local Image Generation - Setup Complete!

**Setup Date:** 2025-10-22
**Status:** ✅ Ready to use

---

## 🎉 What's Installed

### 1. Stable Diffusion WebUI
- **Location:** `~/software/stable-diffusion-webui`
- **Model:** Stable Diffusion v1.5 (4GB)
- **Python:** 3.10 (in dedicated venv)
- **GPU:** NVIDIA RTX 4070 Ti (12GB VRAM)

### 2. Image Gen MCP Server
- **Location:** `~/software/image-gen-mcp`
- **Integration:** Added to Claude Code
- **Output Directory:** `~/Pictures/AI-Generated`

---

## 🚀 How to Use

### Step 1: Start the SD WebUI API Server

**In a terminal, run:**
```bash
cd ~/software/stable-diffusion-webui
./start-api.sh
```

**You'll see:**
```
🎨 Starting Stable Diffusion WebUI with API...

API will be available at: http://localhost:7861
API docs: http://localhost:7861/docs
```

**Wait for:**
```
Model loaded in X.Xs...
Uvicorn running on http://0.0.0.0:7861
```

**Keep this terminal running** while you generate images.

---

### Step 2: Generate Images with Claude Code

Once the server is running, you can ask me to generate images!

**Example prompts:**
- "Generate an image of a modern GTK preferences window with dark theme"
- "Create a UI mockup for TalkType's welcome dialog"
- "Design an icon for a Linux dictation app"
- "Generate a screenshot-style image of a recording indicator overlay"

**The workflow:**
1. You ask for an image
2. I use the Image Gen MCP tool
3. Image generates in 5-15 seconds
4. Image saves to `~/Pictures/AI-Generated/`
5. I can view and show you the result

---

## ⚡ Performance

**Generation Speed (RTX 4070 Ti):**
- **512x512:** ~5-8 seconds
- **768x768:** ~10-12 seconds
- **1024x1024:** ~15-20 seconds

**First generation** after starting takes a bit longer as the model loads into VRAM.

---

## 📁 File Locations

```
~/software/
├── stable-diffusion-webui/          # Main SD WebUI installation
│   ├── models/Stable-diffusion/     # Model files
│   │   └── sd_v1-5.safetensors      # SD 1.5 model (4GB)
│   ├── start-api.sh                 # Helper script to start API
│   └── venv/                        # Python 3.10 venv
└── image-gen-mcp/                   # MCP server for Claude Code
    └── build/index.js               # MCP server entry point

~/Pictures/AI-Generated/             # Your generated images appear here
```

---

## 🔧 Useful Commands

### Check if API is running:
```bash
curl http://localhost:7861/sdapi/v1/sd-models
```

### View API documentation:
Open in browser: http://localhost:7861/docs

### Stop the server:
Press `Ctrl+C` in the terminal where `start-api.sh` is running

### View generated images:
```bash
ls -lh ~/Pictures/AI-Generated/
```

---

## 🎨 Advanced Usage

### Change Image Parameters

When asking for images, you can specify:
- **Size:** "Generate a 1024x1024 image of..."
- **Style:** "photorealistic", "artistic", "sketch", "3D render"
- **Details:** More detailed prompts = better results

### Quality Tips

**Good prompt:**
```
"A modern GTK application preferences window with dark theme,
showing tabs for General, Models, and Hotkeys. Clean GNOME HIG
design, professional UI, high quality screenshot"
```

**Better than:**
```
"A settings window"
```

---

## 💾 Disk Space Usage

**Current:**
- SD WebUI: ~2GB
- Model (SD 1.5): ~4GB
- Dependencies: ~1GB
- **Total: ~7GB**

**Generated images:** ~1-5MB each

---

## 🔄 Updating

### Update SD WebUI:
```bash
cd ~/software/stable-diffusion-webui
git pull
```

### Update Image Gen MCP:
```bash
cd ~/software/image-gen-mcp
git pull
npm install
npm run build
```

---

## ⚠️ Important: First-Time Setup

**After installing the MCP server, you MUST restart Claude Code once.**

MCP servers are only loaded when Claude Code starts. After the initial installation:
1. Close and restart Claude Code
2. Start the SD WebUI server: `cd ~/software/stable-diffusion-webui && ./start-api.sh`
3. Ask me to generate images - it will work!

You only need to restart Claude Code once. After that, just start the server when needed.

---

## 🛠️ Troubleshooting

### "I don't have image generation tools available":
- **Cause:** Claude Code needs to be restarted after MCP server installation
- **Fix:** Close and restart Claude Code once

### Server won't start:
```bash
# Kill any existing SD processes
pkill -f "webui.sh"

# Try starting again
cd ~/software/stable-diffusion-webui
./start-api.sh
```

### Generation fails:
1. Check server is running: `curl http://localhost:7861/sdapi/v1/sd-models`
2. Check logs: `tail -100 /tmp/sd-webui.log`
3. Restart the server

### Out of VRAM:
- Try smaller image sizes (512x512 instead of 1024x1024)
- Close other GPU-heavy applications

### Slow generation:
- Normal for first generation (model loading)
- Subsequent generations should be faster
- Check if other apps are using GPU: `nvidia-smi`

---

## 📊 Comparison: Local vs Cloud

| Aspect | Local (Your Setup) | Cloud (Fal.ai/OpenAI) |
|--------|-------------------|----------------------|
| Cost | Free (unlimited) | Pay per image |
| Speed | 5-15 sec | 3-10 sec |
| Quality | Good | Excellent |
| Privacy | 100% local | Sent to API |
| Internet | Not needed | Required |
| Setup | 1 hour (done!) | 5 minutes |

**Your setup is perfect for:**
- Iterative design work
- Experimentation
- Privacy-sensitive projects
- Unlimited generation

---

## 🎯 Next Steps

### 1. Test It Out!
Start the server and ask me to generate a test image.

### 2. Download More Models (Optional)
Visit: https://civitai.com or https://huggingface.co
- Place models in: `~/software/stable-diffusion-webui/models/Stable-diffusion/`
- Restart server to use them

### 3. Explore Styles
Try different prompts to find styles you like for TalkType mockups.

---

## 📚 Resources

- [SD WebUI GitHub](https://github.com/AUTOMATIC1111/stable-diffusion-webui)
- [SD WebUI Wiki](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki)
- [Prompt Engineering Guide](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/Features#prompt-syntax)
- [Model Hub](https://civitai.com)

---

## ✅ Verification Checklist

- [x] Stable Diffusion WebUI installed
- [x] SD 1.5 model downloaded
- [x] Image Gen MCP server installed
- [x] MCP server added to Claude Code
- [x] API server tested and working
- [x] Output directory created
- [x] Helper scripts created

---

**Everything is ready! Just start the server and ask me to generate images!**

**Quick Start:**
```bash
# Terminal 1: Start SD WebUI
cd ~/software/stable-diffusion-webui && ./start-api.sh

# Then ask me in Claude Code:
# "Generate an image of a modern Linux app preferences window"
```

---

**Last Updated:** 2025-10-22
**Installation Time:** ~1 hour
**Ready to use:** Yes ✅
