

# 🎬 Melanin Video Generator

A high-performance AI video generation system built on **Lightricks LTX-2**, deployed using **Modal**, capable of generating cinematic **text-to-video (T2V)** and **image-to-video (I2V)** outputs with audio synchronization and scalable GPU inference.


## 🚀 Overview

**Melanin Video Generator** is a serverless AI video generation backend designed for:

* Cinematic content creation
* AI-driven storytelling
* Automated video production pipelines
* Scalable cloud inference on GPUs

It leverages chunk-based generation to produce **high-quality, temporally consistent videos up to 60 seconds long**.


## ✨ Key Features

* 🎥 Text-to-Video generation (T2V)
* 🖼️ Image-to-Video generation (I2V)
* 🔊 Auto audio-synced MP4 output
* ⚡ Chunked long-video generation (stable memory usage)
* 🧠 Dual pipeline system:

  * Distilled fast inference
  * Diffusers fallback pipeline
* ☁️ Fully serverless GPU deployment (Modal A100)
* 📦 Persistent model + result caching (Modal Volumes)
* 📊 Real-time job tracking system
* 🔁 Fault-tolerant generation pipeline

---

## 🏗️ System Architecture

The system is built around:

* **FastAPI endpoints (Modal functions)**
* **GPU inference engine (`LTX23Inference`)**
* **Chunk-based video generation pipeline**
* **FFmpeg audio processing layer**
* **Persistent storage via Modal Volumes**

---

## 📡 API Endpoints

### 1. Submit Text-to-Video

```http
POST /ltx23-submit
```

**Request:**

```json
{
  "prompt": "A cinematic African sunset over a futuristic city, ultra realistic, film style",
  "duration_seconds": 5,
  "width": 768,
  "height": 512,
  "seed": 42
}
```

**Response:**

```json
{
  "job_id": "abc123",
  "status": "queued",
  "estimated_minutes": 3
}
```

---

### 2. Submit Image-to-Video

```http
POST /ltx23-submit-image
```

**Form Data:**

* `prompt` → text description
* `image` → input image file

---

### 3. Check Job Status

```http
GET /ltx23-status?job_id=YOUR_JOB_ID
```

**Response:**

```json
{
  "job_id": "abc123",
  "status": "running",
  "stage": "chunk_2",
  "chunk": 2,
  "total": 5
}
```



### 4. Download Final Video

```http
GET /ltx23-result?job_id=YOUR_JOB_ID
```

Returns:

* `video/mp4`


## ⚙️ How It Works

### 1. Input Processing

User submits prompt or image → job ID is created

### 2. Chunk Planning

Video duration is split into overlapping segments for stability

### 3. GPU Generation

Each chunk is generated using:

* Distilled LTX-2 pipeline (fast path)
* OR Diffusers fallback (safe path)

### 4. Temporal Consistency

Each chunk uses the last frame of the previous chunk to ensure continuity

### 5. Audio Enhancement

FFmpeg applies:

* loudness normalization
* EQ balancing
* dynamic compression

### 6. Stitching

All chunks are merged into a final MP4 video

---

## ☁️ Deployment

### Deploy to Modal

```bash
modal deploy backend.py
```

---

## 🧪 Local Test

```bash
modal run backend.py
```

---

## 🧰 Tech Stack

* Python 3.12
* PyTorch
* Lightricks LTX-2
* HuggingFace Diffusers
* FastAPI
* Modal Cloud
* FFmpeg
* xFormers

---

## ⚡ Performance Notes

* Uses **A100 GPU (80GB recommended)**
* Chunk-based generation prevents memory overload
* Warm containers reduce cold start latency
* Persistent caching improves repeat performance

---

## ⚠️ Known Limitations

* First run requires model download (slow initialization)
* High GPU cost for long videos
* Diffusers fallback depends on library compatibility
* Audio enhancement may fallback in rare cases

---

## 🔮 Future Improvements

* Real-time streaming video output
* WebSocket progress updates
* Parallel chunk generation
* Prompt caching system
* Multi-GPU distributed rendering
* UI dashboard for job monitoring

---

## 🧠 Project Vision

**Melanin Video Generator** is designed to evolve into a full AI media engine powering:

* African creative AI infrastructure
* Automated content generation platforms
* Next-generation storytelling tools
* Scalable AI video APIs

---

## 📜 License

Private / Research Use (update as needed)

---
# Melanin-Video-Gen
