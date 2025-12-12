# TalkType Visual Style Guide
**Cyberpunk Minimal Aesthetic**

**Version:** 1.0
**Created:** 2025-10-22
**Design Philosophy:** Professional AI-powered dictation with subtle futuristic flair

---

## 🎨 Design Philosophy

TalkType combines **professional minimalism** with **subtle cyberpunk aesthetics** to create an interface that feels modern, powerful, and accessible. The design should evoke AI-powered technology without being garish or unprofessional.

**Core Principles:**
- **Minimal but memorable** - Clean layouts with strategic accent colors
- **Professional first** - Suitable for work environments
- **Subtle glows** - Not neon-everywhere, but tasteful highlights
- **Dark theme native** - Designed for dark mode, not adapted to it
- **Accessibility** - High contrast, clear typography, colorblind-friendly

---

## 🌈 Color Palette

### Primary Colors

**Background Layers:**
```
Dark Base:       #1a1a1f  (Very dark charcoal)
Surface:         #252530  (Dark gray-purple)
Elevated:        #2d2d3a  (Slightly lighter surface)
```

**Accent Colors:**
```
Cyan Glow:       #00d9ff  (Primary accent - info, active states)
Magenta Accent:  #ff006e  (Secondary accent - warnings, highlights)
Gold Glow:       #ffd60a  (Current yellow glow - success, recording)
Purple Ambient:  #7c3aed  (Ambient lighting, shadows)
```

**Status Colors:**
```
Success Green:   #10b981  (Checkmarks, successful operations)
Error Red:       #ef4444  (Errors, cancel buttons)
Warning Orange:  #f59e0b  (Warnings, cautions)
Info Cyan:       #00d9ff  (Information, help)
```

**Text Colors:**
```
Primary Text:    #e5e7eb  (High contrast white-gray)
Secondary Text:  #9ca3af  (Muted gray for labels)
Disabled Text:   #4b5563  (Very muted for disabled states)
```

### Gradients

**Purple-Cyan Ambient:**
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #00d9ff 100%);
```

**Gold Glow (Recording State):**
```css
background: radial-gradient(circle, #ffd60a 0%, transparent 70%);
```

**Glass Overlay:**
```css
background: rgba(255, 255, 255, 0.05);
backdrop-filter: blur(10px);
```

---

## ✨ Visual Effects

### Glow Effects

**Subtle Button Glow (Hover):**
```css
box-shadow: 0 0 15px rgba(0, 217, 255, 0.3);
```

**Active Element Glow:**
```css
box-shadow: 0 0 20px rgba(0, 217, 255, 0.5),
            0 0 40px rgba(0, 217, 255, 0.2);
```

**Recording Indicator (Existing Gold Glow):**
```css
box-shadow: 0 0 30px rgba(255, 214, 10, 0.6),
            0 0 60px rgba(255, 214, 10, 0.3);
animation: pulse 2s ease-in-out infinite;
```

**Error State Glow:**
```css
box-shadow: 0 0 15px rgba(239, 68, 68, 0.4);
```

### Glassmorphism

**Dialog Backgrounds:**
```css
background: rgba(37, 37, 48, 0.85);
backdrop-filter: blur(20px) saturate(150%);
border: 1px solid rgba(255, 255, 255, 0.1);
border-radius: 12px;
```

**Floating Panels:**
```css
background: rgba(45, 45, 58, 0.7);
backdrop-filter: blur(15px);
box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
```

### Shadows & Depth

**Card Elevation:**
```css
box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3),
            0 1px 4px rgba(0, 0, 0, 0.2);
```

**Floating Dialog:**
```css
box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5),
            0 0 1px rgba(0, 217, 255, 0.2);
```

---

## 🎯 Component Styles

### Buttons

**Primary Button (Cyan Accent):**
```css
background: linear-gradient(135deg, #0ea5e9 0%, #00d9ff 100%);
color: #ffffff;
border: none;
border-radius: 6px;
padding: 8px 16px;
transition: all 0.2s ease;

/* Hover */
box-shadow: 0 0 20px rgba(0, 217, 255, 0.4);
transform: translateY(-1px);
```

**Secondary Button (Outlined):**
```css
background: transparent;
border: 1px solid #00d9ff;
color: #00d9ff;
border-radius: 6px;
padding: 8px 16px;

/* Hover */
background: rgba(0, 217, 255, 0.1);
box-shadow: 0 0 15px rgba(0, 217, 255, 0.2);
```

**Danger Button:**
```css
background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
/* Same hover effects as primary */
```

### Input Fields

**Text Input:**
```css
background: rgba(255, 255, 255, 0.05);
border: 1px solid rgba(255, 255, 255, 0.1);
border-radius: 6px;
padding: 8px 12px;
color: #e5e7eb;

/* Focus */
border-color: #00d9ff;
box-shadow: 0 0 10px rgba(0, 217, 255, 0.2);
outline: none;
```

**Dropdown/Combo Box:**
```css
background: rgba(255, 255, 255, 0.05);
border: 1px solid rgba(255, 255, 255, 0.1);
border-radius: 6px;

/* Active */
border-color: #00d9ff;
box-shadow: 0 0 15px rgba(0, 217, 255, 0.2);
```

### Checkboxes & Switches

**Checkbox (Checked):**
```css
background: linear-gradient(135deg, #00d9ff 0%, #0ea5e9 100%);
border: none;
box-shadow: 0 0 10px rgba(0, 217, 255, 0.3);
```

**Toggle Switch:**
```css
background: rgba(255, 255, 255, 0.1);  /* Off */
background: #00d9ff;  /* On, with glow */
box-shadow: 0 0 15px rgba(0, 217, 255, 0.4);
```

### Tabs

**Active Tab:**
```css
border-bottom: 2px solid #00d9ff;
color: #00d9ff;
box-shadow: 0 2px 8px rgba(0, 217, 255, 0.2);
```

**Inactive Tab:**
```css
color: #9ca3af;
transition: all 0.2s ease;

/* Hover */
color: #e5e7eb;
```

---

## 🌟 Special Elements

### Recording Indicator

**The Gold Glow (Keep Existing!):**
```css
background: radial-gradient(circle, #ffd60a 0%, rgba(255, 214, 10, 0.3) 50%, transparent 100%);
box-shadow: 0 0 30px rgba(255, 214, 10, 0.6),
            0 0 60px rgba(255, 214, 10, 0.3),
            0 0 100px rgba(255, 214, 10, 0.1);
animation: pulse 2s ease-in-out infinite;
```

**Optional: Add waveform visualization when recording**

### Info Icons (💡 Emoji)

**Enhancement Idea - Add CSS glow to emoji:**
```css
.info-icon {
    filter: drop-shadow(0 0 3px rgba(255, 214, 10, 0.5));
}
```

### Welcome/Splash Screen

**Background:**
```css
background: linear-gradient(135deg,
    #1a1a1f 0%,
    #252530 50%,
    #2d2d3a 100%);
```

**Logo/Icon Glow:**
```css
box-shadow: 0 0 40px rgba(0, 217, 255, 0.4),
            0 0 80px rgba(124, 58, 237, 0.2);
```

---

## 📐 Spacing & Typography

### Spacing System

```
xs:  4px
sm:  8px
md:  16px
lg:  24px
xl:  32px
2xl: 48px
```

### Typography

**Font Family:**
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
             'Roboto', 'Helvetica Neue', Arial, sans-serif;
```

**Font Sizes:**
```
Heading 1: 24px (bold)
Heading 2: 20px (semibold)
Heading 3: 18px (semibold)
Body:      14px (regular)
Small:     12px (regular)
Tiny:      10px (regular)
```

**Line Height:**
```
Headings: 1.2
Body:     1.5
```

---

## 🎬 Animations

### Transitions

**Standard Transition:**
```css
transition: all 0.2s ease;
```

**Slow Transition (Glow effects):**
```css
transition: all 0.3s ease-out;
```

### Pulse Animation (Recording)

```css
@keyframes pulse {
    0%, 100% {
        opacity: 1;
        transform: scale(1);
    }
    50% {
        opacity: 0.7;
        transform: scale(1.05);
    }
}
```

### Fade In

```css
@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}
```

### Glow Pulse

```css
@keyframes glowPulse {
    0%, 100% {
        box-shadow: 0 0 20px rgba(0, 217, 255, 0.3);
    }
    50% {
        box-shadow: 0 0 30px rgba(0, 217, 255, 0.6);
    }
}
```

---

## 🚀 Implementation Priority

### Phase 1: Quick Wins (Immediate Impact)
1. ✅ **Keep existing yellow glow** - It's already perfect!
2. Add cyan border glow to focused inputs
3. Add subtle glow to primary buttons on hover
4. Apply glassmorphism to dialogs (blur background)

### Phase 2: Enhanced Accents
5. Add cyan accent to active tab
6. Glow effect on checkbox when checked
7. Subtle purple ambient shadows on elevated surfaces
8. Smooth transitions on all interactive elements

### Phase 3: Advanced Effects
9. Waveform visualization during recording (optional)
10. Animated state transitions
11. Loading indicators with glow
12. Success/error notifications with color-coded glows

---

## 📸 Reference Images

**Generated concept art:**
- `talktype-ui-dark-mockup.png` - Dark UI with cyan/purple accents
- `talktype-neon-glow-concept.png` - Glowing UI elements and gradients
- `talktype-glassmorphic-concept.png` - Frosted glass effects

---

## ⚠️ Don'ts

❌ **Don't:**
- Make everything neon (subtle is key)
- Use bright backgrounds (stay dark)
- Add too many glowing elements (strategic placement only)
- Sacrifice readability for style
- Ignore GNOME HIG completely
- Make it look like a gaming app

✅ **Do:**
- Keep it professional
- Use glows sparingly for emphasis
- Maintain high contrast for accessibility
- Test with colorblind simulators
- Keep animations smooth and subtle
- Make it feel modern but not trendy

---

## 🎨 CSS Template

Here's a starter CSS file for TalkType's cyberpunk aesthetic:

```css
/* TalkType Cyberpunk Theme */

:root {
    /* Colors */
    --bg-dark: #1a1a1f;
    --bg-surface: #252530;
    --bg-elevated: #2d2d3a;

    --accent-cyan: #00d9ff;
    --accent-magenta: #ff006e;
    --accent-gold: #ffd60a;
    --accent-purple: #7c3aed;

    --text-primary: #e5e7eb;
    --text-secondary: #9ca3af;
    --text-disabled: #4b5563;

    --success: #10b981;
    --error: #ef4444;
    --warning: #f59e0b;

    /* Spacing */
    --spacing-xs: 4px;
    --spacing-sm: 8px;
    --spacing-md: 16px;
    --spacing-lg: 24px;
    --spacing-xl: 32px;

    /* Border Radius */
    --radius-sm: 4px;
    --radius-md: 6px;
    --radius-lg: 12px;

    /* Shadows */
    --shadow-sm: 0 1px 4px rgba(0, 0, 0, 0.2);
    --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.3);
    --shadow-lg: 0 20px 60px rgba(0, 0, 0, 0.5);

    /* Glows */
    --glow-cyan: 0 0 15px rgba(0, 217, 255, 0.3);
    --glow-gold: 0 0 30px rgba(255, 214, 10, 0.6);
}

/* Apply to GTK with CSS file: ~/.config/gtk-3.0/gtk.css */
/* Or inline in prefs_style.css */
```

---

## 🔄 Iteration

This is a living document. As TalkType evolves, update this guide with:
- New component patterns
- Refined color values
- User feedback
- Accessibility improvements

**Next review:** After implementing Phase 1 changes

---

**Created with AI assistance** 🤖
**Mockups generated:** Stable Diffusion WebUI
**For:** TalkType v0.4.0 and beyond
