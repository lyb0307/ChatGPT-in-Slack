import logging
from typing import List, Optional
import PyPDF2
from io import BytesIO

from app.slack_ops import download_slack_file_content
from slack_bolt import BoltContext


def append_pdf_content_if_exists(
    *,
    bot_token: str,
    files: List[dict],
    content: List[dict],
    logger: logging.Logger,
) -> None:
    """
    Process PDF files and append their text content to the message content.
    
    Args:
        bot_token: Slack bot token for downloading files
        files: List of Slack file metadata
        content: List to append processed content to
        logger: Logger instance
    """
    if files is None or len(files) == 0:
        return

    logger.debug(f"Processing {len(files)} files for PDF content")
    
    for file in files:
        mime_type = file.get("mimetype")
        filename = file.get("name", "")
        
        logger.debug(f"Checking file: {filename}, mime_type: {mime_type}")
        
        # Check if it's a PDF file
        if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
            file_url = file.get("url_private")
            
            try:
                # Download PDF file using generic file download function
                pdf_bytes = download_slack_file_content(file_url, bot_token)
                
                # Extract text from PDF
                text_content = extract_text_from_pdf(pdf_bytes, filename, logger)
                
                if text_content:
                    # Add as text content to the message
                    text_item = {
                        "type": "text",
                        "text": text_content
                    }
                    content.append(text_item)
                    logger.info(f"Successfully processed PDF: {filename}")
                else:
                    logger.warning(f"No text content extracted from PDF: {filename}")
                    
            except Exception as e:
                logger.error(f"Failed to process PDF file {filename}: {e}")
                continue


def extract_text_from_pdf(pdf_bytes: bytes, filename: str, logger: logging.Logger) -> Optional[str]:
    """
    Extract text content from a PDF file.
    
    Args:
        pdf_bytes: Raw PDF file bytes
        filename: Name of the PDF file
        logger: Logger instance
        
    Returns:
        Extracted text content or None if extraction fails
    """
    try:
        # Create PDF reader from bytes
        pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
        text_parts = []
        
        # Extract text from each page
        num_pages = len(pdf_reader.pages)
        for page_num, page in enumerate(pdf_reader.pages):
            try:
                page_text = page.extract_text().strip()
                if page_text:
                    # Add page header for clarity
                    text_parts.append(f"[Page {page_num + 1} of {num_pages}]")
                    text_parts.append(page_text)
                    text_parts.append("")  # Empty line between pages
            except Exception as e:
                logger.warning(f"Failed to extract text from page {page_num + 1} of {filename}: {e}")
                continue
        
        if not text_parts:
            return None
        
        # Format the complete text with document markers
        full_text = "\n".join(text_parts)
        
        # Limit text length to prevent token overflow (approximately 12.5k tokens)
        max_chars = 50000
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + f"\n\n[Content truncated - showing first {max_chars} characters of {len(full_text)} total]"
        
        # Wrap with document markers for context
        return f"[PDF Document: {filename}]\n\n{full_text}\n[End of PDF Document: {filename}]"
        
    except Exception as e:
        logger.error(f"Failed to read PDF {filename}: {e}")
        return None


def can_process_pdf_files(context: BoltContext) -> bool:
    """
    Check if PDF file processing is enabled.
    
    This uses the generic file access check since PDFs are sent as text content,
    not images, so they don't require specific OpenAI model support.
    """
    from app.slack_ops import can_access_slack_files
    
    has_permission = can_access_slack_files(context)
    context.logger.debug(f"PDF processing permission check: {has_permission}")
    return has_permission