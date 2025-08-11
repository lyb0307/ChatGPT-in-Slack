# Using the New OpenAI Responses API

This codebase now supports both the traditional `client.chat.completions.create` API and the new `client.responses.create` API.

## Default Behavior

By default, the application uses the traditional `client.chat.completions.create` API which is stable and well-tested with all current OpenAI models.

## Enabling the New API

To test the new `client.responses.create` API, set the following environment variable:

```bash
export USE_NEW_OPENAI_API=true
```

Or add it to your `.env` file:

```
USE_NEW_OPENAI_API=true
```

## Important Notes

1. **The new API is experimental** - It may not work with all models or in all scenarios yet
2. **Automatic fallback** - If the new API is not available in your OpenAI client version, it will automatically fall back to the traditional API
3. **Compatibility** - The code maintains full backward compatibility, so existing deployments will continue to work without any changes

## Troubleshooting

If you encounter issues with the new API:

1. Ensure your OpenAI Python package is up to date:
   ```bash
   pip install --upgrade openai
   ```

2. Check if the new API is available:
   ```python
   from openai import OpenAI
   client = OpenAI()
   print(hasattr(client, 'responses'))  # Should print True
   ```

3. Disable the new API by removing or setting to false:
   ```bash
   export USE_NEW_OPENAI_API=false
   ```

## API Differences

### Old API (chat.completions.create)
- Uses `messages` parameter with role/content structure
- Returns `choices[0].delta.content` for streaming
- Well-tested with GPT-3.5, GPT-4, and GPT-5 models

### New API (responses.create)  
- Uses `input` and `instructions` parameters
- Different streaming event format (`response.text.delta`, `response.done`)
- May have different model compatibility

## Development

When the new API becomes generally available and stable, we can change the default behavior by modifying the `check_api_availability()` function in `app/openai_ops.py`.