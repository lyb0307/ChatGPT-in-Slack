from typing import Optional
from typing import List, Dict
import time, json
from collections import OrderedDict

import requests
from httpcore._synchronization import ThreadLock

from slack_sdk.web import WebClient, SlackResponse
from slack_sdk.errors import SlackApiError
from slack_bolt import BoltContext

from app.env import FILE_ACCESS_ENABLED
from app.markdown_conversion import slack_to_markdown


__all__ = [
    "find_parent_message",
    "is_this_app_mentioned",
    "build_thread_replies_as_combined_text",
    "post_wip_message",
    "split_long_message",
    "update_wip_message",
    "extract_state_value",
    "can_send_image_url_to_openai",
    "can_access_slack_files",
    "download_slack_image_content",
    "download_slack_file_content",
]


# ----------------------------
# General operations in a channel
# ----------------------------


def find_parent_message(
    client: WebClient, channel_id: Optional[str], thread_ts: Optional[str]
) -> Optional[dict]:
    if channel_id is None or thread_ts is None:
        return None

    messages = client.conversations_history(
        channel=channel_id,
        latest=thread_ts,
        limit=1,
        inclusive=True,
    ).get("messages", [])

    return messages[0] if len(messages) > 0 else None


def is_this_app_mentioned(context: BoltContext, parent_message: dict) -> bool:
    parent_message_text = parent_message.get("text", "")
    return f"<@{context.bot_user_id}>" in parent_message_text


def build_thread_replies_as_combined_text(
    *,
    context: BoltContext,
    client: WebClient,
    channel: str,
    thread_ts: str,
) -> str:
    thread_content = ""
    for page in client.conversations_replies(
        channel=channel,
        ts=thread_ts,
        limit=1000,
    ):
        for reply in page.get("messages", []):
            user = reply.get("user")
            if user == context.bot_user_id:  # Skip replies by this app
                continue
            if user is None:
                bot_response = client.bots_info(bot=reply.get("bot_id"))
                user = bot_response.get("bot", {}).get("user_id")
                if user is None or user == context.bot_user_id:
                    continue
            text = slack_to_markdown("".join(reply["text"].splitlines()))
            thread_content += f"<@{user}>: {text}\n"
    return thread_content


# ----------------------------
# WIP reply message stuff
# ----------------------------

# Cache for tracking chunk messages during streaming
# Key: (channel, parent_ts), Value: dict with 'timestamps' list and 'last_updated' time
_chunk_messages_cache = OrderedDict()
_CACHE_MAX_SIZE = 100  # Maximum number of conversations to cache
_CACHE_TTL_SECONDS = 300  # 5 minutes TTL for cache entries


def _cleanup_cache():
    """Remove old cache entries to prevent unlimited memory growth."""
    current_time = time.time()

    # Remove entries older than TTL
    keys_to_remove = []
    for key, value in _chunk_messages_cache.items():
        if current_time - value.get("last_updated", 0) > _CACHE_TTL_SECONDS:
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del _chunk_messages_cache[key]

    # Enforce max size limit (LRU eviction)
    while len(_chunk_messages_cache) > _CACHE_MAX_SIZE:
        _chunk_messages_cache.popitem(last=False)  # Remove oldest entry


def post_wip_message(
    *,
    client: WebClient,
    channel: str,
    thread_ts: str,
    loading_text: str,
    messages: List[Dict[str, str]],
    user: str,
) -> SlackResponse:
    system_messages = [msg for msg in messages if msg["role"] == "system"]
    # Clear any cached chunk messages for this new message
    cache_key = (channel, thread_ts)
    if cache_key in _chunk_messages_cache:
        del _chunk_messages_cache[cache_key]

    # Run periodic cache cleanup
    _cleanup_cache()

    return client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=loading_text,
        metadata={
            "event_type": "chat-gpt-convo",
            "event_payload": {"messages": system_messages, "user": user},
        },
    )


def split_long_message(text: str, max_length: int = 4000) -> List[str]:
    """
    Split a long message into multiple parts without breaking words or code blocks.

    Args:
        text: The text to split
        max_length: Maximum byte length for each message chunk (default 4000 for Slack)

    Returns:
        List of message chunks
    """
    # Check byte length instead of character length
    if len(text.encode("utf-8")) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""

    # Check if we're in a code block
    in_code_block = False
    code_block_delimiter = "```"

    # Handle text with or without line breaks
    if "\n" in text:
        lines = text.split("\n")
    else:
        # For continuous text without line breaks, try to split by words first
        if " " in text:
            words = text.split(" ")
            lines = []
            current_line = ""
            for word in words:
                test_line = current_line + " " + word if current_line else word
                if len(test_line.encode("utf-8")) <= max_length:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
        else:
            # For continuous text without spaces, split by byte chunks
            lines = []
            text_bytes = text.encode("utf-8")
            start = 0
            while start < len(text_bytes):
                # Find a safe split point that doesn't break multi-byte characters
                end = min(start + max_length - 6, len(text_bytes))
                # Decode and handle potential partial characters at boundaries
                while end > start:
                    try:
                        chunk = text_bytes[start:end].decode("utf-8")
                        lines.append(chunk)
                        start = end
                        break
                    except UnicodeDecodeError:
                        end -= 1

    for i, line in enumerate(lines):
        # Track code block state
        if code_block_delimiter in line:
            in_code_block = not in_code_block

        # Check if adding this line would exceed the byte limit
        separator = "\n" if current_chunk and i > 0 else ""
        test_chunk = current_chunk + separator + line

        if len(test_chunk.encode("utf-8")) > max_length and current_chunk:
            # If we're in a code block, close it temporarily
            if in_code_block:
                current_chunk += "\n```"

            chunks.append(current_chunk)

            # Start new chunk
            current_chunk = ""

            # If we were in a code block, reopen it
            if in_code_block:
                current_chunk += "\n```\n" + line if current_chunk else "```\n" + line
            else:
                current_chunk += (
                    line if not current_chunk or current_chunk == "..." else "\n" + line
                )
        else:
            current_chunk = test_chunk

    # Add the last chunk if there's content
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def update_wip_message(
    client: WebClient,
    channel: str,
    ts: str,
    text: str,
    messages: List[Dict[str, str]],
    user: str,
) -> SlackResponse:
    system_messages = [msg for msg in messages if msg["role"] == "system"]
    # Ensure text is not empty - Slack API requires non-empty text
    if not text or not text.strip():
        text = ":hourglass_flowing_sand: Processing..."

    # Split long messages
    message_chunks = split_long_message(text)

    # Get the parent thread timestamp (in case this message is itself a reply)
    # We use ts as the thread_ts since messages are posted as replies to ts
    thread_ts = ts
    cache_key = (channel, thread_ts)

    # Get or initialize the chunk message cache for this thread
    if cache_key not in _chunk_messages_cache:
        _chunk_messages_cache[cache_key] = {
            "timestamps": [ts],
            "last_updated": time.time(),
            "thread_lock": ThreadLock(),
        }

    # Update access time (moves to end of OrderedDict)
    _chunk_messages_cache.move_to_end(cache_key)
    thread_lock = _chunk_messages_cache[cache_key]["thread_lock"]
    with thread_lock:
        _chunk_messages_cache[cache_key]["last_updated"] = time.time()

        chunk_timestamps = _chunk_messages_cache[cache_key]["timestamps"]

        last_chunk = message_chunks[-1]

        if len(chunk_timestamps) < len(message_chunks):
            response = client.chat_update(
                channel=channel,
                ts=chunk_timestamps[-1],
                text=message_chunks[-2],
                metadata={
                    "event_type": "chat-gpt-convo",
                    "event_payload": {"messages": system_messages, "user": user},
                },
            )
            response = client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=last_chunk,
            )
            chunk_timestamps.append(response["ts"])
        else:
            response = client.chat_update(
                channel=channel,
                ts=chunk_timestamps[-1],
                text=last_chunk,
                metadata={
                    "event_type": "chat-gpt-convo",
                    "event_payload": {"messages": system_messages, "user": user},
                },
            )

        # Clear cache for completed messages (no loading character)
        if not text.endswith(":hourglass_flowing_sand:") and not text.endswith(":wave:"):
            # Message is complete, we can remove it from cache after a short delay
            # Keep it briefly in case of final adjustments
            if cache_key in _chunk_messages_cache:
                _chunk_messages_cache[cache_key]["last_updated"] = (
                    time.time() - _CACHE_TTL_SECONDS + 30
                )  # Keep for 30 more seconds

    # Periodically clean up old cache entries
    if len(_chunk_messages_cache) > _CACHE_MAX_SIZE // 2:
        _cleanup_cache()

    return response


# ----------------------------
# Modals
# ----------------------------


def extract_state_value(payload: dict, block_id: str, action_id: str = "input") -> dict:
    state_values = payload["state"]["values"]
    return state_values[block_id][action_id]


# ----------------------------
# Files
# ----------------------------


def can_send_image_url_to_openai(context: BoltContext) -> bool:
    if FILE_ACCESS_ENABLED is False:
        return False
    bot_scopes = context.authorize_result.bot_scopes or []
    can_access_files = context and "files:read" in bot_scopes
    if can_access_files is False:
        return False

    openai_model = context.get("OPENAI_MODEL")
    # More supported models will come. This logic will need to be updated then.
    can_send_image_url = openai_model is not None and (
        openai_model.startswith("gpt-4o")
        or openai_model.startswith("gpt-4.1")
        or openai_model.startswith("gpt-5")
    )
    return can_send_image_url


def can_access_slack_files(context: BoltContext) -> bool:
    """
    Check if the bot has permission to access Slack files.
    This is a more generic check that doesn't depend on specific OpenAI models.
    """
    if FILE_ACCESS_ENABLED is False:
        return False
    bot_scopes = context.authorize_result.bot_scopes or []
    return "files:read" in bot_scopes


def download_slack_image_content(image_url: str, bot_token: str) -> bytes:
    response = requests.get(
        image_url,
        headers={"Authorization": f"Bearer {bot_token}"},
    )
    if response.status_code != 200:
        error = f"Request to {image_url} failed with status code {response.status_code}"
        raise SlackApiError(error, response)

    content_type = response.headers["content-type"]
    if content_type.startswith("text/html"):
        error = f"You don't have the permission to download this file: {image_url}"
        raise SlackApiError(error, response)

    if not content_type.startswith("image/"):
        error = f"The responded content-type is not for image data: {content_type}"
        raise SlackApiError(error, response)

    return response.content


def download_slack_file_content(file_url: str, bot_token: str) -> bytes:
    """
    Download any file from Slack (not just images).

    Args:
        file_url: The Slack file URL (usually url_private)
        bot_token: The bot token for authentication

    Returns:
        The file content as bytes
    """
    response = requests.get(
        file_url,
        headers={"Authorization": f"Bearer {bot_token}"},
    )
    if response.status_code != 200:
        error = f"Request to {file_url} failed with status code {response.status_code}"
        raise SlackApiError(error, response)

    content_type = response.headers.get("content-type", "")
    if content_type.startswith("text/html"):
        error = f"You don't have the permission to download this file: {file_url}"
        raise SlackApiError(error, response)

    return response.content
