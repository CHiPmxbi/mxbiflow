from pymotego.send_email import EmailAttachment, EmailClient

from mxbi.utils.logger import logger


def send_email(subject: str, body: str, attachments: list[EmailAttachment]) -> None:
    with EmailClient() as client:
        response = client.send(
            subject=subject,
            html_body=body,
            attachments=attachments,
        )
    logger.info(f"Status: {response.status_code}")
    logger.info(f"Body: {response.text}")
