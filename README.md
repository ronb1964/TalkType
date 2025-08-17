# TalkType 🎤

**AI-powered voice dictation for Linux** - Hold F8, speak, and watch your words appear instantly!

Perfect for coding, writing, chatting, and accessibility. Uses Faster-Whisper for accurate offline transcription.

![TalkType Demo](https://img.shields.io/badge/Platform-Linux-blue) ![License](https://img.shields.io/badge/License-MIT-green) ![Status](https://img.shields.io/badge/Status-Active-brightgreen)

## ✨ Features

- 🎯 **Press & hold F8** to dictate - simple and intuitive
- 🔄 **Real-time transcription** using Faster-Whisper AI
- 🎨 **Smart formatting** with punctuation and line break commands  
- 💬 **Chat-friendly** - line breaks without submitting messages
- 🔒 **Privacy-focused** - everything runs locally, no cloud
- 🐧 **Wayland native** - built for modern Linux desktops
- ⚡ **GPU acceleration** - fast transcription with CUDA support

## 🚀 Quick Start

### Download & Run (Recommended)
1. **Download** the latest [TalkType AppImage](https://github.com/ronb1964/TalkType/releases)
2. **Make executable**: `chmod +x TalkType-x86_64.AppImage`
3. **Run**: `./TalkType-x86_64.AppImage`
4. **Hold F8** and start talking!

### Installation from Source
```bash
git clone https://github.com/ronb1964/TalkType.git
cd TalkType
poetry install
poetry run python -m src.talktype.tray
```

## 🎤 Basic Usage

1. **Start TalkType** - The microphone icon appears in your system tray
2. **Click "Start Service"** from the tray menu  
3. **Hold F8** and speak clearly
4. **Release F8** - Your speech appears as text!

## 📚 Voice Commands

TalkType supports powerful voice commands for formatting:

| Command | Result | Use Case |
|---------|--------|----------|
| `"new line"` | Line break (Shift+Enter) | Chat apps, Discord |
| `"new paragraph"` | Paragraph break | Documents, emails |
| `"comma"` | , | Punctuation |
| `"period"` | . | End sentences |
| `"question mark"` | ? | Questions |
| `"exclamation point"` | ! | Emphasis |

**📖 See the complete [Voice Commands Reference](VOICE_COMMANDS.md) for all available commands.**

## 🎯 Perfect For

- **💻 Coding** - Dictate variable names, comments, documentation
- **✍️ Writing** - Blogs, emails, documents with smart formatting
- **💬 Chatting** - Discord, Slack, Teams with line break control
- **♿ Accessibility** - Hands-free computer interaction
- **📝 Note-taking** - Fast capture of thoughts and ideas

## 🔧 System Requirements

- **OS**: Linux with Wayland (Fedora, Ubuntu 22+, etc.)
- **Audio**: Working microphone
- **GPU**: NVIDIA GPU recommended (CUDA acceleration)
- **Memory**: 4GB+ RAM recommended

## ⚙️ Configuration

Access settings through the system tray:
- **Preferences** - Language, hotkeys, audio settings
- **Start/Stop Service** - Control voice recognition
- **Microphone settings** - Audio input configuration

## 🔧 Development Setup

```bash
# Clone repository
git clone https://github.com/ronb1964/TalkType.git
cd TalkType

# Install dependencies
poetry install

# Run tests
poetry run pytest -q

# Start development version
poetry run python -m src.talktype.tray
```

## 📦 Building AppImage

```bash
# Switch to AppImage branch
git checkout appimage-builds

# Build AppImage
./build-appimage-clean.sh

# Test the result
./TalkType-x86_64.AppImage --help
```

## 🤝 Contributing

We welcome contributions! Please see our [development notes](DEV_NOTES.md) for technical details.

- 🐛 **Bug reports** - [Open an issue](https://github.com/ronb1964/TalkType/issues)
- 💡 **Feature requests** - Share your ideas!
- 🔧 **Pull requests** - Help improve TalkType

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- **Faster-Whisper** - Fast, accurate speech recognition
- **OpenAI Whisper** - Foundation model for transcription
- **ydotool** - Wayland input simulation
- **Python ecosystem** - NumPy, SoundDevice, and more

---

**🎤 Ready to start dictating?** [Download TalkType](https://github.com/ronb1964/TalkType/releases) and experience hands-free computing!

*Questions? Check out the [Voice Commands Guide](VOICE_COMMANDS.md) or [open an issue](https://github.com/ronb1964/TalkType/issues).*