from fastapi import FastAPI, Request
from pydantic import BaseModel
import hashlib
import redis
import openai
import time
import os
import logging
from typing import Optional

openai.api_key = os.getenv("OPENAI_API_KEY")
redis_client = redis.Redis(host='localhost', port=6379, db=0)
logger = logging.getLogger("uvicorn")

class PromptRequest(BaseModel):
    prompt: str
    model: Optional[str] = "auto"
    max_tokens: Optional[int] = 512

app = FastAPI()

def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()

def get_cached_response(prompt: str):
    prompt_hash = hash_prompt(prompt)
    cached = redis_client.get(prompt_hash)
    if cached:
        logger.info("Cache hit")
        return cached.decode()
    return None

def cache_response(prompt: str, response: str):
    prompt_hash = hash_prompt(prompt)
    redis_client.set(prompt_hash, response, ex=3600)

def optimize_prompt(prompt: str) -> str:
    return prompt[:1000]

def select_model(prompt: str) -> str:
    if len(prompt) < 100:
        return "gpt-3.5-turbo"
    return "gpt-4"

def log_usage(prompt: str, model: str, tokens: int):
    logger.info(f"Used {model} for {tokens} tokens")

@app.post("/generate")
async def generate_text(req: PromptRequest):
    start = time.time()
    prompt = optimize_prompt(req.prompt)

    if cached := get_cached_response(prompt):
        return {"source": "cache", "response": cached}

    model = req.model if req.model != "auto" else select_model(prompt)

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=req.max_tokens,
        )
        output = response["choices"][0]["message"]["content"]
        token_usage = response["usage"]["total_tokens"]
        cache_response(prompt, output)
        log_usage(prompt, model, token_usage)
        return {
            "source": "llm",
            "model": model,
            "tokens": token_usage,
            "response": output,
            "time_taken": round(time.time() - start, 2)
        }
    except Exception as e:
        logger.error(str(e))
        return {"error": str(e)}
