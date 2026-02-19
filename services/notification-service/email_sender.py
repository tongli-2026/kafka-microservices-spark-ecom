import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


class EmailSender:
    """Email sender using Mailhog SMTP."""

    def __init__(self, mailhog_host: str, mailhog_port: int):
        """Initialize email sender."""
        self.mailhog_host = mailhog_host
        self.mailhog_port = mailhog_port

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send email via Mailhog SMTP."""
        try:
            msg = MIMEMultipart()
            msg["From"] = "noreply@kafka-ecom.local"
            msg["To"] = to_email
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "plain"))

            # Connect to Mailhog SMTP (no authentication needed)
            with smtplib.SMTP(self.mailhog_host, self.mailhog_port) as server:
                server.send_message(msg)

            logger.info(f"Email sent to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {e}")
            return False
