"""
Nova 2 API wrapper using Amazon Bedrock Converse API.
Runs boto3 calls in a thread pool to play nicely with async FastAPI.
"""

import asyncio
import json
import re
import boto3
from typing import Any

# Model IDs — update if Nova 2 Pro becomes generally available
NOVA_LITE_MODEL_ID = "us.amazon.nova-2-lite-v1:0"
NOVA_PRO_MODEL_ID = "us.amazon.nova-pro-v1:0"   # Nova 1 Pro until Nova 2 Pro is GA


def _extract_json(text: str) -> Any:
    """
    Robustly extract JSON from a Nova response.
    Tries: raw parse → fenced code block → first {...} or [...] in text.
    """
    text = text.strip()

    # 1. Try raw parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Try ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Find first complete JSON object or array
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(text[start:], start):
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not extract JSON from response: {text[:200]}")


class NovaClient:
    def __init__(self, region: str = "us-east-1"):
        self._region = region
        # boto3 client is thread-safe for concurrent reads
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def _converse_sync(self, model_id: str, system_prompt: str, user_message: str,
                       max_tokens: int, temperature: float) -> str:
        """Synchronous Bedrock Converse call (run inside thread pool)."""
        response = self._client.converse(
            modelId=model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        )
        return response["output"]["message"]["content"][0]["text"]

    async def invoke(
        self,
        model_id: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        temperature: float = 0.8,
    ) -> str:
        """Async wrapper — runs the boto3 call in a thread pool."""
        return await asyncio.to_thread(
            self._converse_sync,
            model_id,
            system_prompt,
            user_message,
            max_tokens,
            temperature,
        )

    async def invoke_json(
        self,
        model_id: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        temperature: float = 0.8,
    ) -> Any:
        """Like invoke() but parses the response as JSON."""
        text = await self.invoke(model_id, system_prompt, user_message, max_tokens, temperature)
        return _extract_json(text)

    # ── Nova Canvas image generation ──────────────────────────────────────────

    def _generate_image_sync(self, prompt: str, negative_prompt: str,
                              width: int, height: int, seed: int) -> str:
        """Synchronous Nova Canvas InvokeModel call. Returns base64 PNG string."""
        body = json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": prompt[:1000],
                "negativeText": negative_prompt,
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": height,
                "width": width,
                "cfgScale": 8.0,
                "seed": seed,
            },
        })
        response = self._client.invoke_model(
            modelId="amazon.nova-canvas-v1:0",
            body=body,
            accept="application/json",
            contentType="application/json",
        )
        result = json.loads(response["body"].read())
        if result.get("error"):
            raise RuntimeError(f"Nova Canvas error: {result['error']}")
        return result["images"][0]   # base64 PNG

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "text, letters, words, watermark, ugly, blurry, dark, scary",
        width: int = 512,
        height: int = 512,
        seed: int = 0,
    ) -> str:
        """Async Nova Canvas image generation. Returns base64-encoded PNG string."""
        return await asyncio.to_thread(
            self._generate_image_sync,
            prompt, negative_prompt, width, height, seed,
        )

    def lite(self) -> str:
        return NOVA_LITE_MODEL_ID

    def pro(self) -> str:
        return NOVA_PRO_MODEL_ID
