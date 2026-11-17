# @AI_GENERATED
"""
load_api operator backend — Fetches data from a REST API endpoint.

Supports GET and POST methods with configurable headers and params/body.
Parses JSON response into a DataFrame.
"""
import json

import pandas as pd
import requests
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "load_api"


def execute(params: dict, inputs: dict) -> dict:
    """
    Send an HTTP request and parse the response into a DataFrame.

    Args:
        params: Operator parameters including:
            - url (str, required): API endpoint URL
            - method (str, optional): HTTP method, "GET" or "POST", default "GET"
            - headers (dict, optional): HTTP headers
            - params (dict, optional): Query parameters (for GET) or body (for POST)
        inputs: Not used for data source operators.

    Returns:
        {"data": DataFrame}
    """
    url = params.get("url")
    if not url:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "url parameter is required"
        )

    method = params.get("method", "GET").upper()
    headers = params.get("headers") or {}
    request_params = params.get("params") or {}

    if isinstance(headers, str):
        try:
            headers = json.loads(headers)
        except json.JSONDecodeError:
            headers = {}

    if isinstance(request_params, str):
        try:
            request_params = json.loads(request_params)
        except json.JSONDecodeError:
            request_params = {}

    try:
        if method == "POST":
            response = requests.post(url, headers=headers, json=request_params, timeout=30)
        else:
            response = requests.get(url, headers=headers, params=request_params, timeout=30)
    except requests.RequestException as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "RequestError", f"HTTP request failed: {e}"
        )

    if not response.ok:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "HTTPError",
            f"HTTP {response.status_code}: {response.text[:200]}",
        )

    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError) as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParseError", f"Failed to parse JSON response: {e}"
        )

    try:
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            # Try common response wrapper patterns
            for key in ("data", "results", "items", "records", "rows"):
                if key in data and isinstance(data[key], list):
                    df = pd.DataFrame(data[key])
                    break
            else:
                df = pd.DataFrame([data])
        else:
            raise OperatorExecutionError(
                OPERATOR_ID,
                "ParseError",
                f"Unexpected response type: {type(data).__name__}",
            )
    except OperatorExecutionError:
        raise
    except Exception as e:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParseError", f"Failed to convert response to DataFrame: {e}"
        )

    logger.info(
        f"[load_api] Fetched {len(df)} rows, {len(df.columns)} columns from {url}"
    )
    return {"data": df}
# @AI_GENERATED: end
