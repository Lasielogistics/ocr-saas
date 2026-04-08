"""Email consumer for IMAP-based document ingestion."""
import email
import imaplib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from api.celery_app import celery_app
from shared.supabase import SupabaseClientFactory

logger = logging.getLogger(__name__)


class EmailConsumer:
    """Consumes emails from IMAP mailbox and creates OCR jobs."""

    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        self.config = SupabaseClientFactory.get_config(customer_id)
        self.imap_config = self.config.email_imap

        if not self.imap_config:
            raise ValueError(f"Customer {customer_id} has no email IMAP configuration")

    def connect(self) -> imaplib.IMAP4_SSL:
        """Connect to IMAP server."""
        mail = imaplib.IMAP4_SSL(
            host=self.imap_config["host"],
            port=self.imap_config.get("port", 993),
        )
        mail.login(
            self.imap_config["user"],
            self.imap_config["password"],
        )
        return mail

    def fetch_new_emails(self) -> list[tuple[str, str, list[bytes]]]:
        """
        Fetch new emails with attachments.

        Returns:
            List of (subject, sender, [(filename, content)]) tuples
        """
        emails_with_attachments = []
        mail = self.connect()

        try:
            mail.select(self.imap_config.get("folder", "INBOX"))

            # Search for unread emails
            status, message_ids = mail.search(None, "UNSEEN")

            if status != "OK":
                logger.warning(f"Failed to search emails: {status}")
                return []

            for msg_id in message_ids[0].split():
                try:
                    status, msg_data = mail.fetch(msg_id, "(RFC822)")

                    if status != "OK":
                        continue

                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    subject = msg.get("Subject", "(no subject)")
                    sender = msg.get("From", "")

                    attachments = []
                    for part in msg.walk():
                        content_disposition = part.get("Content-Disposition", "")
                        if "attachment" in content_disposition:
                            filename = part.get_filename()
                            if filename:
                                content = part.get_payload(decode=True)
                                if content:
                                    attachments.append((filename, content))

                    if attachments:
                        emails_with_attachments.append((subject, sender, attachments))

                    # Mark as seen (in production, you might want to move to processed folder)
                    # mail.store(msg_id, "+FLAGS", "\\Seen")

                except Exception as e:
                    logger.error(f"Error processing email {msg_id}: {e}")
                    continue

        finally:
            mail.logout()

        return emails_with_attachments

    def process_emails(self) -> int:
        """
        Process all new emails and create OCR jobs.

        Returns:
            Number of documents queued
        """
        from shared.storage import get_storage

        emails = self.fetch_new_emails()
        storage = get_storage()
        queued_count = 0

        for subject, sender, attachments in emails:
            for filename, content in attachments:
                try:
                    if not storage.is_supported_file(filename):
                        logger.info(f"Skipping unsupported attachment: {filename}")
                        continue

                    # Save to pending
                    job_id, file_path = storage.save_upload(
                        content,
                        filename,
                        self.customer_id,
                    )

                    # Queue OCR task
                    celery_app.send_task(
                        "worker.tasks.process_document",
                        args=[job_id, self.customer_id, file_path],
                        task_id=job_id,
                    )
                    queued_count += 1
                    logger.info(f"Queued {filename} as job {job_id}")

                except Exception as e:
                    logger.error(f"Error queuing {filename}: {e}")
                    continue

        return queued_count


@celery_app.task(name="api.email_consumer.check_all_customers")
def check_all_customers():
    """Check all customers with email configured for new emails."""
    results = []

    for customer_id in SupabaseClientFactory.list_customers():
        config = SupabaseClientFactory.get_config(customer_id)

        if not config.email_imap:
            continue

        try:
            consumer = EmailConsumer(customer_id)
            count = consumer.process_emails()
            if count > 0:
                results.append(f"{customer_id}: {count} documents queued")
        except Exception as e:
            logger.error(f"Error processing emails for {customer_id}: {e}")
            results.append(f"{customer_id}: Error - {str(e)}")

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # For testing, run directly
    check_all_customers()
