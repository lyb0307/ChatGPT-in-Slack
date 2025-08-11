# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the Application
```bash
# Local development
python main.py

# Production
python main_prod.py
```

### Code Quality and Testing
```bash
# Run all validation checks (formatter, tests, linters)
./validate.sh

# Individual commands from validate.sh:
black ./*.py ./app/*.py ./tests/*.py          # Format code
pytest .                                      # Run tests
flake8 ./*.py ./app/*.py ./tests/*.py        # Lint code
pytype ./*.py ./app/*.py ./tests/*.py        # Type check
```

## Architecture Overview

This is a Slack bot that integrates ChatGPT, allowing users to interact with OpenAI models directly in Slack. The app supports multiple interfaces:

1. **Channel threads** - Mention the bot to start conversations
2. **Direct messages** - Private 1:1 conversations with context maintained per thread
3. **Home tab** - Quick access to proofreading and prompt sending features

### Key Components

- **main.py** - Entry point for local development using Socket Mode
- **main_prod.py** - Production entry point with AWS Lambda support  
- **app/bolt_listeners.py** - Core event handlers for Slack interactions
- **app/openai_ops.py** - OpenAI API integration and streaming response handling
- **app/slack_ops.py** - Slack-specific operations and utilities
- **app/file_handlers.py** - Multi-format file processing (images, PDFs, documents, code)
- **app/slack_ui.py** - Slack UI components (modals, blocks, home tab)
- **app/markdown_conversion.py** - Conversion between OpenAI markdown and Slack mrkdwn

### Environment Variables

Required:
- `SLACK_APP_TOKEN` - App-level token with connections:write scope
- `SLACK_BOT_TOKEN` - Bot user OAuth token  
- `OPENAI_API_KEY` - OpenAI API key

Key optional variables:
- `OPENAI_MODEL` - Model to use (default: gpt-3.5-turbo)
- `FILE_ACCESS_ENABLED` - Enable file upload processing
- `TRANSLATE_MARKDOWN` - Convert between OpenAI/Slack formats
- `REDACTION_ENABLED` - Basic prompt redaction
- `USE_SLACK_LANGUAGE` - Translate prompts to user's language

### Testing Approach

- Unit tests in `tests/` directory
- Test individual modules: `pytest tests/openai_ops_test.py`
- All tests must pass before committing changes