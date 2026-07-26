from __future__ import annotations
import os
import pytest
import httpx
from backend.core.config import get_settings
from backend.services.ai import _extract_response_text

pytestmark=pytest.mark.skipif(os.getenv('RUN_LIVE_TESTS')!='1',reason='set RUN_LIVE_TESTS=1')

def test_ark_responses_live():
    settings=get_settings()
    assert settings.ark_api_key
    response=httpx.post(
        settings.ark_openai_base_url.rstrip('/')+'/responses',
        headers={'Authorization':f'Bearer {settings.ark_api_key}','Content-Type':'application/json'},
        json={
            'model':settings.ark_model,
            'input':[{'role':'user','content':[{'type':'input_text','text':'只回复：识境连接成功'}]}],
            'max_output_tokens':128,
        },
        timeout=httpx.Timeout(40,connect=10),trust_env=False,
    )
    assert response.status_code==200,response.text
    assert _extract_response_text(response.json())
