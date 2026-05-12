from fastapi import APIRouter, status
import httpx
import json
import os
from typing import List
from ..schemas.generate_prompts import GeneratePromptRequest, GeneratePromptResponse, PromptItem

router = APIRouter(prefix="/api", tags=["generate-prompts"])


def build_prompt_item(idx: int, topic: str) -> PromptItem:
    return PromptItem(
        title=f"Prompt {idx+1} for {topic}",
        strategyTag=f"strategy-{idx+1}",
        description=f"Description of strategy {idx+1} for topic {topic}",
        prompt=f"Generate content about {topic} using strategy {idx+1}",
    )


@router.post("/generate-prompts", response_model=GeneratePromptResponse, status_code=status.HTTP_200_OK)
async def generate_prompts(request: GeneratePromptRequest) -> GeneratePromptResponse:
    api_key = os.getenv("CLAUDE_API_KEY")
    if api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    json={
                        "model": "claude-sonnet-4-6",
                        "max_tokens": 1024,
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    f"Generate eight distinct prompts for the topic: {request.topic}. "
                                    "Return ONLY a JSON array with exactly 8 objects, each having fields: "
                                    "title (string), strategyTag (string), description (string), prompt (string)."
                                ),
                            }
                        ],
                    },
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["content"][0]["text"]
                prompts_raw: List[dict] = json.loads(text)
                prompts: List[PromptItem] = []
                for item in prompts_raw:
                    try:
                        prompts.append(PromptItem(**item))
                    except Exception:
                        continue
                if len(prompts) < 8:
                    for i in range(len(prompts), 8):
                        prompts.append(build_prompt_item(i, request.topic))
                elif len(prompts) > 8:
                    prompts = prompts[:8]
                return GeneratePromptResponse(prompts=prompts)
        except Exception:
            pass
    prompts = [build_prompt_item(i, request.topic) for i in range(8)]
    return GeneratePromptResponse(prompts=prompts)
