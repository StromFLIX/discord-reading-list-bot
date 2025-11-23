from pydantic import BaseModel, Field, ConfigDict
from typing import List
from openai import AsyncOpenAI
import json

class ContentSummary(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    title: str = Field(..., description="The title of the content")
    summary: str = Field(..., description="A short and concise summary, not longer than 2 paragraphs")
    caveats: List[str] = Field(..., description="A list of caveats if applicable, such as things that stand out as wrong, misleading, or unfactual. Return an empty list if none.")
    topics: List[str] = Field(..., description="List of general topics (e.g. politics, software_engineering). Use snake_case.")
    issues: List[str] = Field(..., description="List of specific issues discussed (e.g. covid_19). Use snake_case. Return empty list if none.")
    sentiment: str = Field(..., description="Overall sentiment of the content (e.g. positive, negative, neutral).")
    people: List[str] = Field(..., description="List of key people mentioned (e.g. trump, atrioc). Use snake_case. Return empty list if none.")

class Summarizer:
    def __init__(self, api_key: str, model: str = "openai/gpt-4o-mini"):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model = model

    async def summarize(self, text: str) -> ContentSummary:
        """
        Summarizes the given text into a structured format using OpenRouter.
        """
        if not text:
            return ContentSummary(title="Error", summary="No text provided to summarize.", caveats=[], topics=[], issues=[], sentiment="neutral", people=[])

        # Truncate text if it's too long to avoid context limits (simple truncation)
        # A rough estimate: 1 token ~= 4 chars. 100k tokens is plenty, but let's be safe.
        max_chars = 100000 
        if len(text) > max_chars:
            text = text[:max_chars] + "...(truncated)"

        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a helpful assistant that summarizes text. You must output JSON."
                    },
                    {
                        "role": "user", 
                        "content": f"Analyze the following text and provide a structured summary:\n\n{text}"
                    }
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "content_summary",
                        "strict": True,
                        "schema": ContentSummary.model_json_schema()
                    }
                }
            )
            
            content = completion.choices[0].message.content
            return ContentSummary.model_validate_json(content)
            1
        except Exception as e:
            return ContentSummary(
                title="Error generating summary",
                summary=f"An error occurred while communicating with the AI: {str(e)}",
                caveats=[],
                topics=[],
                issues=[],
                sentiment="neutral",
                people=[]
            )
