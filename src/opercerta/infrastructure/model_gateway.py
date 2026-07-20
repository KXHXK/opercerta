import json
from typing import cast

import httpx
from pydantic import SecretStr, ValidationError

from opercerta.domain.model_gateway import ScenarioAssessment
from opercerta.domain.replenishment import ModelPlanExplanation


class ModelOutputInvalid(ValueError):
    code = "model_output_invalid"

    def __init__(self) -> None:
        super().__init__(self.code)


class OpenAICompatibleModelGateway:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        model: str,
        api_key: SecretStr,
        timeout_seconds: float = 10.0,
        max_attempts: int = 2,
        disable_thinking: bool = False,
    ) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model = model
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_attempts = max(1, min(max_attempts, 2))
        self._disable_thinking = disable_thinking

    async def explain_plan(self, assessment: ScenarioAssessment) -> ModelPlanExplanation:
        for attempt in range(self._max_attempts):
            try:
                request_payload: dict[str, object] = {
                    "model": self._model,
                    "max_tokens": 256,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Return JSON with exactly summary and rationale. "
                                "Do not decide actions, quantities, priority or permissions."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                assessment.model_dump(mode="json"),
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        },
                    ],
                }
                if self._disable_thinking:
                    request_payload["thinking"] = {"type": "disabled"}
                response = await self._client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
                    json=request_payload,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                payload = cast(dict[str, object], response.json())
                choices = cast(list[dict[str, object]], payload["choices"])
                message = cast(dict[str, object], choices[0]["message"])
                content = message["content"]
                if not isinstance(content, str):
                    raise ModelOutputInvalid
                return ModelPlanExplanation.model_validate_json(content)
            except httpx.HTTPError:
                if attempt + 1 == self._max_attempts:
                    raise
            except (KeyError, IndexError, TypeError, ValueError, ValidationError):
                if attempt + 1 == self._max_attempts:
                    raise ModelOutputInvalid from None
        raise ModelOutputInvalid
