# 📞 HangOn

**HangOn** is an Android application designed to protect middle-aged adults (29–60 years old) from increasingly sophisticated phone scams. Instead of detecting scams after the damage is done, HangOn provides **real-time guidance during phone calls** through intelligent pop-up warnings and AI-powered conversation analysis.

The application listens to call audio (with explicit user consent), streams it to the backend for analysis, and immediately alerts users when suspicious scam patterns are detected. For AI voice cloning attacks, HangOn introduces a **Family Codeword** verification mechanism to help users confirm the caller's identity.

> Built for **Garuda Hacks 7.0**.

---

## 🚀 Overview

Phone scams have evolved with AI, making impersonation attacks more convincing than ever. HangOn helps users stay protected by acting as a real-time companion during unknown phone calls.

The Android app captures call audio (only when enabled by the user), streams it securely to a FastAPI backend, where speech is transcribed and analyzed for scam indicators. If suspicious content is detected, HangOn immediately displays a non-intrusive popup warning, allowing users to make safer decisions before it's too late. The project focuses on protecting users through **real-time intervention**, rather than post-incident recovery. :contentReference[oaicite:0]{index=0}

---

## ✨ Main Features

- 📞 **Real-Time Scam Detection**
  - Monitors ongoing phone conversations and detects suspicious scam patterns in real time.

- ⚠️ **Smart Popup Guidance**
  - Displays contextual warning popups during phone calls without interrupting the conversation.

- 👨‍👩‍👧 **Family Codeword Verification**
  - Create a trusted family group with rotating secret codewords to verify callers against AI voice cloning attacks.

- 🔒 **Privacy-First Design**
  - Audio monitoring only starts with explicit user consent.
  - Users have full control over when protection is enabled.

- 📋 **Call Protection Toggle**
  - Easily enable or disable HangOn's call protection whenever needed.

---

## 🏗️ Tech Stack

### 📱 Android Application

- **Language:** Kotlin
- **UI:** Jetpack Compose
- **Authentication:** Firebase Authentication
- **Cloud Services:** Firebase
- **Networking:** Retrofit + OkHttp (WebSocket)
- **Call Integration:** Android Call Screening API
- **Overlay:** WindowManager / SYSTEM_ALERT_WINDOW

### ⚙️ Backend

- **Framework:** FastAPI
- **Language:** Python
- **Communication:** WebSocket (Audio Streaming)
- **AI Analysis:** Google Gemini API

### 🗄️ Database

- **Neon PostgreSQL**

---

## 🔄 System Architecture

```text
Android App (Kotlin)
        │
        │  Audio Stream (WebSocket)
        ▼
 FastAPI Backend (Python)
        │
        ├── Speech Processing
        ├── Scam Detection (Gemini)
        └── Family Codeword Verification
        │
        ▼
 Popup Warning & Guidance
        │
        ▼
 Neon PostgreSQL
```

---

## 👥 Contributors

- **Carlo Angkisan**
- **Nayla Zahira**
- **Varel Tiara**
- **Ranashahira Reztaputri**
