# filename: server.py
# -*- coding: utf-8 -*-
import base64
import time
import secrets
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from captcha_generator import generate_time_captcha

"""
FastAPI service for time-encoded CAPTCHA
- POST /captcha/new: create a new CAPTCHA, returns id + video (Base64) + hint
- POST /captcha/verify: submit id + answer, returns success
- In-memory store with TTL; production should use Redis and CDN for video delivery

Security best practices:
- Use HTTPS
- Rate limit by IP
- One-time tokens
- Short TTL
- Server-side validation
"""

app = FastAPI()

# Serve the demo HTML at root
@app.get("/")
async def serve_demo():
    return FileResponse("static_demo.html")

CAPTCHA_STORE: Dict[str, Dict] = {}
TTL_SECONDS = 180  # 3 minutes

class NewCaptchaRequest(BaseModel):
    mode: str = "text"          # "text" | "shape" | "depth" | "random"
    difficulty: str = "medium"  # "easy" | "medium" | "hard"
    threshold_low: Optional[float] = 0.2  # tl for depth mode
    threshold_high: Optional[float] = 0.8  # tu for depth mode
    depth_image: Optional[str] = None  # base64 encoded depth image

class NewCaptchaResponse(BaseModel):
    id: str
    video_base64: str
    hint: str  # e.g., "请识别视频中的单词" / "请识别形状"
    expires_at: int

class VerifyRequest(BaseModel):
    id: str
    answer: str

class VerifyResponse(BaseModel):
    success: bool
    message: str

@app.post("/captcha/new", response_model=NewCaptchaResponse)
def new_captcha(req: NewCaptchaRequest):
    # Handle random mode selection
    import random
    if req.mode == "random":
        mode = random.choice(["text", "shape", "depth"])
    else:
        mode = req.mode

    # Generate CAPTCHA with enhanced parameters
    try:
        if mode == "depth" and req.depth_image:
            # For depth mode with custom depth image
            from io import BytesIO
            from PIL import Image
            import numpy as np

            # Decode base64 depth image
            image_data = base64.b64decode(req.depth_image.split(',')[1])
            depth_img = Image.open(BytesIO(image_data)).convert('L')
            depth_array = np.array(depth_img)

            # Convert threshold values (0-1) to pixel values (0-255)
            tl = int((req.threshold_low or 0.2) * 255)
            tu = int((req.threshold_high or 0.8) * 255)

            mp4_bytes, answer = generate_time_captcha(
                mode=mode,
                depth_image=depth_array,
                thresholds=(tl, tu)
            )
        else:
            # Standard generation for text/shape modes
            mp4_bytes, answer = generate_time_captcha(mode=mode)
    except Exception as e:
        # Fallback to text mode if generation fails
        print(f"Failed to generate {mode} captcha: {e}")
        mode = "text"
        mp4_bytes, answer = generate_time_captcha(mode=mode)

    # Base64-encode video for simple delivery; consider CDN in prod
    b64 = base64.b64encode(mp4_bytes).decode("ascii")
    hint = {
        "text": "请识别视频中的单词（播放过程中才能看清）",
        "shape": "请识别视频中的形状（播放过程中才能看清）",
        "depth": "请识别视频中的对象（播放过程中才能看清）",
    }.get(mode, "请识别视频中的内容")

    # Store with TTL
    cid = secrets.token_urlsafe(18)
    now = int(time.time())
    CAPTCHA_STORE[cid] = {
        "answer": answer.lower(),
        "created_at": now,
        "expires_at": now + TTL_SECONDS,
        "attempts": 0,
        "mode": mode,
        "difficulty": req.difficulty,
        "hint": hint,
    }

    return NewCaptchaResponse(
        id=cid,
        video_base64=b64,
        hint=hint,
        expires_at=now + TTL_SECONDS,
    )

@app.post("/captcha/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest):
    rec = CAPTCHA_STORE.get(req.id)
    if not rec:
        return VerifyResponse(success=False, message="验证码不存在或已过期")

    now = int(time.time())
    if now > rec["expires_at"]:
        CAPTCHA_STORE.pop(req.id, None)
        return VerifyResponse(success=False, message="验证码已过期")

    rec["attempts"] += 1
    if rec["attempts"] > 5:
        CAPTCHA_STORE.pop(req.id, None)
        return VerifyResponse(success=False, message="尝试次数过多，已失效")

    user_ans = req.answer.strip().lower()

    # Fuzzy matching for shapes/common variants
    mode = rec["mode"]
    truth = rec["answer"]
    ok = False
    if mode == "text":
        ok = (user_ans == truth)
    elif mode == "shape":
        synonyms = {
            "rectangle": {"rect", "矩形"},
            "circle": {"圆", "圆形"},
            "triangle": {"三角形"},
            "heart": {"心形", "爱心"},
            "arrow": {"箭头"},
        }
        if user_ans == truth:
            ok = True
        else:
            ok = user_ans in synonyms.get(truth, set())
    elif mode == "depth":
        # Depth mode often maps to a category; customize per your data source
        ok = (user_ans == truth) or (user_ans in {"object", "物体"})
    else:
        ok = (user_ans == truth)

    if ok:
        CAPTCHA_STORE.pop(req.id, None)
        return VerifyResponse(success=True, message="验证成功")
    else:
        return VerifyResponse(success=False, message="答案不正确")

@app.get("/captcha/hint/{captcha_id}")
def get_hint(captcha_id: str):
    rec = CAPTCHA_STORE.get(captcha_id)
    if not rec:
        raise HTTPException(status_code=404, detail="验证码不存在或已过期")

    now = int(time.time())
    if now > rec["expires_at"]:
        CAPTCHA_STORE.pop(captcha_id, None)
        raise HTTPException(status_code=404, detail="验证码已过期")

    # Return hint with penalty (increase attempts)
    rec["attempts"] += 1
    if rec["attempts"] > 5:
        CAPTCHA_STORE.pop(captcha_id, None)
        raise HTTPException(status_code=410, detail="尝试次数过多，已失效")

    return {"hint": rec["hint"], "attempts": rec["attempts"]}
